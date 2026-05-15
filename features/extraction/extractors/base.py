# Class cha của các extractor (PDF, DOCX...)
# Mỗi loại file con sẽ override "extract()" để đọc text từ file

import asyncio
from abc import ABC, abstractmethod


class BaseExtractor(ABC):
    # Hàm sync: đọc file và trả về text. Subclass phải implement
    @abstractmethod
    def extract(self, file_path: str) -> str: ...

    # Wrapper async: chạy "extract()" trong thread riêng để không block event loop
    async def extract_async(self, file_path: str) -> str:
        return await asyncio.to_thread(self.extract, file_path)
