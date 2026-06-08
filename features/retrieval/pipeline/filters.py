# Tách filter (years/skills) ra khỏi câu hỏi cho Qdrant filter
# Skills lấy động từ SkillRegistry (chỉ skill đã từng xuất hiện trong DB)

import re
from dataclasses import dataclass, field

from core.registries import SkillRegistry


# Years patterns (vi + en),
#   min, "tối thiểu 5 năm", "trên 5 năm", "from 5 years", "at least 5 yrs", ">=5 năm"
#   max, "dưới 5 năm", "under 5 years", "less than 5 yrs", "<=5 năm"
#   plus, "5+ năm" thành min
#   bare, "5 năm" thì fallback coi là min
_MIN_YEARS_RE = re.compile(
    r"(?:tối thiểu|trên|từ|at\s+least|min(?:imum)?|from|over|>=?)\s*(\d+)\s*\+?\s*(?:năm|years?|yrs?)",
    re.IGNORECASE,
)
_MAX_YEARS_RE = re.compile(
    r"(?:dưới|under|less\s+than|max(?:imum)?|<=?)\s*(\d+)\s*(?:năm|years?|yrs?)",
    re.IGNORECASE,
)
_PLUS_YEARS_RE = re.compile(r"(\d+)\s*\+\s*(?:năm|years?|yrs?)", re.IGNORECASE)
_BARE_YEARS_RE = re.compile(r"(\d+)\s*(?:năm|years?|yrs?)", re.IGNORECASE)


@dataclass
class ParsedQuery:
    text: str                                       # Câu gốc, dùng để embed
    min_years_exp: int | None = None
    max_years_exp: int | None = None
    required_skills: list[str] = field(default_factory=list)


def _compile_skill(skill: str) -> re.Pattern:
    """Skill matcher với custom word boundary cho 'C++'/'C#'/'.NET'"""
    return re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(skill) + r"(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


def parse_query(query: str, skill_registry: SkillRegistry | None = None) -> ParsedQuery:
    """Extract years (min/max) + skills filter từ query"""
    parsed = ParsedQuery(text=query)

    m_min = _MIN_YEARS_RE.search(query)
    m_max = _MAX_YEARS_RE.search(query)
    m_plus = _PLUS_YEARS_RE.search(query)

    if m_min:
        parsed.min_years_exp = int(m_min.group(1))
    elif m_plus:
        parsed.min_years_exp = int(m_plus.group(1))

    if m_max:
        parsed.max_years_exp = int(m_max.group(1))

    # Không có marker rõ ràng nhưng có "N năm" thì coi là min
    if parsed.min_years_exp is None and parsed.max_years_exp is None and not m_plus:
        m_bare = _BARE_YEARS_RE.search(query)
        if m_bare:
            parsed.min_years_exp = int(m_bare.group(1))

    # Skills, registry đã sort giảm dần độ dài, match "Spring Boot" trước "Spring"
    known = skill_registry.all() if skill_registry else []
    matched: list[str] = []
    for skill in known:
        if skill in matched:
            continue
        if _compile_skill(skill).search(query):
            matched.append(skill)
    parsed.required_skills = matched

    return parsed
