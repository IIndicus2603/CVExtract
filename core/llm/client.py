# LLM client dùng chung (parsing CV + matching JD)
# Caller format prompt, client lo retry + parse JSON + sum token usage

import asyncio
import json
import logging
import re
from typing import AsyncIterator

from core.llm.providers import (
    PROVIDERS,
    BaseProvider,
    OpenAICompatProvider,
    RateLimitError,
    StreamChunk,
    TokenUsage,
)

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(
        self,
        provider: BaseProvider,
        max_retries: int = 2,
        retry_backoff: float = 1.5,
    ):
        """max_retries=2 = 1 lần chính + 1 retry"""
        self._provider = provider
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

    async def chat_text(self, system_prompt: str, user_prompt: str) -> tuple[str, TokenUsage]:
        """Gọi LLM, trả raw text + usage, không parse JSON, không retry parse"""
        try:
            return await self._provider.chat(system_prompt, user_prompt)
        except RateLimitError:
            logger.warning("Rate limited (429) on chat_text | giving up")
            return "", TokenUsage()

    async def stream_text(
        self, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[StreamChunk]:
        """Stream LLM response, yield StreamChunk, chunk cuối có usage"""
        try:
            async for ev in self._provider.stream(system_prompt, user_prompt):
                yield ev
        except RateLimitError:
            logger.warning("Rate limited (429) on stream_text | giving up")
            return

    async def extract_json(self, system_prompt: str, user_prompt: str) -> tuple[dict, TokenUsage]:
        """Gọi LLM + parse JSON với retry, trả ({}, usage) nếu thất bại hết"""
        total = TokenUsage()
        for attempt in range(1, self.max_retries + 1):
            try:
                raw, usage = await self._provider.chat(system_prompt, user_prompt)
                total = total + usage
            except RateLimitError:
                logger.warning(
                    "Rate limited (429) | attempt=%d/%d | sleeping 60s",
                    attempt, self.max_retries,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(60.0)
                continue

            if not raw.strip():
                logger.warning("Empty LLM response | attempt=%d/%d", attempt, self.max_retries)
            else:
                parsed = self._parse_json(raw)
                if parsed:
                    return parsed, total
                logger.warning("Unparseable LLM response | attempt=%d/%d", attempt, self.max_retries)

            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_backoff * attempt)

        logger.error("Giving up after %d attempts", self.max_retries)
        return {}, total

    def _parse_json(self, raw: str) -> dict:
        """Strip think/fence, parse, nếu fail thử repair, trả {} nếu hết cách"""
        clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        clean = re.sub(r"```json|```", "", clean).strip()

        try:
            # strict=False để chấp nhận control char (xuống dòng thô) trong string value
            return json.loads(clean, strict=False)
        except json.JSONDecodeError as e:
            logger.warning("JSON parse error: %s | trying repair | raw: %r", e, clean[:500])

        repaired = self._repair_json(clean)
        if repaired != clean:
            try:
                return json.loads(repaired, strict=False)
            except json.JSONDecodeError as e:
                logger.error("JSON parse error after repair: %s | repaired: %r", e, repaired[:500])
                return {}

        logger.error("JSON repair made no change | raw: %r", clean[:500])
        return {}

    def _repair_json(self, s: str) -> str:
        """Trích {...} đầu-cuối, fix trailing comma, gộp quote liên tiếp"""
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end != -1 and end > start:
            s = s[start : end + 1]

        # Gộp quote liên tiếp ("Python,""") + bỏ comma thừa + bỏ empty array element
        s = re.sub(r'"{2,}', '"', s)
        s = re.sub(r",(\s*[}\]])", r"\1", s)
        s = re.sub(r",\s*,", ",", s)

        return s.strip()


def build_llm_client(provider: str, model: str | None = None) -> LLMClient:
    """Build client theo provider name + optional model"""
    name = (provider or "").lower().strip()
    spec = PROVIDERS.get(name)
    if spec is None:
        raise ValueError(
            f"Unknown provider: {provider!r}. Expected one of: {', '.join(PROVIDERS)}"
        )
    adapter = OpenAICompatProvider(spec, model=model)
    logger.info("LLM client built | provider=%s | model=%s", name, adapter.model)
    return LLMClient(adapter, max_retries=2)
