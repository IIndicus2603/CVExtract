# Extract text từ file DOCX dùng thư viện python-docx

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from features.extraction.extractors.base import BaseExtractor


class DocxExtractor(BaseExtractor):
    def extract(self, file_path: str) -> str:
        # Mở file rồi duyệt toàn bộ phần thân của document
        doc = Document(file_path)
        return "\n".join(self._iter_block_text(doc.element.body, doc)).strip()

    def _iter_block_text(self, parent, doc):
        # Duyệt từng phần tử con bên trong document/cell
        for child in parent.iterchildren():
            if child.tag == qn("w:p"):
                # Là đoạn văn thì lấy text
                text = Paragraph(child, doc).text.strip()
                if text:
                    yield text
            elif child.tag == qn("w:tbl"):
                # Là bảng thì đi vào duyệt từng cell
                yield from self._iter_table_text(Table(child, doc))

    def _iter_table_text(self, table: Table):
        # Duyệt bảng theo từng hàng, mỗi hàng có nhiều cell
        for row in table.rows:
            for cell in row.cells:
                yield from self._iter_cell_text(cell)

    def _iter_cell_text(self, cell: _Cell):
        # xử lý trường hợp trong 1 cell có thể chứa đoạn văn hoặc bảng lồng nhau
        for child in cell._tc.iterchildren():
            if child.tag == qn("w:p"):
                text = Paragraph(child, cell).text.strip()
                if text:
                    yield text
            elif child.tag == qn("w:tbl"):
                yield from self._iter_table_text(Table(child, cell))
