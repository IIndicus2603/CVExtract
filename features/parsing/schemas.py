# Pydantic model cho parsing, chuẩn hoá output LLM về đúng shape

from typing import Annotated, Optional
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

from core.schemas import to_int_or_none


class ParsedCV(BaseModel):
    """Chuẩn hoá output LLM, field nào thiếu thì điền default"""
    model_config = ConfigDict(extra="ignore")

    is_cv: bool = False
    confidence: float = 0.0
    name: str = ""
    email: str = ""
    phone: str = ""
    years_exp: Annotated[Optional[int], BeforeValidator(to_int_or_none)] = None
    skills: list = Field(default_factory=list)
    education: list = Field(default_factory=list)
    work_history: list = Field(default_factory=list)
    projects: list = Field(default_factory=list)
    awards: list = Field(default_factory=list)
    certifications: list = Field(default_factory=list)
    summary: str = ""

    @classmethod
    def normalize(cls, raw: dict) -> dict:
        """Raw LLM dict thành dict sạch, giữ {} nếu rỗng, trả raw nếu lỗi"""
        if not raw:
            return {}
        try:
            return cls.model_validate(raw).model_dump()
        except ValidationError:
            return raw
