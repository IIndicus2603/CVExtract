# Extract text từ file PDF dùng pdfplumber

import pdfplumber
from features.extraction.extractors.base import BaseExtractor


class PdfExtractor(BaseExtractor):
    def extract(self, file_path: str) -> str:
        """Mở PDF, đọc từng trang rồi nối lại bằng newline"""
        parts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = self._extract_page(page)
                if page_text:
                    parts.append(page_text)
        return "\n".join(parts).strip()

    def _extract_page(self, page) -> str:
        """Extract 1 page, nếu có bảng tách thành blocks sort theo y position"""
        tables = page.find_tables()
        if not tables:
            return page.extract_text() or ""

        # block = (y, text), sort cuối cùng theo y để giữ thứ tự đọc tự nhiên
        blocks: list[tuple[float, str]] = []

        # Text ngoài bảng (loại bbox của bảng để tránh trùng)
        outside = page
        for t in tables:
            outside = outside.outside_bbox(t.bbox, relative=False, strict=False)
        for line in outside.extract_text_lines():
            text = line["text"].strip()
            if text:
                blocks.append((line["top"], text))

        # Text trong bảng
        for t in tables:
            cell_lines = []
            for row in t.extract():
                for cell in row:
                    if cell and cell.strip():
                        cell_lines.append(cell.strip())
            if cell_lines:
                top_y = t.bbox[1]
                blocks.append((top_y, "\n".join(cell_lines)))

        blocks.sort(key=lambda b: b[0])
        return "\n".join(text for _, text in blocks)
