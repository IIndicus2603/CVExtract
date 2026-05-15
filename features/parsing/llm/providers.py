# Adapter cho từng LLM provider. Mỗi class chỉ implement _call() trả raw text.
# RateLimitError (429) được bubble lên để client.py bắt và retry.

import logging
import time
from abc import ABC, abstractmethod

from google import genai
from google.genai import types
from google.genai import errors as genai_errors
from groq import AsyncGroq
from groq import RateLimitError as GroqRateLimitError
from openai import AsyncOpenAI, RateLimitError as OpenAIRateLimitError

logger = logging.getLogger(__name__)


# Exception chung mà client.py bắt để biết khi nào cần retry vì rate limit
class RateLimitError(Exception):
    pass


class BaseProvider(ABC):
    name: str  # Tên provider hiển thị trong log, set ở subclass

    def __init__(self, model: str, temperature: float, max_tokens: int):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    # Template method: log + timing + giữ logic chung. Subclass chỉ implement _call().
    async def chat(self, system: str, user: str) -> str:
        logger.debug("Calling %s | model=%s | prompt_len=%d", self.name, self.model, len(user))
        t0 = time.perf_counter()
        raw = await self._call(system, user)
        logger.info(
            "%s response in %.2fs | response_len=%d",
            self.name, time.perf_counter() - t0, len(raw),
        )
        return raw

    # Subclass gọi SDK provider, raise RateLimitError nếu bị 429
    @abstractmethod
    async def _call(self, system: str, user: str) -> str: ...


class GroqProvider(BaseProvider):
    name = "Groq"

    def __init__(
        self,
        api_key: str,
        model: str = "meta-llama/llama-4-scout-17b-16e-instruct",
        temperature: float = 0.6,
        max_tokens: int = 1500,
    ):
        super().__init__(model, temperature, max_tokens)
        self.client = AsyncGroq(api_key=api_key)

    async def _call(self, system: str, user: str) -> str:
        try:
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.temperature,
                max_completion_tokens=self.max_tokens,
                top_p=0.95,
                stream=False,
                stop=None,
            )
        except GroqRateLimitError as e:
            raise RateLimitError(str(e)) from e
        return completion.choices[0].message.content or ""


class GeminiProvider(BaseProvider):
    name = "Gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-flash-lite-latest",
        temperature: float = 0.6,
        max_tokens: int = 1500,
    ):
        super().__init__(model, temperature, max_tokens)
        self.client = genai.Client(api_key=api_key)

    async def _call(self, system: str, user: str) -> str:
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                    top_p=0.95,
                    response_mime_type="application/json",
                ),
            )
        except genai_errors.ClientError as e:
            # Gemini gói 429 vào ClientError với code=429
            if getattr(e, "code", None) == 429:
                raise RateLimitError(str(e)) from e
            raise
        return response.text or ""


class NvidiaProvider(BaseProvider):
    name = "NVIDIA"

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-20b",
        temperature: float = 1.0,
        max_tokens: int = 4096,
        top_p: float = 1.0,
        base_url: str = "https://integrate.api.nvidia.com/v1",
    ):
        super().__init__(model, temperature, max_tokens)
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0)
        self.top_p = top_p

    async def _call(self, system: str, user: str) -> str:
        try:
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens,
                stream=False,
            )
        except OpenAIRateLimitError as e:
            raise RateLimitError(str(e)) from e
        return completion.choices[0].message.content or ""
