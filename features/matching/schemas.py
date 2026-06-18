# Schemas cho JD và CV matching

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


def _to_score(v) -> float:
    """Ép value LLM về float 0..1, clamp ngoài khoảng, trả 0.0 nếu không parse được"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if f < 0.0 else 1.0 if f > 1.0 else f


class JDMatchRequest(BaseModel):
    jd_text: str = Field(..., min_length=10, max_length=20000)
    top_k: int = Field(default=5, ge=1, le=50)
    # Hard filter trên Qdrant (years/skills), False thì chỉ ranking
    strict_skills_filter: bool = False
    strict_years_filter: bool = True
    llm_evaluate: bool = False  # Bật thì chấm điểm và re-rank bằng LLM


class ParsedJD(BaseModel):
    """JD đã parse bởi LLM (hoặc fallback raw text)"""
    summary: str = ""
    required_skills: list[str] = Field(default_factory=list)
    min_years_exp: int | None = None
    max_years_exp: int | None = None


class LLMEvaluation(BaseModel):
    """Kết quả LLM chấm độ phù hợp 1 CV với JD, chuẩn hoá từ raw dict"""
    model_config = ConfigDict(extra="ignore")

    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Điểm phù hợp LLM 0..1")
    recommendation: str = ""
    reasoning: str = ""
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    experience_fit: str = ""
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)

    @classmethod
    def normalize(cls, raw: dict) -> "LLMEvaluation | None":
        """Raw LLM dict thành LLMEvaluation sạch, trả None nếu rỗng hoặc lỗi"""
        if not raw:
            return None
        try:
            return cls(
                score=_to_score(raw.get("score")),
                recommendation=str(raw.get("recommendation") or "")[:100],
                reasoning=str(raw.get("reasoning") or ""),
                matched_skills=[s for s in (raw.get("matched_skills") or []) if isinstance(s, str)],
                missing_skills=[s for s in (raw.get("missing_skills") or []) if isinstance(s, str)],
                experience_fit=str(raw.get("experience_fit") or ""),
                strengths=[s for s in (raw.get("strengths") or []) if isinstance(s, str)],
                concerns=[s for s in (raw.get("concerns") or []) if isinstance(s, str)],
            )
        except ValidationError:
            return None


class CVMatch(BaseModel):
    cv_key: str
    cv: dict[str, Any]
    score: float = Field(..., ge=0.0, le=1.0, description="Điểm aggregated 0..1")
    matched_chunks: list[dict[str, Any]] = Field(default_factory=list)
    llm_evaluation: "LLMEvaluation | None" = None  # None nếu llm_evaluate tắt hoặc eval thất bại


class MatchResponse(BaseModel):
    parsed_jd: ParsedJD
    total_cvs: int
    results: list[CVMatch]
