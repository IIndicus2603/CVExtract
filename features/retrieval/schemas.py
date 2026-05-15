# Các kiểu dữ liệu cho tính năng tìm kiếm CV theo ý nghĩa

from typing import Annotated, Literal
from pydantic import BaseModel, BeforeValidator, Field

SectionType = Literal[
    "header", "summary", "skills", "education", "work_history",
    "projects", "awards", "certifications",
]


# LLM thỉnh thoảng trả về float — ép về số nguyên để khớp với Qdrant
def _to_int(v):
    if v is None or v == "":
        return None
    return int(float(v))


YearsExp = Annotated[int | None, BeforeValidator(_to_int)]


# đoạn text nhỏ tách từ CV, sẵn sàng để biến thành vector số
class Chunk(BaseModel):
    cv_key: str
    section: SectionType
    text: str
    section_index: int = 0

    # Gắn kèm thông tin chính của CV vào mỗi đoạn để Qdrant lọc nhanh khi tìm kiếm
    name: str | None = None
    years_exp: YearsExp = None
    skills: list[str] = Field(default_factory=list)


# kết quả tìm kiếm trả về cho user
class SearchHit(BaseModel):
    cv_key: str
    section: SectionType
    chunk_text: str
    score: float = Field(..., description="Điểm giống nhau, 0-1")


# Dữ liệu user gửi lên khi tìm kiếm theo ý nghĩa (POST /Search/Semantic)
class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
