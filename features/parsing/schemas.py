# Pydantic models cho feature parsing.

from typing import Optional
from pydantic import BaseModel, Field


class ParseRequest(BaseModel):
    text: str


# dòng kinh nghiệm làm việc trong CV
class WorkEntry(BaseModel):
    role: str = ""
    company: str = ""
    duration: str = ""
    description: str = ""  # Trách nhiệm chính + tech stack


# bằng cấp trong CV
class EducationEntry(BaseModel):
    degree: str = ""
    school: str = ""
    duration: str = ""


# dự án trong CV
class ProjectEntry(BaseModel):
    name: str = ""
    description: str = ""  # Mục tiêu, vai trò, tech stack
    tech: list[str] = Field(default_factory=list)
    duration: str = ""
    url: str = ""


# giải thưởng
class AwardEntry(BaseModel):
    name: str = ""
    issuer: str = ""
    year: str = ""
    description: str = ""


# chứng chỉ nghề nghiệp
class CertificationEntry(BaseModel):
    name: str = ""
    issuer: str = ""
    year: str = ""


# Cấu trúc CV sau khi LLM parse xong
class ParsedCV(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    years_exp: Optional[int] = None
    skills: list[str] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    work_history: list[WorkEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    awards: list[AwardEntry] = Field(default_factory=list)
    certifications: list[CertificationEntry] = Field(default_factory=list)
    summary: str = ""
