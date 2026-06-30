# Điều phối các service, extraction - parsing - storage - retrieval - matching - chatbot

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
    JD_MATCH_DEFAULT_TOP_K,
    PARSING_LLM_MODEL, PARSING_LLM_PROVIDER,
    QDRANT_COLLECTION, QDRANT_URL,
    RERANKER_MODEL,
)

from core.database import AsyncSessionLocal, engine, get_db, init_db
from core.logger import setup_logging
from core.embeddings.embedder import Embedder
from core.embeddings.reranker import Reranker
from core.registries import NameRegistry, SkillRegistry
from core.vector_store import VectorStore
from features.chat.memory.store import SessionStore, cleanup_expired_sessions_loop
from features.chat.schemas import (
    ChatRequest, ChatResponse, ChatSession,
    CreateSessionRequest, CreateSessionResponse,
)
from features.chat.service import ChatService
from features.extraction.schemas import CVResult, CVStatus
from features.extraction.service import CVExtractorService
from features.matching.schemas import JDMatchRequest, MatchResponse
from features.matching.service import MatchingService
from features.parsing.service import NOT_A_CV_MESSAGE, ParsingService
from features.retrieval.schemas import SemanticSearchRequest
from features.retrieval.service import RetrievalService
from features.storage.schemas import CVSaveData
from features.storage.service import StorageService

setup_logging()
logger = logging.getLogger(__name__)


