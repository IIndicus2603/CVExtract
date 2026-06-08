# Request schema cho /Search/Semantic

from pydantic import BaseModel, Field


class SemanticSearchRequest(BaseModel):
    """top_k=None, trả tất cả CV đạt filter (unlimited, skip rerank)"""
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int | None = Field(default=None, ge=1)
