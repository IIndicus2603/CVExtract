# Client hợp nhất: gọi LLM provider (Groq/Gemini/NVIDIA) để parse CV thành JSON.
# Provider/model truyền qua tham số khi gọi build_llm_client().

import asyncio
import datetime as _dt
import json
import logging
import re

from core.config import GEMINI_API_KEY, GROQ_API_KEY, NVIDIA_API_KEY
from features.parsing.llm.prompts import CV_EXTRACT_TEMPLATE, SYSTEM_PROMPT
from features.parsing.llm.providers import (
    BaseProvider,
    GeminiProvider,
    GroqProvider,
    NvidiaProvider,
    RateLimitError,
)

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(
        self,
        provider: BaseProvider,
        max_retries: int = 2,
        retry_backoff: float = 1.5,
    ):
        # max_retries=2 = 1 lần gọi chính + 1 lần retry
        self._provider = provider
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

    async def extract_cv(self, cv_text: str) -> dict:
        logger.info("Extracting CV | text_len=%d chars", len(cv_text))
        today = _dt.date.today().strftime("%Y-%m-%d")
        user_prompt = CV_EXTRACT_TEMPLATE.format(cv_text=cv_text, today=today)

        for attempt in range(1, self.max_retries + 1):
            try:
                raw = await self._provider.chat(SYSTEM_PROMPT, user_prompt)
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
                    return parsed
                logger.warning("Unparseable LLM response | attempt=%d/%d", attempt, self.max_retries)

            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_backoff * attempt)

        logger.error("Giving up after %d attempts", self.max_retries)
        return {}

    def _parse_json(self, raw: str) -> dict:
        # Bỏ khối <think>...</think>
        clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        # Bỏ markdown code fence "json ... "
        clean = re.sub(r"```json|```", "", clean).strip()

        try:
            return json.loads(clean)
        except json.JSONDecodeError as e:
            logger.warning("JSON parse error: %s | trying repair | raw: %r", e, clean[:500])

        repaired = self._repair_json(clean)
        if repaired != clean:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError as e:
                logger.error("JSON parse error after repair: %s | repaired: %r", e, repaired[:500])
                return {}

        logger.error("JSON repair made no change | raw: %r", clean[:500])
        return {}

    def _repair_json(self, s: str) -> str:
        # Trích đoạn từ '{' đầu tiên tới '}' cuối cùng
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end != -1 and end > start:
            s = s[start : end + 1]

        # Gộp chuỗi quote liên tiếp như: "Python,""" -> "Python,"
        s = re.sub(r'"{2,}', '"', s)
        # Bỏ dấu phẩy thừa trước ] hoặc }
        s = re.sub(r",(\s*[}\]])", r"\1", s)
        # Bỏ phần tử rỗng trong array do quote sai: ["a", , "b"] -> ["a", "b"]
        s = re.sub(r",\s*,", ",", s)

        return s.strip()


# Build client theo provider + model do caller chỉ định.
def build_llm_client(provider: str, model: str | None = None) -> LLMClient:
    name = (provider or "").lower().strip()
    kwargs = {"model": model} if model else {}

    if name == "nvidia":
        adapter = NvidiaProvider(api_key=NVIDIA_API_KEY, **kwargs)
    elif name == "groq":
        adapter = GroqProvider(api_key=GROQ_API_KEY, **kwargs)
    elif name == "gemini":
        adapter = GeminiProvider(api_key=GEMINI_API_KEY, **kwargs)
    else:
        raise ValueError(
            f"Unknown provider: {provider!r}. Expected: nvidia | groq | gemini"
        )

    logger.info("LLM client built | provider=%s | model=%s", name, adapter.model)
    return LLMClient(adapter, max_retries=2)
