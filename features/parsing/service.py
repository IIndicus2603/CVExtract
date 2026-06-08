# Parse CV text bằng LLM thành structured JSON, classify is_cv qua confidence threshold

import asyncio
import datetime as _dt
import logging

from core.config import CV_CONFIDENCE_THRESHOLD
from core.llm.client import build_llm_client
from core.llm.providers import TokenUsage

from features.parsing.llm.prompts import CV_EXTRACT_TEMPLATE, SYSTEM_PROMPT
from features.parsing.schemas import ParsedCV

logger = logging.getLogger(__name__)


NOT_A_CV_MESSAGE = "Document does not appear to be a CV"


class ParsingService:
    def __init__(self, provider: str, model: str | None = None):
        """Init LLM client theo provider config"""
        self._client = build_llm_client(provider=provider, model=model)

    async def parse(self, cv_text: str) -> tuple[dict, TokenUsage]:
        """Parse 1 CV text thành (parsed_dict, token usage)"""
        logger.info("Extracting CV | text_len=%d chars", len(cv_text))
        today = _dt.date.today().strftime("%Y-%m-%d")
        user_prompt = CV_EXTRACT_TEMPLATE.format(cv_text=cv_text, today=today)
        raw, usage = await self._client.extract_json(SYSTEM_PROMPT, user_prompt)
        return ParsedCV.normalize(raw), usage

    async def parse_many(self, cv_texts: list[str]) -> tuple[list[dict], TokenUsage]:
        """Parse song song, trả (list parsed, tổng token)"""
        results = await asyncio.gather(*[self.parse(t) for t in cv_texts])
        parsed_list = [r[0] for r in results]
        total_usage = TokenUsage()
        for _, u in results:
            total_usage = total_usage + u
        return parsed_list, total_usage

    @staticmethod
    def classify(parsed: dict) -> tuple[bool, dict]:
        """Dựa vào is_cv + confidence từ LLM, pop 2 field meta khỏi parsed"""
        if not parsed:
            # Empty parsed (LLM fail) thì coi success, caller fallback raw text
            return True, parsed
        is_cv = bool(parsed.pop("is_cv", False))
        confidence = float(parsed.pop("confidence", 0) or 0)
        return is_cv and confidence >= CV_CONFIDENCE_THRESHOLD, parsed
