# Shared schemas, Chunk = đoạn CV thành vector index, SearchHit = 1 kết quả search

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field

SectionType = Literal[
    "header", "summary", "skills", "education", "work_history",
    "projects", "awards", "certifications",
]


def to_int_or_none(v):
    """Ép value (chuỗi, float, None) về int, trả None nếu rỗng hoặc không parse được"""
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


YearsExp = Annotated[int | None, BeforeValidator(to_int_or_none)]


class Chunk(BaseModel):
    """1 đoạn CV sẵn sàng embed, meta gắn theo để Qdrant lọc nhanh"""
    cv_key: str
    section: SectionType
    text: str
    section_index: int = 0

    name: str | None = None
    years_exp: YearsExp = None
    skills: list[str] = Field(default_factory=list)


class SearchHit(BaseModel):
    cv_key: str
    section: SectionType
    chunk_text: str
    score: float = Field(..., description="Điểm giống nhau, 0-1 (sigmoid sau rerank)")
