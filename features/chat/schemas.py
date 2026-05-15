# Các kiểu dữ liệu cho tính năng chat

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from features.retrieval.schemas import SearchHit


# 1 tin nhắn trong phiên chat; bot trả lời thì kèm sources
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    sources: list[SearchHit] = Field(default_factory=list)


# 1 phiên chat gắn cố định với 1 CV (1 ứng viên)
class ChatSession(BaseModel):
    session_id: str
    cv_key: str
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity_at: datetime = Field(default_factory=datetime.utcnow)


# Dữ liệu user gửi lên khi chat (POST /Chat/Sessions/{id}/Messages)
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


# Dữ liệu trả về sau khi bot trả lời (non streaming)
class ChatResponse(BaseModel):
    message: str
    sources: list[SearchHit] = Field(default_factory=list)


# Dữ liệu user gửi lên khi tạo phiên chat mới (POST /Chat/Sessions)
class CreateSessionRequest(BaseModel):
    cv_key: str = Field(..., min_length=1, max_length=255)


# Dữ liệu trả về sau khi tạo phiên chat
class CreateSessionResponse(BaseModel):
    session_id: str
    cv_key: str
