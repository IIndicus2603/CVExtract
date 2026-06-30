# Chat orchestration, condense câu hỏi rồi retrieve chunks rồi answer LLM rồi lưu DB

import json
import logging
import time
from typing import AsyncIterator, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import (
    CHAT_LLM_MODEL,
    CHAT_LLM_PROVIDER,
    CHAT_RETRIEVE_TOP_K,
)
from core.llm.client import build_llm_client
from core.schemas import SearchHit
from features.chat.llm.answer import build_answer_messages, format_context
from features.chat.llm.condense import (
    build_condense_messages,
    format_history_for_condense,
)
from features.chat.memory.store import SessionStore
from features.chat.schemas import ChatMessage, ChatResponse, ChatSession

logger = logging.getLogger(__name__)


SearchWithinCVFn = Callable[[str, str, int], Awaitable[list[SearchHit]]]


# Sentinel cuối stream để tách phần text trả lời và phần JSON sources
SOURCES_SENTINEL = "\n__SOURCES__\n"

REFUSAL_MESSAGE = (
    "Tôi không tìm thấy thông tin này trong CV. "
    "Bạn có thể hỏi về kinh nghiệm, kỹ năng, học vấn, hoặc dự án của ứng viên."
)

# LLM lỗi hoặc rate limit trả rỗng thì dùng message này thay vì lưu message rỗng vào DB
LLM_ERROR_MESSAGE = (
    "Xin lỗi, hệ thống đang gián đoạn khi sinh câu trả lời. "
    "Vui lòng thử lại sau ít phút."
)


def _should_refuse(hits: list) -> tuple[bool, float]:
    """Reject khi retrieval rỗng, còn lại để LLM tự từ chối qua prompt answer"""
    if not hits:
        return True, 0.0
    return False, hits[0].score


