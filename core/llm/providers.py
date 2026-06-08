# OpenAI-compatible LLM providers, tất cả share 1 class, khác nhau qua ProviderSpec
# Thêm provider mới = thêm 1 entry vào PROVIDERS registry


import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

from openai import AsyncOpenAI, RateLimitError as OpenAIRateLimitError

from core.config import GROQ_API_KEY, NVIDIA_API_KEY, ROUTER9_API_KEY

logger = logging.getLogger(__name__)

# Map tên biến env sang giá trị key, OpenAICompatProvider đọc key qua dict này
API_KEYS = {
    "GROQ_API_KEY": GROQ_API_KEY,
    "NVIDIA_API_KEY": NVIDIA_API_KEY,
    "ROUTER9_API_KEY": ROUTER9_API_KEY,
}


@dataclass(frozen=True)
class TokenUsage:
    prompt: int = 0
    completion: int = 0

    @property
    def total(self) -> int:
        """Tổng prompt + completion tokens"""
        return self.prompt + self.completion

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        """Cộng dồn token usage (immutable)"""
        return TokenUsage(self.prompt + other.prompt, self.completion + other.completion)


class RateLimitError(Exception):
    """Shared exception client.py catch để retry"""


@dataclass(frozen=True)
class StreamChunk:
    """1 event trong stream: delta text trong khi sinh, usage chỉ set ở chunk cuối"""
    delta: str = ""
    usage: TokenUsage | None = None


@dataclass(frozen=True)
class ProviderSpec:
    """Cấu hình per-provider, đăng ký trong PROVIDERS registry"""
    name: str
    api_key_env: str
    base_url: str
    default_model: str
    max_tokens_param: str = "max_tokens"
    default_temperature: float = 0.6
    default_max_tokens: int = 4096
    default_top_p: float = 0.95


PROVIDERS: dict[str, ProviderSpec] = {
    "groq": ProviderSpec(
        name="Groq",
        api_key_env="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1",
        default_model="meta-llama/llama-4-scout-17b-16e-instruct",
        max_tokens_param="max_completion_tokens",
    ),
    "nvidia": ProviderSpec(
        name="NVIDIA",
        api_key_env="NVIDIA_API_KEY",
        base_url="https://integrate.api.nvidia.com/v1",
        default_model="openai/gpt-oss-20b",
        default_temperature=1.0,
        default_max_tokens=4096,
        default_top_p=1.0,
    ),
    "9router": ProviderSpec(
        name="9Router",
        api_key_env="ROUTER9_API_KEY",
        base_url="http://localhost:20128/v1",
        default_model="llm",
    ),
}


class BaseProvider(ABC):
    name: str  # Set ở subclass / instance, dùng cho log

    def __init__(self, model: str, temperature: float, max_tokens: int):
        """Init params chung, subclass thêm SDK client"""
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def chat(self, system: str, user: str) -> tuple[str, TokenUsage]:
        """Template method, log + timing, subclass implement _call()"""
        logger.debug("Calling %s | model=%s | prompt_len=%d", self.name, self.model, len(user))
        t0 = time.perf_counter()
        raw, usage = await self._call(system, user)
        logger.info(
            "%s response in %.2fs | response_len=%d | tokens=p%d/c%d",
            self.name, time.perf_counter() - t0, len(raw), usage.prompt, usage.completion,
        )
        return raw, usage

    async def stream(self, system: str, user: str) -> AsyncIterator[StreamChunk]:
        """Streaming template, yield delta chunks, chunk cuối có usage"""
        logger.debug("Streaming %s | model=%s | prompt_len=%d", self.name, self.model, len(user))
        t0 = time.perf_counter()
        total_text_len = 0
        final_usage = TokenUsage()
        async for chunk in self._stream(system, user):
            total_text_len += len(chunk.delta)
            if chunk.usage is not None:
                final_usage = chunk.usage
            yield chunk
        logger.info(
            "%s stream done in %.2fs | response_len=%d | tokens=p%d/c%d",
            self.name, time.perf_counter() - t0, total_text_len,
            final_usage.prompt, final_usage.completion,
        )

    @abstractmethod
    async def _call(self, system: str, user: str) -> tuple[str, TokenUsage]:
        """Subclass gọi SDK, raise RateLimitError khi bị 429"""
        ...

    @abstractmethod
    def _stream(self, system: str, user: str) -> AsyncIterator[StreamChunk]:
        """Subclass gọi SDK streaming, raise RateLimitError khi bị 429"""
        ...


def _openai_chunk_to_event(chunk) -> StreamChunk | None:
    """OpenAI-shape chunk thành StreamChunk, trả None nếu không có delta lẫn usage"""
    delta = ""
    if getattr(chunk, "choices", None):
        d = chunk.choices[0].delta
        delta = getattr(d, "content", "") or ""
    usage = None
    u = getattr(chunk, "usage", None)
    if u is not None:
        usage = TokenUsage(
            prompt=getattr(u, "prompt_tokens", 0) or 0,
            completion=getattr(u, "completion_tokens", 0) or 0,
        )
    if not delta and usage is None:
        return None
    return StreamChunk(delta=delta, usage=usage)


class OpenAICompatProvider(BaseProvider):
    """Generic provider cho mọi endpoint OpenAI-compatible, config qua ProviderSpec"""

    def __init__(
        self,
        spec: ProviderSpec,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
    ):
        """API key + base URL đọc từ env theo spec, param không truyền thì lấy default từ spec"""
        self.name = spec.name
        self._spec = spec
        super().__init__(
            model or spec.default_model,
            spec.default_temperature if temperature is None else temperature,
            spec.default_max_tokens if max_tokens is None else max_tokens,
        )
        self.top_p = spec.default_top_p if top_p is None else top_p

        api_key = API_KEYS.get(spec.api_key_env, "")
        base_url = os.getenv(spec.api_key_env.replace("_API_KEY", "_BASE_URL"), spec.base_url)
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0)

    def _messages(self, system: str, user: str) -> list[dict]:
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _common_kwargs(self) -> dict:
        """Kwargs share giữa non-stream + stream, max_tokens_param khác nhau per spec"""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "top_p": self.top_p,
            self._spec.max_tokens_param: self.max_tokens,
        }

    async def _call(self, system: str, user: str) -> tuple[str, TokenUsage]:
        try:
            completion = await self.client.chat.completions.create(
                messages=self._messages(system, user),
                stream=False,
                **self._common_kwargs(),
            )
        except OpenAIRateLimitError as e:
            raise RateLimitError(str(e)) from e
        text = completion.choices[0].message.content or ""
        u = completion.usage
        usage = TokenUsage(
            prompt=getattr(u, "prompt_tokens", 0) or 0,
            completion=getattr(u, "completion_tokens", 0) or 0,
        )
        return text, usage

    async def _stream(self, system: str, user: str) -> AsyncIterator[StreamChunk]:
        try:
            stream = await self.client.chat.completions.create(
                messages=self._messages(system, user),
                stream=True,
                stream_options={"include_usage": True},
                **self._common_kwargs(),
            )
        except OpenAIRateLimitError as e:
            raise RateLimitError(str(e)) from e
        async for raw in stream:
            ev = _openai_chunk_to_event(raw)
            if ev is not None:
                yield ev
