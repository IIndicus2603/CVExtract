# Extract text từ file DOCX dùng python-docx

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from features.extraction.extractors.base import BaseExtractor


class DocxExtractor(BaseExtractor):
    def extract(self, file_path: str) -> str:
        """Mở file rồi duyệt toàn bộ body lấy text"""
        doc = Document(file_path)
        return "\n".join(self._iter_block_text(doc.element.body, doc)).strip()

    def _iter_block_text(self, parent, doc):
        """Duyệt từng block trong document/cell, yield text paragraph hoặc table"""
        for child in parent.iterchildren():
            if child.tag == qn("w:p"):
                text = Paragraph(child, doc).text.strip()
                if text:
                    yield text
            elif child.tag == qn("w:tbl"):
                yield from self._iter_table_text(Table(child, doc))

    def _iter_table_text(self, table: Table):
        """Duyệt bảng theo từng hàng/cell, yield text từng cell"""
        for row in table.rows:
            for cell in row.cells:
                yield from self._iter_cell_text(cell)

    def _iter_cell_text(self, cell: _Cell):
        """Xử lý cell có thể chứa paragraph hoặc bảng lồng nhau"""
        for child in cell._tc.iterchildren():
            if child.tag == qn("w:p"):
                text = Paragraph(child, cell).text.strip()
                if text:
                    yield text
            elif child.tag == qn("w:tbl"):
                yield from self._iter_table_text(Table(child, cell))
