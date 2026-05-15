# Lưu/đọc phiên chat trong MySQL + task nền dọn dẹp phiên quá hạn

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import CHAT_SESSION_TTL_HOURS
from core.database import AsyncSessionLocal
from core.models import ChatMessageDB, ChatSessionDB
from features.chat.schemas import ChatMessage, ChatSession
from features.retrieval.schemas import SearchHit

logger = logging.getLogger(__name__)


# Task nền: mỗi 1h, xoá phiên chat quá hạn (last_activity_at < now - TTL)
# CASCADE FK xoá luôn messages của phiên đó
async def cleanup_expired_sessions_loop():
    while True:
        try:
            await asyncio.sleep(3600)
            async with AsyncSessionLocal() as db:
                cutoff = datetime.utcnow() - timedelta(hours=CHAT_SESSION_TTL_HOURS)
                result = await db.execute(
                    delete(ChatSessionDB).where(ChatSessionDB.last_activity_at < cutoff)
                )
                await db.commit()
                logger.info(
                    "Chat cleanup: deleted %d expired sessions (cutoff=%s)",
                    result.rowcount, cutoff.isoformat(),
                )
        except asyncio.CancelledError:
            logger.info("Chat cleanup task stopped")
            break
        except Exception as e:
            logger.error("Chat cleanup error: %s", e)


class SessionStore:
    def __init__(self, history_last_n: int = 10):
        self._history_last_n = history_last_n

    # Tạo phiên chat mới với mã ngẫu nhiên UUID4, gắn vào 1 CV cụ thể
    async def create(self, db: AsyncSession, cv_key: str) -> ChatSession:
        row = ChatSessionDB(session_id=str(uuid.uuid4()), cv_key=cv_key)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        logger.debug("Created session %s for cv_key=%s", row.session_id, cv_key)
        return _to_session_metadata(row)

    # Chỉ lấy info chính của phiên
    async def get(self, db: AsyncSession, session_id: str) -> ChatSession | None:
        row = await db.scalar(
            select(ChatSessionDB).where(ChatSessionDB.session_id == session_id)
        )
        return _to_session_metadata(row) if row else None

    # Lấy phiên chat kèm tất cả tin nhắn (GET /Chat/Sessions/{id})
    async def get_with_messages(self, db: AsyncSession, session_id: str) -> ChatSession | None:
        row = await db.scalar(
            select(ChatSessionDB).where(ChatSessionDB.session_id == session_id)
        )
        if row is None:
            return None
        msg_rows = (await db.execute(
            select(ChatMessageDB)
            .where(ChatMessageDB.session_id == session_id)
            .order_by(ChatMessageDB.created_at, ChatMessageDB.id)
        )).scalars().all()
        return ChatSession(
            session_id=row.session_id,
            cv_key=row.cv_key,
            messages=[_to_message(m) for m in msg_rows],
            created_at=row.created_at,
            last_activity_at=row.last_activity_at,
        )

    # Thêm 1 tin nhắn vào DB, cập nhật mốc thời gian hoạt động của phiên
    async def append(self, db: AsyncSession, session_id: str, message: ChatMessage, *, commit: bool = True) -> None:
        exists = await db.scalar(
            select(ChatSessionDB.session_id).where(ChatSessionDB.session_id == session_id)
        )
        if exists is None:
            raise KeyError(session_id)

        db.add(ChatMessageDB(
            session_id=session_id,
            role=message.role,
            content=message.content,
            sources_json=(
                json.dumps([h.model_dump() for h in message.sources], ensure_ascii=False)
                if message.sources else None
            ),
        ))
        await db.execute(
            update(ChatSessionDB)
            .where(ChatSessionDB.session_id == session_id)
            .values(last_activity_at=func.now())
        )
        if commit:
            await db.commit()

    # Lưu cùng lúc cả tin nhắn user và bot vào DB
    async def append_pair(self, db: AsyncSession, session_id: str, user_msg: ChatMessage, assistant_msg: ChatMessage) -> None:
        await self.append(db, session_id, user_msg, commit=False)
        await self.append(db, session_id, assistant_msg, commit=False)
        await db.commit()

    # Lấy N tin nhắn mới nhất để llm đọc khi viết lại câu hỏi
    async def get_history(self, db: AsyncSession, session_id: str) -> list[ChatMessage]:
        rows = (await db.execute(
            select(ChatMessageDB)
            .where(ChatMessageDB.session_id == session_id)
            .order_by(desc(ChatMessageDB.created_at), desc(ChatMessageDB.id))
            .limit(self._history_last_n)
        )).scalars().all()
        return [_to_message(m) for m in reversed(rows)]

    # Xoá session chat
    async def delete(self, db: AsyncSession, session_id: str) -> bool:
        result = await db.execute(
            delete(ChatSessionDB).where(ChatSessionDB.session_id == session_id)
        )
        await db.commit()
        return result.rowcount > 0

    async def list_sessions(self, db: AsyncSession) -> list[ChatSession]:
        rows = (await db.execute(
            select(ChatSessionDB).order_by(desc(ChatSessionDB.last_activity_at))
        )).scalars().all()
        return [_to_session_metadata(r) for r in rows]


# Đổi 1 dòng DB sang Pydantic, không load các tin nhắn (load sau khi cần)
def _to_session_metadata(row: ChatSessionDB) -> ChatSession:
    return ChatSession(
        session_id=row.session_id,
        cv_key=row.cv_key,
        messages=[],
        created_at=row.created_at,
        last_activity_at=row.last_activity_at,
    )


def _to_message(row: ChatMessageDB) -> ChatMessage:
    sources: list[SearchHit] = []
    if row.sources_json:
        try:
            sources = [SearchHit(**d) for d in json.loads(row.sources_json)]
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            # Sources lỗi format không làm hỏng luồng chat, chỉ ghi log cảnh báo
            logger.warning("Bad sources_json msg_id=%d: %s", row.id, e)
    return ChatMessage(
        role=row.role,
        content=row.content,
        timestamp=row.created_at,
        sources=sources,
    )
