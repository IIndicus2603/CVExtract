# In-memory registries cho query filter,
#  - NameRegistry, ánh xạ cv_key với tên ứng viên (bỏ dấu, tokenize)
#  - SkillRegistry, known-skills list (cho parser regex match)

import asyncio
import logging
import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import CVData

logger = logging.getLogger(__name__)


def _tokenize(s: str) -> list[str]:
    """Lowercase + strip dấu + split, drop token < 2 ký tự"""
    if not s:
        return []
    nfd = unicodedata.normalize("NFD", s)
    stripped = "".join(c for c in nfd if not unicodedata.combining(c))
    lowered = stripped.lower()
    return [t for t in lowered.replace(",", " ").replace(".", " ").split() if len(t) >= 2]


class NameRegistry:
    def __init__(self):
        """Init in-memory map + reverse token index"""
        self._map: dict[str, list[str]] = {}        # cv_key ánh xạ sang tokens tên
        self._tokens: dict[str, set[str]] = {}      # token ánh xạ sang set cv_key
        self._lock = asyncio.Lock()

    async def load_from_db(self, db: AsyncSession) -> None:
        """Build registry từ tất cả CVData.name trong DB"""
        rows = (await db.execute(
            select(CVData.key, CVData.name).where(CVData.name.is_not(None))
        )).all()
        async with self._lock:
            self._map.clear()
            self._tokens.clear()
            for key, name in rows:
                self._add_unlocked(key, name)
        logger.info("NameRegistry loaded: %d names, %d unique tokens", len(self._map), len(self._tokens))

    async def add(self, cv_key: str, name: str | None) -> None:
        """Add/replace tên cho cv_key (xoá entry cũ nếu có)"""
        async with self._lock:
            self._remove_unlocked(cv_key)
            self._add_unlocked(cv_key, name)

    async def remove(self, cv_key: str) -> None:
        """Xoá cv_key khỏi registry (no-op nếu không tồn tại)"""
        async with self._lock:
            self._remove_unlocked(cv_key)

    def match(self, query: str) -> list[str]:
        """Trả cv_keys mà MỌI token tên đều xuất hiện trong query"""
        q_tokens = set(_tokenize(query))
        if not q_tokens:
            return []
        return [
            cv_key for cv_key, name_tokens in self._map.items()
            if name_tokens and all(t in q_tokens for t in name_tokens)
        ]

    def _add_unlocked(self, cv_key: str, name: str | None) -> None:
        """Internal add (caller phải giữ lock)"""
        tokens = _tokenize(name or "")
        if not tokens:
            return
        self._map[cv_key] = tokens
        for t in set(tokens):
            self._tokens.setdefault(t, set()).add(cv_key)

    def _remove_unlocked(self, cv_key: str) -> None:
        """Internal remove (caller phải giữ lock)"""
        tokens = self._map.pop(cv_key, None)
        if not tokens:
            return
        for t in set(tokens):
            bucket = self._tokens.get(t)
            if bucket is None:
                continue
            bucket.discard(cv_key)
            if not bucket:
                del self._tokens[t]


class SkillRegistry:
    def __init__(self):
        """Init in-memory canonical-case skill map"""
        self._canonical: dict[str, str] = {}  # lowered ánh xạ sang casing đầu tiên thấy
        self._lock = asyncio.Lock()

    async def load_from_db(self, db: AsyncSession) -> None:
        """Build registry từ tất cả CVData.skills trong DB"""
        rows = (await db.execute(
            select(CVData.skills).where(CVData.skills.is_not(None))
        )).scalars().all()
        async with self._lock:
            self._canonical.clear()
            for skills in rows:
                self._merge_unlocked(skills)
        logger.info("SkillRegistry loaded: %d unique skills", len(self._canonical))

    async def add(self, skills: list[str] | None) -> None:
        """Merge skills mới (case-insensitive dedup)"""
        if not skills:
            return
        async with self._lock:
            self._merge_unlocked(skills)

    def all(self) -> list[str]:
        """Sort giảm dần độ dài để regex match 'Spring Boot' trước 'Spring'"""
        return sorted(self._canonical.values(), key=len, reverse=True)

    def _merge_unlocked(self, skills) -> None:
        """Internal merge (caller phải giữ lock)"""
        if not isinstance(skills, list):
            return
        for s in skills:
            if not isinstance(s, str):
                continue
            s = s.strip()
            if not s:
                continue
            self._canonical.setdefault(s.lower(), s)