# Singletons (lifespan-bound)
_extractor = CVExtractorService()
_parser = ParsingService(provider=PARSING_LLM_PROVIDER, model=PARSING_LLM_MODEL)
_storage = StorageService()
_name_registry = NameRegistry()
_skill_registry = SkillRegistry()
_retrieval: RetrievalService | None = None
_vector_store: VectorStore | None = None
_session_store: SessionStore | None = None
_chat_service: ChatService | None = None
_matching: MatchingService | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Khởi tạo DB + Qdrant + embedder/reranker + chat services, cleanup khi shutdown"""
    global _retrieval, _vector_store, _session_store, _chat_service, _matching

    await init_db()

    # Nạp registries từ DB (dùng cho query filter)
    async with AsyncSessionLocal() as db:
        await _name_registry.load_from_db(db)
        await _skill_registry.load_from_db(db)

    _vector_store = VectorStore(
        url=QDRANT_URL,
        collection=QDRANT_COLLECTION,
        vector_dim=EMBEDDING_DIM,
    )
    await _vector_store.ensure_collection()

    embedder = Embedder(model_name=EMBEDDING_MODEL, expected_dim=EMBEDDING_DIM)
    reranker = Reranker(model_name=RERANKER_MODEL) if RERANKER_MODEL else None

    _retrieval = RetrievalService(
        embedder=embedder,
        vector_store=_vector_store,
        reranker=reranker,
        name_registry=_name_registry,
        skill_registry=_skill_registry,
    )

    _matching = MatchingService(
        provider=PARSING_LLM_PROVIDER,
        model=PARSING_LLM_MODEL,
        embedder=embedder,
        vector_store=_vector_store,
        get_cvs_fn=_storage.get_by_keys,
        reranker=reranker,
    )

    _session_store = SessionStore(history_last_n=CHAT_HISTORY_LAST_N)
    _chat_service = ChatService(search_fn=_retrieval.search_within_cv, store=_session_store)

    cleanup_task = asyncio.create_task(cleanup_expired_sessions_loop())

    logger.info("Startup complete: MySQL + Qdrant + embedder%s + chat ready",
                " + reranker" if reranker else "")

    yield

    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    await _vector_store.close()
    await engine.dispose()


app = FastAPI(title="CV Extraction API", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


# Cho list[UploadFile], Swagger UI cần "format, binary" để render file picker
def _patch_binary_uploads(schema: dict) -> None:
    """Walk schema, convert contentMediaType=octet-stream thành format=binary"""
    if isinstance(schema, dict):
        if (
            schema.get("type") == "string"
            and schema.pop("contentMediaType", None) == "application/octet-stream"
        ):
            schema["format"] = "binary"
        for v in schema.values():
            _patch_binary_uploads(v)
    elif isinstance(schema, list):
        for v in schema:
            _patch_binary_uploads(v)


_original_openapi = app.openapi


def _patched_openapi():
    """Wrap FastAPI.openapi() để apply binary-upload patch"""
    schema = _original_openapi()
    _patch_binary_uploads(schema)
    return schema


app.openapi = _patched_openapi


# Frontend
@app.get("/")
def index():
    """Trang chính (SPA)"""
    return FileResponse("static/index.html")


# Upload
@app.post("/UploadCV")
async def upload_cv(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """Upload 1 file CV, extract rồi parse LLM rồi classify rồi lưu MySQL rồi index Qdrant"""
    logger.info("UploadCV | file=%s", file.filename)
    stem, ext = os.path.splitext(file.filename)
    ext = ext.lower()

    if not _extractor.supports(ext):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: '{ext}'. Supported: .pdf, .docx",
        )

    result = await _extractor.extract_file(file, ext)
    if result.status == CVStatus.ERROR:
        raise HTTPException(status_code=422, detail=result.error_message)

    parsed, usage = await _parser.parse(result.text)
    logger.info(
        "Parse '%s' tokens: prompt=%d completion=%d total=%d",
        result.file_name, usage.prompt, usage.completion, usage.total,
    )
    is_cv, parsed = _parser.classify(parsed)
    if not is_cv:
        raise HTTPException(status_code=422, detail=NOT_A_CV_MESSAGE)
    text = json.dumps(parsed, ensure_ascii=False, indent=2) if parsed else result.text

    await _storage.save(db, CVSaveData(
        key=stem.lower(),
        file_name=result.file_name,
        extension=result.extension,
        status=result.status,
        text=text,
    ))

    # Index Qdrant, lỗi KHÔNG fail request
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


# Browser webkitdirectory upload, nhiều file qua multipart, backend lọc .pdf/.docx
@app.post("/UploadMultipleCVs")
async def upload_multiple_cvs(files: list[UploadFile] = File(...), db: AsyncSession = Depends(get_db)):
    """Upload batch nhiều file CV, file unsupported báo lỗi cùng response"""
    logger.info("UploadMultipleCVs | files=%d", len(files))
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    extract_tasks: list[tuple] = []
    errors: list[CVResult] = []
    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if not _extractor.supports(ext):
            errors.append(CVResult(
                file_name=f.filename, extension=ext,
                status=CVStatus.ERROR,
                error_message=f"Unsupported file type: '{ext}'",
            ))
        else:
            extract_tasks.append((f, ext))

    if not extract_tasks:
        raise HTTPException(status_code=400, detail="No supported files in selection (.pdf, .docx only)")

    extracted = list(await asyncio.gather(*[
        _extractor.extract_file(f, ext) for f, ext in extract_tasks
    ]))

    success = [r for r in extracted if r.status == CVStatus.SUCCESS]
    errors.extend(r for r in extracted if r.status == CVStatus.ERROR)

    parsed_list, batch_usage = await _parser.parse_many([r.text for r in success])
    logger.info(
        "ParseBatch files=%d tokens: prompt=%d completion=%d total=%d (across %d success)",
        len(files), batch_usage.prompt, batch_usage.completion, batch_usage.total, len(success),
    )

    # File parse OK nhưng không phải CV thì chuyển sang errors
    saved: list[tuple] = []
    for r, parsed in zip(success, parsed_list):
        is_cv, parsed = _parser.classify(parsed)
        if not is_cv:
            r.status = CVStatus.ERROR
            r.error_message = NOT_A_CV_MESSAGE
            errors.append(r)
        else:
            saved.append((r, parsed))

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

    # Index Qdrant song song, lỗi 1 CV không fail cả batch
    async def _index_safe(key, parsed):
        try:
            await _retrieval.index_cv(cv_key=key, parsed=parsed)
        except Exception as e:
            logger.error("Index failed for '%s': %s", key, e)

    await asyncio.gather(*[
        _index_safe(os.path.splitext(r.file_name)[0].lower(), parsed)
        for r, parsed in saved
    ])

    for r in errors:
        batch_items.append({
            "file_name": r.file_name,
            "status": r.status,
            "error_message": r.error_message,
        })

    return {
        "message": "CV upload process completed",
        "total": len(files),
        "succeeded": len(saved),
        "failed": len(errors),
        "errors": [{"file": r.file_name, "reason": r.error_message} for r in errors],
        "results": batch_items,
        "tokens": {
            "prompt": batch_usage.prompt,
            "completion": batch_usage.completion,
            "total": batch_usage.total,
        },
    }


# Storage CRUD
@app.get("/Storage")
async def get_storage(db: AsyncSession = Depends(get_db)):
    """Trả toàn bộ CV trong DB dạng dict {key, cv_dict}"""
    return {"cv_storage": await _storage.get_all(db)}


@app.get("/Storage/{cv_key}")
async def get_cv_detail(cv_key: str, db: AsyncSession = Depends(get_db)):
    """Chi tiết 1 CV theo key, 404 nếu không có"""
    cv = await _storage.get_by_key(db, cv_key.lower())
    if cv is None:
        raise HTTPException(status_code=404, detail=f"CV '{cv_key}' not found")
    return cv


@app.patch("/Storage/{cv_key}")
async def update_cv(cv_key: str, payload: dict, db: AsyncSession = Depends(get_db)):
    """Update parsed fields của 1 CV + re-index Qdrant"""
    key = cv_key.lower()
    parsed = payload.get("parsed")
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="Missing 'parsed' object in body")

    ok = await _storage.update(db, key, parsed)
    if not ok:
        raise HTTPException(status_code=404, detail=f"CV '{cv_key}' not found")

    # Re-index Qdrant, lỗi KHÔNG fail request
    try:
        await _retrieval.index_cv(cv_key=key, parsed=parsed)
    except Exception as e:
        logger.error("Failed to re-index '%s' after update: %s", key, e)

    return {"message": "CV updated", "cv_key": key}


@app.delete("/Storage/{cv_key}")
async def delete_cv(cv_key: str, db: AsyncSession = Depends(get_db)):
    """Xoá CV khỏi MySQL + Qdrant + NameRegistry"""
    key = cv_key.lower()
    ok = await _storage.delete(db, key)
    if not ok:
        raise HTTPException(status_code=404, detail=f"CV '{cv_key}' not found")

    try:
        await _retrieval.remove_cv(key)
    except Exception as e:
        logger.error("Failed to remove '%s' from retrieval: %s", key, e)

    return {"message": "CV deleted", "cv_key": key}


# Semantic search
@app.post("/Search/Semantic")
async def search_semantic(req: SemanticSearchRequest, db: AsyncSession = Depends(get_db)):
    """Vector search rồi group theo CV, sort theo score"""
    hits = await _retrieval.search(query=req.query, top_k=req.top_k)

    # Fetch full CV 1 query theo cv_key duy nhất, skip CV bị xoá khỏi MySQL
    order = list(dict.fromkeys(h.cv_key for h in hits))
    cv_map = await _storage.get_by_keys(db, order)

    # Group hits theo cv_key, sort theo score
    seen: dict[str, dict] = {}
    for hit in hits:
        cv = cv_map.get(hit.cv_key)
        if cv is None:
            continue
        if hit.cv_key not in seen:
            seen[hit.cv_key] = {
                "cv_key": hit.cv_key,
                "cv": cv,
                "matched_chunks": [],
                "score": hit.score,
            }
        seen[hit.cv_key]["matched_chunks"].append({
            "section": hit.section,
            "text": hit.chunk_text,
            "score": hit.score,
        })

    results = sorted(seen.values(), key=lambda x: -x["score"])
    return {
        "query": req.query,
        "total_cvs": len(results),
        "results": results,
    }


# JD matching
@app.post("/Match/JD", response_model=MatchResponse)
async def match_jd(req: JDMatchRequest, db: AsyncSession = Depends(get_db)):
    """Match JD text ra top-K CV phù hợp kèm score aggregated"""
    logger.info("MatchJD | jd_len=%d top_k=%d", len(req.jd_text), req.top_k)
    return await _matching.match(
        db, req.jd_text, req.top_k,
        strict_skills_filter=req.strict_skills_filter,
        strict_years_filter=req.strict_years_filter,
        llm_evaluate=req.llm_evaluate,
    )


@app.post("/Match/JD/Upload", response_model=MatchResponse)
async def match_jd_upload(
    file: UploadFile = File(...),
    top_k: int = Form(JD_MATCH_DEFAULT_TOP_K, ge=1, le=50),
    strict_skills_filter: bool = Form(False),
    strict_years_filter: bool = Form(True),
    llm_evaluate: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    """Match JD upload PDF/DOCX ra top-K CV phù hợp"""
    logger.info("MatchJD/Upload | file=%s top_k=%d", file.filename, top_k)
    _, ext = os.path.splitext(file.filename)
    ext = ext.lower()
    if not _extractor.supports(ext):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: '{ext}'. Supported: .pdf, .docx",
        )

    result = await _extractor.extract_file(file, ext)
    if result.status == CVStatus.ERROR:
        raise HTTPException(status_code=422, detail=result.error_message)

    return await _matching.match(
        db, result.text, top_k,
        strict_skills_filter=strict_skills_filter,
        strict_years_filter=strict_years_filter,
        llm_evaluate=llm_evaluate,
    )


# Chatbot
@app.post("/Chat/Sessions", response_model=CreateSessionResponse)
async def create_chat_session(
    request: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Tạo phiên chat mới gắn với 1 CV, 404 nếu cv_key không tồn tại"""
    cv_key = request.cv_key.lower()
    cv = await _storage.get_by_key(db, cv_key)
    if cv is None:
        raise HTTPException(status_code=404, detail=f"CV '{request.cv_key}' not found")
    session = await _chat_service.create_session(db, cv_key=cv_key)
    return CreateSessionResponse(session_id=session.session_id, cv_key=session.cv_key)


