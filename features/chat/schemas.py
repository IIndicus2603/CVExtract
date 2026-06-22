# Schemas cho chat layer

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from core.schemas import SearchHit


def utc_naive() -> datetime:
    """UTC hiện tại dạng naive (bỏ tzinfo) để khớp với UTC_TIMESTAMP() của DB"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ChatMessage(BaseModel):
    """1 tin nhắn, sources rỗng nếu role=user hoặc refusal"""
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime = Field(default_factory=utc_naive)
    sources: list[SearchHit] = Field(default_factory=list)


class ChatSession(BaseModel):
    """1 phiên chat 1-1 với 1 CV"""
    session_id: str
    cv_key: str
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_naive)
    last_activity_at: datetime = Field(default_factory=utc_naive)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    message: str
    sources: list[SearchHit] = Field(default_factory=list)


class CreateSessionRequest(BaseModel):
    cv_key: str = Field(..., min_length=1, max_length=255)


class CreateSessionResponse(BaseModel):
    session_id: str
    cv_key: str
