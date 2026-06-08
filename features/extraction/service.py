# CV text extraction từ .pdf / .docx

import logging
import time
from pathlib import Path

from core.config import CV_RAW_TEXT_DIR
from features.extraction.schemas import CVResult, CVStatus
from features.extraction.extractors.factory import EXTRACTOR_MAP

logger = logging.getLogger(__name__)


class CVExtractorService:
    def __init__(self):
        """Map extension sang extractor instance (factory)"""
        self._extractors = EXTRACTOR_MAP

    def supports(self, ext: str) -> bool:
        """True nếu extension có extractor (.pdf, .docx)"""
        return ext in self._extractors

    async def extract_file(self, file, ext: str) -> CVResult:
        """Extract từ UploadFile, bắt mọi exception thành CVResult(ERROR) cho batch resilient"""
        common = dict(file_name=file.filename, extension=ext)
        fname = common["file_name"]
        try:
            t0 = time.perf_counter()
            text = await self._extractors[ext].extract_async(file.file)
            elapsed = time.perf_counter() - t0

            # PDF chỉ có ảnh / file rỗng thì coi là lỗi
            if not text.strip():
                logger.warning("No text content extracted from '%s'", fname)
                return CVResult(**common, status=CVStatus.ERROR,
                                error_message="No text content extracted (file may be empty or image-only)")

            self._dump_raw_text(fname, text)
            logger.info("Extracted '%s' in %.2fs (%d chars)", fname, elapsed, len(text))
            return CVResult(**common, status=CVStatus.SUCCESS, text=text)

        except Exception as exc:
            logger.error("Failed to extract '%s': %s", fname, exc)
            return CVResult(**common, status=CVStatus.ERROR, error_message=str(exc))

    @staticmethod
    def _dump_raw_text(file_name: str, text: str) -> None:
        """Lưu raw text ra CV_RAW_TEXT_DIR/{stem}.txt, lỗi I/O không fail request"""
        if not CV_RAW_TEXT_DIR:
            return
        try:
            out_dir = Path(CV_RAW_TEXT_DIR)
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = Path(file_name).stem
            (out_dir / f"{stem}.txt").write_text(text, encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to dump raw text for '%s': %s", file_name, exc)
