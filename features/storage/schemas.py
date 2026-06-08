# Pydantic models cho feature storage

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
