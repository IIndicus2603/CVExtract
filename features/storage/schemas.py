# Pydantic models cho feature storage.

from typing import Optional
from pydantic import BaseModel


# Dữ liệu cần lưu xuống DB
class CVSaveData(BaseModel):
    key: str            # Tên file viết thường, không có đuôi (làm unique key)
    file_name: str
    extension: str
    status: str
    text: str = ""      # JSON đã parse hoặc text gốc
    error_message: Optional[str] = None


# Cấu trúc 1 CV khi đọc ra từ DB
class CVItem(BaseModel):
    file_name: str
    extension: str
    status: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    years_exp: Optional[int] = None
    skills: Optional[list] = None
    education: Optional[str] = None
    work_history: Optional[list] = None
    summary: Optional[str] = None
    text: str = ""
    error_message: Optional[str] = None
