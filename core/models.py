# SQLAlchemy ORM models cho MySQL

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


# Ép MySQL trả UTC, đồng bộ với Python datetime.now
_UTC_NOW = text("UTC_TIMESTAMP()")


class CVData(Base):
    """1 CV (extracted + parsed), key = filename lowercase, no extension"""
    __tablename__ = "cv_data"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    extension: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))

    # Structured fields extract từ LLM JSON
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    years_exp: Mapped[int | None] = mapped_column(nullable=True)
    skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    education: Mapped[list | None] = mapped_column(JSON, nullable=True)
    work_history: Mapped[list | None] = mapped_column(JSON, nullable=True)
    projects: Mapped[list | None] = mapped_column(JSON, nullable=True)
    awards: Mapped[list | None] = mapped_column(JSON, nullable=True)
    certifications: Mapped[list | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    error_message: Mapped[str | None] = mapped_column(LONGTEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=_UTC_NOW)


class ChatSessionDB(Base):
    """1 phiên chat gắn với 1 CV, cleanup task xoá theo last_activity_at + TTL"""
    __tablename__ = "chat_sessions"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cv_key: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=_UTC_NOW)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=_UTC_NOW, onupdate=_UTC_NOW,
    )


class ChatMessageDB(Base):
    """Message trong phiên chat, sources_json NULL khi role=user hoặc refusal"""
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.session_id", ondelete="CASCADE"), index=True,
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(LONGTEXT)
    sources_json: Mapped[str | None] = mapped_column(LONGTEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=_UTC_NOW)
