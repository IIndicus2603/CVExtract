# Base class cho các extractor (PDF, DOCX, ...)

import asyncio
from abc import ABC, abstractmethod


class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, file_path: str) -> str:
        """Đọc file (sync) thành text, subclass phải implement"""
        ...

    async def extract_async(self, file_path: str) -> str:
        """Async wrapper chạy extract() trong thread riêng để không block event loop"""
        return await asyncio.to_thread(self.extract, file_path)
