# Schemas cho JD và CV matching

from typing import Any

from pydantic import BaseModel, Field


class JDMatchRequest(BaseModel):
    jd_text: str = Field(..., min_length=10, max_length=20000)
    top_k: int = Field(default=5, ge=1, le=50)
    # Hard filter trên Qdrant (years/skills), False thì chỉ ranking
    strict_skills_filter: bool = False
    strict_years_filter: bool = True


class ParsedJD(BaseModel):
    """JD đã parse bởi LLM (hoặc fallback raw text)"""
    summary: str = ""
    required_skills: list[str] = Field(default_factory=list)
    min_years_exp: int | None = None
    max_years_exp: int | None = None


class CVMatch(BaseModel):
    cv_key: str
    cv: dict[str, Any]
    score: float = Field(..., ge=0.0, le=1.0, description="Điểm aggregated 0..1")
    matched_chunks: list[dict[str, Any]] = Field(default_factory=list)


class MatchResponse(BaseModel):
    parsed_jd: ParsedJD
    total_cvs: int
    results: list[CVMatch]
