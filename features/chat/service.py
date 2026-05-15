# Lớp điều phối chat: viết lại câu hỏi, tìm các đoạn CV liên quan,
# gọi llm trả lời, lưu vào DB (user và bot cùng lưu 1 lần)

import json
import logging
import time
from typing import AsyncIterator, Awaitable, Callable

from langchain_groq import ChatGroq
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import CHAT_LLM_MODEL, CHAT_REFUSAL_SCORE_THRESHOLD, GROQ_API_KEY
from features.chat.llm.answer import build_answer_chain, format_context
from features.chat.llm.condense import (
    build_condense_chain,
    format_history_for_condense,
)
from features.chat.memory.store import SessionStore
from features.chat.schemas import ChatMessage, ChatResponse, ChatSession
from features.retrieval.schemas import SearchHit

logger = logging.getLogger(__name__)


# Hàm tìm kiếm CV trả về list SearchHit
SearchWithinCVFn = Callable[[str, str, int], Awaitable[list[SearchHit]]]


# Số đoạn CV tốt nhất lấy ra mỗi câu hỏi
RETRIEVE_TOP_K = 5

# Đánh dấu cuối stream để tách phần text trả lời và phần danh sách sources
SOURCES_SENTINEL = "\n__SOURCES__\n"

# Reject cố định khi không tìm thấy thông tin liên quan
REFUSAL_MESSAGE = (
    "Tôi không tìm thấy thông tin này trong CV. "
    "Bạn có thể hỏi về kinh nghiệm, kỹ năng, học vấn, hoặc dự án của ứng viên."
)

# Reject: không tìm được đoạn nào hoặc điểm cao nhất dưới ngưỡng
def _should_refuse(hits: list) -> tuple[bool, float]:
    if not hits:
        return True, 0.0
    top_score = hits[0].score
    return top_score < CHAT_REFUSAL_SCORE_THRESHOLD, top_score


