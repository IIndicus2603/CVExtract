# Điều phối các service: extraction - parsing - storage - retrieval - chatbot

from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import (
    CHAT_HISTORY_LAST_N,
    EMBEDDING_DIM, EMBEDDING_MODEL,
    PARSING_LLM_MODEL, PARSING_LLM_PROVIDER,
    QDRANT_COLLECTION, QDRANT_URL,
    RERANKER_MODEL,
)
from core.database import engine, get_db, init_db
from core.logger import setup_logging
from features.chat.memory.store import SessionStore, cleanup_expired_sessions_loop
from features.chat.schemas import (
    ChatRequest, ChatResponse, ChatSession,
    CreateSessionRequest, CreateSessionResponse,
)
from features.chat.service import ChatService
from features.extraction.schemas import CVStatus
from features.extraction.service import CVExtractorService
from features.parsing.service import ParsingService
from features.retrieval.models.embedder import Embedder
from features.retrieval.models.reranker import Reranker
from features.retrieval.pipeline.vector_store import VectorStore
from features.retrieval.schemas import SemanticSearchRequest
from features.retrieval.service import RetrievalService
from features.storage.schemas import CVSaveData
from features.storage.service import StorageService

setup_logging()
logger = logging.getLogger(__name__)


# Globals khởi tạo trong lifespan, dùng chung cho mọi request
# ChatService cũng init ở lifespan (không module level) vì cần _retrieval ready
_retrieval: RetrievalService | None = None
_vector_store: VectorStore | None = None
_session_store: SessionStore | None = None
_chat_service: ChatService | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _retrieval, _vector_store, _session_store, _chat_service

    # MySQL
    await init_db()

    # Qdrant: tạo collection nếu chưa có
    _vector_store = VectorStore(
        url=QDRANT_URL,
        collection=QDRANT_COLLECTION,
        vector_dim=EMBEDDING_DIM,
    )
    await _vector_store.ensure_collection()

    # Embedder: load eager lúc startup
    embedder = Embedder(model_name=EMBEDDING_MODEL, expected_dim=EMBEDDING_DIM)

    # Reranker: optional. Set RERANKER_MODEL="" trong .env để tắt
    reranker = Reranker(model_name=RERANKER_MODEL) if RERANKER_MODEL else None

    _retrieval = RetrievalService(
        embedder=embedder,
        vector_store=_vector_store,
        reranker=reranker,
    )

    # Chat layer DB-backed; main inject hàm search vào, chat không phụ thuộc retrieval
    _session_store = SessionStore(history_last_n=CHAT_HISTORY_LAST_N)
    _chat_service = ChatService(search_fn=_retrieval.search_within_cv, store=_session_store)

    cleanup_task = asyncio.create_task(cleanup_expired_sessions_loop())

    logger.info("Startup complete: MySQL + Qdrant + embedder%s + chat ready",
                " + reranker" if reranker else "")

    yield

    # Cleanup
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    await _vector_store.close()
    await engine.dispose()


