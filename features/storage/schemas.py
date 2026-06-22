# Pydantic models cho feature storage

from typing import Optional
from pydantic import BaseModel, Field


class CVSaveData(BaseModel):
    """Dữ liệu cần lưu xuống DB"""
    key: str = Field(..., description="Tên file viết thường, không có đuôi (làm unique key)")
    file_name: str
    extension: str
    status: str
    text: str = Field(default="", description="JSON đã parse hoặc text gốc")
    error_message: Optional[str] = None