@app.post("/Chat/Sessions/{session_id}/Messages", response_model=ChatResponse)
async def send_chat_message(
    session_id: str,
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Gửi 1 message, response non-streaming kèm sources"""
    try:
        return await _chat_service.chat(db, session_id, request.message)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/Chat/Sessions/{session_id}/Messages/Stream")
async def send_chat_message_stream(
    session_id: str,
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Streaming text response + __SOURCES__ sentinel + JSON sources cuối"""
    if await _chat_service.get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return StreamingResponse(
        _chat_service.chat_stream(db, session_id, request.message),
        media_type="text/plain; charset=utf-8",
    )


@app.get("/Chat/Sessions/{session_id}", response_model=ChatSession)
async def get_chat_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Lịch sử đầy đủ + metadata phiên chat"""
    session = await _chat_service.get_session_full(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return session


@app.delete("/Chat/Sessions/{session_id}")
async def delete_chat_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Xoá phiên chat + CASCADE xoá messages"""
    if not await _chat_service.delete_session(db, session_id):
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {"message": "Session deleted"}


if __name__ == "__main__":
    import uvicorn
    # log_config=None để uvicorn giữ nguyên cấu hình logging từ setup_logging
    uvicorn.run(app, host="127.0.0.1", port=8000, log_config=None)
