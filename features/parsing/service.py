# Service parse CV: bọc LLMClient để trừu tượng hóa logic gọi LLM
# Hỗ trợ parse 1 CV hoặc parse nhiều CV song song

import asyncio
import logging

from features.parsing.llm.client import build_llm_client

logger = logging.getLogger(__name__)


class ParsingService:
    def __init__(self, provider: str, model: str | None = None):
        self._client = build_llm_client(provider=provider, model=model)

    # Parse 1 CV text sang dict (tên, email, skills...)
    async def parse(self, cv_text: str) -> dict:
        return await self._client.extract_cv(cv_text)

    # Parse nhiều CV cùng lúc (chạy song song bằng asyncio.gather)
    async def parse_many(self, cv_texts: list[str]) -> list[dict]:
        return list(await asyncio.gather(*[self._client.extract_cv(t) for t in cv_texts]))
