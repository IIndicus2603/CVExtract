# Service trích xuất text từ file CV (.pdf, .docx).

import asyncio
import glob
import logging
import os
import time

from features.extraction.schemas import CVResult, CVStatus
from features.extraction.extractors.factory import EXTRACTOR_MAP, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)


class CVExtractorService:
    def __init__(self):
        # Map ".pdf"/".docx" 
        self._extractors = EXTRACTOR_MAP

    # Kiểm tra extension có được hỗ trợ không
    def supports(self, ext: str) -> bool:
        return ext in self._extractors

    # Quét folder, trả về danh sách file .pdf/.docx
    def _scan_files(self, folder_path: str) -> list[str]:
        pattern = os.path.join(folder_path, "**", "*")
        all_files = [f for f in glob.glob(pattern, recursive=True) if os.path.isfile(f)]

        # Tách 2 nhóm: file hỗ trợ và file bỏ qua
        supported, skipped = [], []
        for f in all_files:
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS:
                supported.append(f)
            else:
                skipped.append(f)

        if skipped:
            logger.warning("Skipped %d unsupported file(s): %s", len(skipped), [os.path.basename(f) for f in skipped])

        logger.info("Found %d supported file(s) to process", len(supported))
        return sorted(supported)

    # Extract từ UploadFile
    async def extract_file(self, file, ext: str) -> CVResult:
        common = dict(file_name=file.filename, extension=ext)
        fname = common["file_name"]
        try:
            # Đo thời gian extract để log performance
            t0 = time.perf_counter()
            text = await self._extractors[ext].extract_async(file.file)
            elapsed = time.perf_counter() - t0

            # File rỗng hoặc PDF chỉ có ảnh thì coi là lỗi
            if not text.strip():
                logger.warning("No text content extracted from '%s'", fname)
                return CVResult(**common, status=CVStatus.ERROR, error_message="No text content extracted (file may be empty or image-only)")

            logger.info("Extracted '%s' in %.2fs (%d chars)", fname, elapsed, len(text))
            return CVResult(**common, status=CVStatus.SUCCESS, text=text)

        except Exception as exc:
            # Bắt mọi exception để batch không bị dừng giữa chừng
            logger.error("Failed to extract '%s': %s", fname, exc)
            return CVResult(**common, status=CVStatus.ERROR, error_message=str(exc))


    # Logic giống extract_file nhưng input là path string thay vì file object
    async def _process_file(self, file_path: str) -> CVResult:
        ext = os.path.splitext(file_path)[1].lower()
        common = dict(file_name=os.path.basename(file_path), extension=ext)
        fname = common["file_name"]
        try:
            t0 = time.perf_counter()
            text = await self._extractors[ext].extract_async(file_path)
            elapsed = time.perf_counter() - t0

            if not text.strip():
                logger.warning("No text content extracted from '%s'", fname)
                return CVResult(**common, status=CVStatus.ERROR, error_message="No text content extracted (file may be empty or image-only)")

            logger.info("Extracted '%s' in %.2fs (%d chars)", fname, elapsed, len(text))
            return CVResult(**common, status=CVStatus.SUCCESS, text=text)

        except Exception as exc:
            logger.error("Failed to extract '%s': %s", fname, exc)
            return CVResult(**common, status=CVStatus.ERROR, error_message=str(exc))

    # Extract từ UploadMultipleCVs
    async def extract_folder(self, path: str) -> list[CVResult]:
        # Nếu folder không có file hỗ trợ: trả về []
        if os.path.isdir(path):
            files = self._scan_files(path)
            if not files:
                logger.warning("No supported files found in '%s'", path)
                return []

            logger.info("Starting extraction of %d file(s) from '%s'", len(files), path)
            # asyncio.gather chạy tất cả task cùng lúc
            tasks = [self._process_file(fp) for fp in files]
            t0 = time.perf_counter()
            results = list(await asyncio.gather(*tasks))
            elapsed = time.perf_counter() - t0

            # Bao nhiêu file thành công / thất bại
            success = sum(1 for r in results if r.status == CVStatus.SUCCESS)
            failed = len(results) - success
            if failed:
                logger.warning("Extraction complete: %d/%d succeeded, %d failed (%.2fs)", success, len(results), failed, elapsed)
            else:
                logger.info("Extraction complete: %d/%d succeeded (%.2fs)", success, len(results), elapsed)
            return results

        # Nếu path không phải folder hợp lệ: raise FileNotFoundError
        logger.error("Path does not exist: '%s'", path)
        raise FileNotFoundError(f"Path does not exist: {path}")