app = FastAPI(title="CV Extraction API", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")



# Khởi tạo 1 lần, dùng chung cho mọi request
# Provider + model parsing đọc từ .env (PARSING_LLM_PROVIDER / PARSING_LLM_MODEL)
_extractor = CVExtractorService()
_parser = ParsingService(provider=PARSING_LLM_PROVIDER, model=PARSING_LLM_MODEL)
_storage = StorageService()

# Confidence tối thiểu để công nhận document là CV
CV_CONFIDENCE_THRESHOLD = 0.5
NOT_A_CV_MESSAGE = "Document does not appear to be a CV"


# Kiểm tra có phải CV không
def _classify_cv(parsed: dict) -> tuple[bool, dict]:
    if not parsed:
        # Fallback raw text, coi là success
        return True, parsed
    is_cv = bool(parsed.pop("is_cv", False))
    confidence = float(parsed.pop("confidence", 0) or 0)
    return is_cv and confidence >= CV_CONFIDENCE_THRESHOLD, parsed


# Frontend
@app.get("/")
def index():
    return FileResponse("static/index.html")


# Upload 1 CV
@app.post("/UploadCV")
async def upload_cv(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    logger.info("UploadCV | file=%s", file.filename)
    stem, ext = os.path.splitext(file.filename)
    ext = ext.lower()

    # Chỉ chấp nhận .pdf và .docx
    if not _extractor.supports(ext):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: '{ext}'. Supported: .pdf, .docx",
        )

    # Extract text từ file
    result = await _extractor.extract_file(file, ext)
    if result.status == CVStatus.ERROR:
        raise HTTPException(status_code=422, detail=result.error_message)

    # Nhờ LLM parse text thành JSON. Nếu fail thì giữ nguyên text gốc
    parsed = await _parser.parse(result.text)
    is_cv, parsed = _classify_cv(parsed)
    if not is_cv:
        raise HTTPException(status_code=422, detail=NOT_A_CV_MESSAGE)
    text = json.dumps(parsed, ensure_ascii=False, indent=2) if parsed else result.text

    # Lưu xuống MySQL (key = tên file không có .ext)
    await _storage.save(db, CVSaveData(
        key=stem.lower(),
        file_name=result.file_name,
        extension=result.extension,
        status=result.status,
        text=text,
    ))

    # Index vào Qdrant. Lỗi ở đây KHÔNG fail request.
    # MySQL là source of truth, Qdrant là derived index có thể rebuild.
    try:
        await _retrieval.index_cv(cv_key=stem.lower(), parsed=parsed)
    except Exception as e:
        logger.error("Failed to index '%s' to Qdrant: %s", stem, e)

    return {
        "message": "CV uploaded successfully",
        "results": {
            "file_name": result.file_name,
            "extension": result.extension,
            "status": result.status,
            "text": text,
        },
    }


# Upload nhiều CV từ 1 folder
@app.post("/UploadMultipleCVs")
async def upload_multiple_cvs(folder_path: str = Form(...), db: AsyncSession = Depends(get_db)):
    logger.info("UploadMultipleCVs | folder=%s", folder_path)
    if not os.path.isdir(folder_path):
        raise HTTPException(status_code=400, detail=f"Folder not found: '{folder_path}'")

    # Extract toàn bộ file trong folder
    results = await _extractor.extract_folder(folder_path)
    if not results:
        raise HTTPException(status_code=400, detail="No supported files found in the specified folder")

    # Tách kết quả thành 2 nhóm: thành công và lỗi
    success = [r for r in results if r.status == CVStatus.SUCCESS]
    errors = [r for r in results if r.status == CVStatus.ERROR]

    # Parse song song các file thành công
    parsed_list = await _parser.parse_many([r.text for r in success])

    # Loại các file không phải CV ra khỏi nhóm success, chuyển sang errors
    saved: list[tuple] = []
    for r, parsed in zip(success, parsed_list):
        is_cv, parsed = _classify_cv(parsed)
        if not is_cv:
            r.status = CVStatus.ERROR
            r.error_message = NOT_A_CV_MESSAGE
            errors.append(r)
        else:
            saved.append((r, parsed))

    # Lưu DB và build response
    batch_items: list[dict] = []
    for r, parsed in saved:
        text = json.dumps(parsed, ensure_ascii=False, indent=2) if parsed else r.text
        await _storage.save(db, CVSaveData(
            key=os.path.splitext(r.file_name)[0].lower(),
            file_name=r.file_name,
            extension=r.extension,
            status=r.status,
            text=text,
        ))
        batch_items.append({"file_name": r.file_name, "status": r.status})

    # Index tất cả CV thành công vào Qdrant song song
    # Lỗi từng CV không fail cả batch
    async def _index_safe(key, parsed):
        try:
            await _retrieval.index_cv(cv_key=key, parsed=parsed)
        except Exception as e:
            logger.error("Index failed for '%s': %s", key, e)

    await asyncio.gather(*[
        _index_safe(os.path.splitext(r.file_name)[0].lower(), parsed)
        for r, parsed in saved
    ])

    # Thêm các file lỗi vào response (không lưu DB)
    for r in errors:
        batch_items.append({
            "file_name": r.file_name,
            "status": r.status,
            "error_message": r.error_message,
        })

    return {
        "message": "CV upload process completed",
        "total": len(results),
        "succeeded": len(saved),
        "failed": len(errors),
        "errors": [{"file": r.file_name, "reason": r.error_message} for r in errors],
        "results": batch_items,
    }


# Trả về toàn bộ CV đã lưu
@app.get("/Storage")
async def get_storage(db: AsyncSession = Depends(get_db)):
    return {"cv_storage": await _storage.get_all(db)}


@app.post("/Search/Semantic")
async def search_semantic(req: SemanticSearchRequest, db: AsyncSession = Depends(get_db)):
    hits = await _retrieval.search(query=req.query, top_k=req.top_k)

    # Group hits theo cv_key + fetch full CV từ MySQL
    seen: dict[str, dict] = {}
    for hit in hits:
        if hit.cv_key not in seen:
            cv = await _storage.get_by_key(db, hit.cv_key)
            if cv is None:
                # Edge case: CV bị xóa khỏi MySQL nhưng còn trong Qdrant
                continue
            seen[hit.cv_key] = {
                "cv_key": hit.cv_key,
                "cv": cv,
                "matched_chunks": [],
                "best_score": hit.score,
            }
        seen[hit.cv_key]["matched_chunks"].append({
            "section": hit.section,
            "text": hit.chunk_text,
            "score": hit.score,
        })

    # Sort theo best_score giảm dần
    results = sorted(seen.values(), key=lambda x: -x["best_score"])

    return {
        "query": req.query,
        "total_hits": len(hits),
        "results": results,
    }


# Conversational chat
# Tạo session, verify cv_key exists trong DB
@app.post("/Chat/Sessions", response_model=CreateSessionResponse)
async def create_chat_session(
    request: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
):
    cv_key = request.cv_key.lower()
    cv = await _storage.get_by_key(db, cv_key)
    if cv is None:
        raise HTTPException(status_code=404, detail=f"CV '{request.cv_key}' not found")
    session = await _chat_service.create_session(db, cv_key=cv_key)
    return CreateSessionResponse(session_id=session.session_id, cv_key=session.cv_key)


# Gửi 1 message, response non-streaming
@app.post("/Chat/Sessions/{session_id}/Messages", response_model=ChatResponse)
async def send_chat_message(
    session_id: str,
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _chat_service.chat(db, session_id, request.message)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


# Streaming response plain text
@app.post("/Chat/Sessions/{session_id}/Messages/Stream")
async def send_chat_message_stream(
    session_id: str,
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    if await _chat_service.get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return StreamingResponse(
        _chat_service.chat_stream(db, session_id, request.message),
        media_type="text/plain; charset=utf-8",
    )


# Lịch sử đầy đủ + metadata session
@app.get("/Chat/Sessions/{session_id}", response_model=ChatSession)
async def get_chat_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await _chat_service.get_session_full(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return session


# Xoá session chat
@app.delete("/Chat/Sessions/{session_id}")
async def delete_chat_session(session_id: str, db: AsyncSession = Depends(get_db)):
    if not await _chat_service.delete_session(db, session_id):
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {"message": "Session deleted"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
