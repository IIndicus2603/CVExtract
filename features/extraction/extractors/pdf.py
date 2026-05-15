# Extract text từ file PDF dùng thư viện pdfplumber

import pdfplumber
from features.extraction.extractors.base import BaseExtractor


class PdfExtractor(BaseExtractor):
    def extract(self, file_path: str) -> str:
        # Mở file PDF, đọc từng trang rồi nối lại bằng dấu xuống dòng
        parts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = self._extract_page(page)
                if page_text:
                    parts.append(page_text)
        return "\n".join(parts).strip()

    def _extract_page(self, page) -> str:
        # Tìm xem trang này có bảng không, nếu không có thì extract bình thường
        tables = page.find_tables()
        if not tables:
            return page.extract_text() or ""

        # Có bảng: tách thành nhiều "block", mỗi block kèm vị trí y (để sort sau)
        # block = (y, text)
        blocks: list[tuple[float, str]] = []

        # Lấy text ngoài bảng rồi và bỏ bảng ra khỏi trang để tránh đọc trùng
        outside = page
        for t in tables:
            outside = outside.outside_bbox(t.bbox, relative=False, strict=False)
        for line in outside.extract_text_lines():
            text = line["text"].strip()
            if text:
                blocks.append((line["top"], text))

        # Lấy text trong bảng
        for t in tables:
            cell_lines = []
            for row in t.extract():
                for cell in row:
                    if cell and cell.strip():
                        cell_lines.append(cell.strip())
            if cell_lines:
                top_y = t.bbox[1]
                blocks.append((top_y, "\n".join(cell_lines)))

        # Sort theo thứ tự bản gốc
        blocks.sort(key=lambda b: b[0])
        return "\n".join(text for _, text in blocks)
