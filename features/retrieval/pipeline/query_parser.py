# Tách filter (số năm, kỹ năng, vai trò) ra khỏi câu hỏi để Qdrant lọc nhanh

import re
from dataclasses import dataclass, field


# Bắt "5 năm", "5+ năm", "5 years", "5+ yrs experience",...
_YEARS_PATTERNS = [
    re.compile(r"(\d+)\s*\+?\s*(?:năm|years?|yrs?)", re.IGNORECASE),
]


# Danh sách kỹ năng cho phép, tránh nhầm lẫn (vd "Java" trong "JavaScript" hoặc tên người)
KNOWN_SKILLS = [
    # Languages
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Golang", "Rust", "C++", "C#",
    "Kotlin", "Swift", "Ruby", "PHP", "Scala", "R", "SQL",
    # Backend frameworks
    "FastAPI", "Django", "Flask", "Spring", "Spring Boot", "Express", "NestJS",
    ".NET", "Laravel", "Rails",
    # Frontend
    "React", "Vue", "Angular", "Next.js", "Nuxt",
    # Data / infra
    "Kafka", "RabbitMQ", "Redis", "PostgreSQL", "MySQL", "MongoDB", "ClickHouse",
    "Elasticsearch", "Spark", "PySpark", "Airflow", "Snowflake", "BigQuery", "Databricks",
    # DevOps / cloud
    "Docker", "Kubernetes", "K8s", "AWS", "GCP", "Azure", "Terraform", "Jenkins",
    # Mobile / game
    "Unity", "Unreal", "Flutter", "React Native",
    # ML
    "PyTorch", "TensorFlow", "Pandas", "NumPy",
]


# Map tên vai trò chuẩn sang các tên thay thế. CV mỗi nơi gọi khác nhau ("Senior SWE", "Tech Lead",...)
# nên dùng nhiều alias để bắt được nhiều biến thể
ROLE_ALIASES: dict[str, list[str]] = {
    "data engineer":   ["data engineer"],
    "data scientist":  ["data scientist"],
    "product manager": ["product manager", "product owner"],
    "engineer":        ["engineer", "developer", "dev", "swe", "programmer", "lập trình viên"],
    "manager":         ["manager", "lead", "head", "trưởng nhóm", "quản lý"],
    "architect":       ["architect", "kiến trúc sư"],
    "analyst":         ["analyst", "phân tích viên"],
    "designer":        ["designer", "thiết kế"],
    "tester":          ["tester", "qa", "kiểm thử"],
    "devops":          ["devops", "sre"],
}


# Tự xác định ranh giới từ để xử lý ký tự tiếng Việt và alias nhiều từ
def _compile_alias(alias: str) -> re.Pattern:
    return re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


# Sắp theo độ dài giảm dần để "data engineer" được match trước "engineer"
_ROLE_PATTERNS: dict[str, list[re.Pattern]] = {
    canonical: [_compile_alias(a) for a in sorted(aliases, key=len, reverse=True)]
    for canonical, aliases in ROLE_ALIASES.items()
}

_ALIAS_PATTERNS: list[tuple[str, re.Pattern]] = sorted(
    [(canonical, pat)
     for canonical, pats in _ROLE_PATTERNS.items()
     for pat in pats],
    key=lambda x: -len(x[1].pattern),
)


@dataclass
class ParsedQuery:
    text: str                                    # Câu hỏi gốc, vẫn dùng để biến thành vector
    min_years_exp: int | None = None
    required_skills: list[str] = field(default_factory=list)
    required_roles: list[str] = field(default_factory=list)


def parse_query(query: str) -> ParsedQuery:
    parsed = ParsedQuery(text=query)

    for pat in _YEARS_PATTERNS:
        m = pat.search(query)
        if m:
            parsed.min_years_exp = int(m.group(1))
            break

    # Sắp theo độ dài giảm dần để match "Spring Boot" trước "Spring"
    matched: list[str] = []
    for skill in sorted(KNOWN_SKILLS, key=len, reverse=True):
        # \b (word boundary) không hoạt động với "C++" / "C#" / ".NET" nên phải tự viết
        pattern = re.compile(
            r"(?<![A-Za-z0-9])" + re.escape(skill) + r"(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        if pattern.search(query) and skill not in matched:
            matched.append(skill)

    parsed.required_skills = matched

    roles: list[str] = []
    for canonical, pat in _ALIAS_PATTERNS:
        if canonical in roles:
            continue
        if pat.search(query):
            roles.append(canonical)
    parsed.required_roles = roles

    return parsed


# Trả True nếu text chứa bất kỳ tên thay thế nào của vai trò, dùng để ưu tiên kết quả
def text_matches_role(text: str, canonical_role: str) -> bool:
    patterns = _ROLE_PATTERNS.get(canonical_role)
    if not patterns:
        return False
    return any(p.search(text) for p in patterns)
