# Định nghĩa cấu trúc các bảng trong MySQL bằng SQLAlchemy ORM

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


# Bảng lưu CV:
class CVData(Base):
    __tablename__ = "cv_data"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # "key" dùng làm unique identifier (= tên file viết thường, không có đuôi)
    key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    extension: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))

    # Các cột thông tin trích xuất từ JSON LLM
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

    # JSON gốc do LLM trả về
    raw_json: Mapped[str] = mapped_column(LONGTEXT)
    error_message: Mapped[str | None] = mapped_column(LONGTEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# Bảng phiên chat; session_id = UUID4, cleanup task xoá theo last_activity_at + TTL
class ChatSessionDB(Base):
    __tablename__ = "chat_sessions"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cv_key: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


# Bảng message trong phiên chat; CASCADE xoá theo session
# sources_json: JSON string của list[SearchHit], NULL khi role=user hoặc refusal
class ChatMessageDB(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.session_id", ondelete="CASCADE"), index=True,
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(LONGTEXT)
    sources_json: Mapped[str | None] = mapped_column(LONGTEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