class ChatService:
    def __init__(self, search_fn: SearchWithinCVFn, store: SessionStore):
        self._search = search_fn
        self._store = store
        self._llm = ChatGroq(api_key=GROQ_API_KEY, model=CHAT_LLM_MODEL, temperature=0.3, max_tokens=1024, timeout=30)
        # Tạo 2 pipeline 1 lần lúc khởi tạo, dùng chung cho mọi request
        self._condense_chain = build_condense_chain(self._llm)
        self._answer_chain = build_answer_chain(self._llm)
        logger.info("ChatService ready: model=%s", CHAT_LLM_MODEL)

    async def create_session(self, db: AsyncSession, cv_key: str) -> ChatSession:
        return await self._store.create(db, cv_key)

    # Chỉ lấy info chính của phiên
    async def get_session(self, db: AsyncSession, session_id: str) -> ChatSession | None:
        return await self._store.get(db, session_id)

    async def get_session_full(self, db: AsyncSession, session_id: str) -> ChatSession | None:
        return await self._store.get_with_messages(db, session_id)

    async def delete_session(self, db: AsyncSession, session_id: str) -> bool:
        return await self._store.delete(db, session_id)

    # Non streaming
    async def chat(self, db: AsyncSession, session_id: str, message: str) -> ChatResponse:
        session = await self._store.get(db, session_id)
        if session is None:
            raise LookupError(f"Session '{session_id}' not found")

        t_total = time.perf_counter()

        # Lượt đầu (chưa có lịch sử) thì không cần viết lại câu hỏi
        history_msgs = await self._store.get_history(db, session_id)
        condense_time = 0.0
        if history_msgs:
            t_cd = time.perf_counter()
            history_str = format_history_for_condense(history_msgs)
            standalone = await self._condense_chain.ainvoke({
                "chat_history": history_str,
                "question": message,
            })
            standalone = standalone.strip()
            condense_time = time.perf_counter() - t_cd
            logger.info(
                "Condensed (session=%s, %.2fs): '%s' -> '%s'",
                session_id, condense_time, message[:60], standalone[:60],
            )
        else:
            standalone = message

        # Tìm đoạn CV liên quan; bắt buộc chỉ tìm trong đúng 1 CV của session này
        hits = await self._search(standalone, session.cv_key, RETRIEVE_TOP_K)

        # Nếu điểm cao nhất quá thấp thì từ chối luôn
        refuse, top_score = _should_refuse(hits)
        if refuse:
            logger.info(
                "Refused query (top_score=%.3f, session=%s): %s",
                top_score, session_id, message[:50],
            )
            await self._store.append_pair(
                db, session_id,
                ChatMessage(role="user", content=message),
                ChatMessage(role="assistant", content=REFUSAL_MESSAGE, sources=[]),
            )
            return ChatResponse(message=REFUSAL_MESSAGE, sources=[])

        # Cho LLM trả lời theo đúng câu hỏi gốc của user 
        t_ans = time.perf_counter()
        context = format_context(hits)
        answer = await self._answer_chain.ainvoke({
            "context": context,
            "question": message,
        })
        answer = answer.strip()
        answer_time = time.perf_counter() - t_ans

        # Lưu cả user và bot cùng lúc
        await self._store.append_pair(
            db, session_id,
            ChatMessage(role="user", content=message),
            ChatMessage(role="assistant", content=answer, sources=hits),
        )

        total_time = time.perf_counter() - t_total
        logger.info(
            "Chat session=%s | top_score=%.3f | condense=%.2fs | answer=%.2fs | total=%.2fs | hits=%d",
            session_id, top_score, condense_time, answer_time, total_time, len(hits),
        )
        return ChatResponse(message=answer, sources=hits)

    # Streaming
    async def chat_stream(self, db: AsyncSession, session_id: str, message: str) -> AsyncIterator[str]:
        session = await self._store.get(db, session_id)
        if session is None:
            raise LookupError(f"Session '{session_id}' not found")

        t_total = time.perf_counter()

        history_msgs = await self._store.get_history(db, session_id)
        condense_time = 0.0
        if history_msgs:
            t_cd = time.perf_counter()
            history_str = format_history_for_condense(history_msgs)
            standalone = await self._condense_chain.ainvoke({
                "chat_history": history_str,
                "question": message,
            })
            standalone = standalone.strip()
            condense_time = time.perf_counter() - t_cd
            logger.info(
                "Condensed[stream] (session=%s, %.2fs): '%s' -> '%s'",
                session_id, condense_time, message[:60], standalone[:60],
            )
        else:
            standalone = message

        hits = await self._search(standalone, session.cv_key, RETRIEVE_TOP_K)

        # Reject
        refuse, top_score = _should_refuse(hits)
        if refuse:
            logger.info(
                "Refused query[stream] (top_score=%.3f, session=%s): %s",
                top_score, session_id, message[:50],
            )
            yield REFUSAL_MESSAGE
            yield SOURCES_SENTINEL + "[]"
            await self._store.append_pair(
                db, session_id,
                ChatMessage(role="user", content=message),
                ChatMessage(role="assistant", content=REFUSAL_MESSAGE, sources=[]),
            )
            return

        context = format_context(hits)

        t_ans = time.perf_counter()
        buffer: list[str] = []
        async for chunk in self._answer_chain.astream({
            "context": context,
            "question": message,
        }):
            buffer.append(chunk)
            yield chunk

        answer = "".join(buffer).strip()
        answer_time = time.perf_counter() - t_ans 

        # Sau khi trả lời xong, gửi ký hiệu phân cách
        sources_json = json.dumps(
            [h.model_dump() for h in hits], ensure_ascii=False,
        )
        yield SOURCES_SENTINEL + sources_json

        # Lưu cả cuộc trò chuyện sau khi stream xong
        await self._store.append_pair(
            db, session_id,
            ChatMessage(role="user", content=message),
            ChatMessage(role="assistant", content=answer, sources=hits),
        )

        total_time = time.perf_counter() - t_total
        logger.info(
            "ChatStream session=%s | top_score=%.3f | condense=%.2fs | answer=%.2fs | total=%.2fs | hits=%d",
            session_id, top_score, condense_time, answer_time, total_time, len(hits),
        )