class ChatService:
    def __init__(self, search_fn: SearchWithinCVFn, store: SessionStore):
        """Init LLM client từ core (provider + client lo abstraction)"""
        self._search = search_fn
        self._store = store
        self._llm = build_llm_client(CHAT_LLM_PROVIDER, CHAT_LLM_MODEL)
        logger.info("ChatService ready: provider=%s model=%s", CHAT_LLM_PROVIDER, CHAT_LLM_MODEL)

    async def create_session(self, db: AsyncSession, cv_key: str) -> ChatSession:
        """Tạo session mới (delegate SessionStore)"""
        return await self._store.create(db, cv_key)

    async def get_session(self, db: AsyncSession, session_id: str) -> ChatSession | None:
        """Lấy info session (không messages)"""
        return await self._store.get(db, session_id)

    async def get_session_full(self, db: AsyncSession, session_id: str) -> ChatSession | None:
        """Lấy session kèm full message history"""
        return await self._store.get_with_messages(db, session_id)

    async def delete_session(self, db: AsyncSession, session_id: str) -> bool:
        """Xoá session + messages"""
        return await self._store.delete(db, session_id)

    async def _condense(
        self, session_id: str, message: str, history_msgs: list[ChatMessage], label: str,
    ) -> tuple[str, int, int, float]:
        """Rewrite follow-up thành standalone, trả (standalone, p_tokens, c_tokens, elapsed)"""
        if not history_msgs:
            return message, 0, 0, 0.0
        t0 = time.perf_counter()
        history_str = format_history_for_condense(history_msgs)
        system, user = build_condense_messages(history_str, message)
        text, usage = await self._llm.chat_text(system, user)
        standalone = text.strip() or message
        elapsed = time.perf_counter() - t0
        logger.info(
            "Condensed%s (session=%s, %.2fs, tokens=p%d/c%d): '%s' -> '%s'",
            label, session_id, elapsed, usage.prompt, usage.completion,
            message[:60], standalone[:60],
        )
        return standalone, usage.prompt, usage.completion, elapsed

    async def chat(self, db: AsyncSession, session_id: str, message: str) -> ChatResponse:
        """Non-streaming chat"""
        session = await self._store.get(db, session_id)
        if session is None:
            raise LookupError(f"Session '{session_id}' not found")

        t_total = time.perf_counter()
        history_msgs = await self._store.get_history(db, session_id)
        standalone, cp, cc, condense_time = await self._condense(
            session_id, message, history_msgs, label="",
        )
        total_prompt = cp
        total_completion = cc

        hits = await self._search(standalone, session.cv_key, CHAT_RETRIEVE_TOP_K)

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

        # Answer LLM dùng câu hỏi GỐC (không phải standalone)
        t_ans = time.perf_counter()
        system, user = build_answer_messages(format_context(hits), message)
        answer_text, ans_usage = await self._llm.chat_text(system, user)
        answer = answer_text.strip()
        total_prompt += ans_usage.prompt
        total_completion += ans_usage.completion
        answer_time = time.perf_counter() - t_ans

        # LLM fail trả rỗng thì thay bằng thông báo thân thiện, không kèm sources
        sources = hits
        if not answer:
            logger.warning("Empty LLM answer (session=%s), dùng LLM_ERROR_MESSAGE", session_id)
            answer = LLM_ERROR_MESSAGE
            sources = []

        await self._store.append_pair(
            db, session_id,
            ChatMessage(role="user", content=message),
            ChatMessage(role="assistant", content=answer, sources=sources),
        )

        total_time = time.perf_counter() - t_total
        logger.info(
            "Chat session=%s | top_score=%.3f | condense=%.2fs | answer=%.2fs | total=%.2fs | hits=%d | tokens=(prompt=%d completion=%d total=%d)",
            session_id, top_score, condense_time, answer_time, total_time, len(hits),
            total_prompt, total_completion, total_prompt + total_completion,
        )
        return ChatResponse(message=answer, sources=sources)

    async def chat_stream(self, db: AsyncSession, session_id: str, message: str) -> AsyncIterator[str]:
        """Streaming chat, yield text chunks + SOURCES_SENTINEL + JSON sources cuối"""
        session = await self._store.get(db, session_id)
        if session is None:
            raise LookupError(f"Session '{session_id}' not found")

        t_total = time.perf_counter()
        history_msgs = await self._store.get_history(db, session_id)
        standalone, cp, cc, condense_time = await self._condense(
            session_id, message, history_msgs, label="[stream]",
        )
        total_prompt = cp
        total_completion = cc

        hits = await self._search(standalone, session.cv_key, CHAT_RETRIEVE_TOP_K)

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

        # Stream answer LLM dùng câu hỏi GỐC
        t_ans = time.perf_counter()
        buffer: list[str] = []
        system, user = build_answer_messages(format_context(hits), message)
        async for chunk in self._llm.stream_text(system, user):
            if chunk.delta:
                buffer.append(chunk.delta)
                yield chunk.delta
            if chunk.usage is not None:
                total_prompt += chunk.usage.prompt
                total_completion += chunk.usage.completion

        answer = "".join(buffer).strip()
        answer_time = time.perf_counter() - t_ans

        # Stream rỗng (LLM fail giữa chừng hoặc rate limit) thì yield thông báo thân thiện
        sources = hits
        if not answer:
            logger.warning("Empty LLM stream answer (session=%s), dùng LLM_ERROR_MESSAGE", session_id)
            answer = LLM_ERROR_MESSAGE
            sources = []
            yield answer

        sources_json = json.dumps(
            [h.model_dump() for h in sources], ensure_ascii=False,
        )
        yield SOURCES_SENTINEL + sources_json

        await self._store.append_pair(
            db, session_id,
            ChatMessage(role="user", content=message),
            ChatMessage(role="assistant", content=answer, sources=sources),
        )

        total_time = time.perf_counter() - t_total
        logger.info(
            "ChatStream session=%s | top_score=%.3f | condense=%.2fs | answer=%.2fs | total=%.2fs | hits=%d | tokens=(prompt=%d completion=%d total=%d)",
            session_id, top_score, condense_time, answer_time, total_time, len(hits),
            total_prompt, total_completion, total_prompt + total_completion,
        )
