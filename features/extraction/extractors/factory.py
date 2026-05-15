# Map extension đến extractor instance

from features.extraction.extractors.base import BaseExtractor
from features.extraction.extractors.pdf import PdfExtractor
from features.extraction.extractors.docx import DocxExtractor

EXTRACTOR_MAP: dict[str, BaseExtractor] = {
    ".pdf": PdfExtractor(),
    ".docx": DocxExtractor(),
}

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(EXTRACTOR_MAP)
