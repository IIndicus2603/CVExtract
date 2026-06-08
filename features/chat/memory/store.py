# DB-backed chat session store + cleanup task xoá phiên quá hạn

import asyncio
import json
import logging
import uuid
from datetime import timedelta

from sqlalchemy import delete, desc, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import CHAT_SESSION_TTL_HOURS
from core.database import AsyncSessionLocal
from core.models import ChatMessageDB, ChatSessionDB
from core.schemas import SearchHit
from features.chat.schemas import ChatMessage, ChatSession, utc_naive

logger = logging.getLogger(__name__)


async def cleanup_expired_sessions_loop():
    """Mỗi 1h xoá phiên có last_activity_at < utc_now - TTL, DB lưu UTC qua UTC_TIMESTAMP() nên so naive-UTC với naive-UTC, CASCADE xoá luôn messages"""
    while True:
        try:
            await asyncio.sleep(3600)
            async with AsyncSessionLocal() as db:
                cutoff = utc_naive() - timedelta(hours=CHAT_SESSION_TTL_HOURS)
                result = await db.execute(
                    delete(ChatSessionDB).where(ChatSessionDB.last_activity_at < cutoff)
                )
                await db.commit()
                logger.info(
                    "Chat cleanup: deleted %d expired sessions (cutoff=%s UTC)",
                    result.rowcount, cutoff.isoformat(),
                )
        except asyncio.CancelledError:
            logger.info("Chat cleanup task stopped")
            break
        except Exception as e:
            logger.error("Chat cleanup error: %s", e)


class SessionStore:
    def __init__(self, history_last_n: int = 10):
        """history_last_n, N message cuối load vào condense prompt"""
        self._history_last_n = history_last_n

    async def create(self, db: AsyncSession, cv_key: str) -> ChatSession:
        """Tạo session mới UUID4 gắn với 1 CV"""
        row = ChatSessionDB(session_id=str(uuid.uuid4()), cv_key=cv_key)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        logger.debug("Created session %s for cv_key=%s", row.session_id, cv_key)
        return _to_session_metadata(row)

    async def get(self, db: AsyncSession, session_id: str) -> ChatSession | None:
        """Lấy info session (không messages), None nếu không tồn tại"""
        row = await db.scalar(
            select(ChatSessionDB).where(ChatSessionDB.session_id == session_id)
        )
        return _to_session_metadata(row) if row else None

    async def get_with_messages(self, db: AsyncSession, session_id: str) -> ChatSession | None:
        """Lấy session kèm toàn bộ messages, sort theo created_at"""
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

    async def append(self, db: AsyncSession, session_id: str, message: ChatMessage, *, commit: bool = True) -> None:
        """Append 1 message + touch last_activity_at"""
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
            .values(last_activity_at=text("UTC_TIMESTAMP()"))
        )
        if commit:
            await db.commit()

    async def append_pair(self, db: AsyncSession, session_id: str, user_msg: ChatMessage, assistant_msg: ChatMessage) -> None:
        """Lưu user + assistant message trong 1 transaction"""
        await self.append(db, session_id, user_msg, commit=False)
        await self.append(db, session_id, assistant_msg, commit=False)
        await db.commit()

    async def get_history(self, db: AsyncSession, session_id: str) -> list[ChatMessage]:
        """N message mới nhất, return theo thứ tự tăng dần"""
        rows = (await db.execute(
            select(ChatMessageDB)
            .where(ChatMessageDB.session_id == session_id)
            .order_by(desc(ChatMessageDB.created_at), desc(ChatMessageDB.id))
            .limit(self._history_last_n)
        )).scalars().all()
        return [_to_message(m) for m in reversed(rows)]

    async def delete(self, db: AsyncSession, session_id: str) -> bool:
        """Xoá session + CASCADE xoá messages, trả False nếu không có"""
        result = await db.execute(
            delete(ChatSessionDB).where(ChatSessionDB.session_id == session_id)
        )
        await db.commit()
        return result.rowcount > 0


def _to_session_metadata(row: ChatSessionDB) -> ChatSession:
    """ORM row thành Pydantic, không load messages"""
    return ChatSession(
        session_id=row.session_id,
        cv_key=row.cv_key,
        messages=[],
        created_at=row.created_at,
        last_activity_at=row.last_activity_at,
    )


def _to_message(row: ChatMessageDB) -> ChatMessage:
    """ORM row thành Pydantic, parse sources_json, lỗi format không hỏng chat"""
    sources: list[SearchHit] = []
    if row.sources_json:
        try:
            sources = [SearchHit(**d) for d in json.loads(row.sources_json)]
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            # Sources lỗi format không hỏng luồng chat
            logger.warning("Bad sources_json msg_id=%d: %s", row.id, e)
    return ChatMessage(
        role=row.role,
        content=row.content,
        timestamp=row.created_at,
        sources=sources,
    )
