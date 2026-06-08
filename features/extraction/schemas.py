# Pydantic models dùng cho feature extraction

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# Trạng thái của 1 lần extract, thành công hay lỗi
class CVStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


# Kết quả của 1 lần extract 1 file CV
class CVResult(BaseModel):
    file_name: str = Field(..., description="Tên file CV")
    extension: str = Field(..., description="Phần mở rộng của file (.pdf, .docx)")
    status: CVStatus = Field(..., description="Trạng thái trích xuất")
    text: str = Field(default="", description="Nội dung văn bản đã trích xuất")
    error_message: Optional[str] = Field(default=None, description="Thông báo lỗi nếu có")
