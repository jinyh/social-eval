from pathlib import Path
from src.ingestion.parsers.base import BaseParser
from src.ingestion.parsers.pdf_parser import PDFParser
from src.ingestion.parsers.docx_parser import DocxParser
from src.ingestion.parsers.txt_parser import TxtParser
from src.ingestion.reference_extractor import extract_references
from src.ingestion.structure_detector import detect_structure
from src.ingestion.schemas import ProcessedPaper
from src.core.exceptions import IngestionError

PARSERS: dict[str, type[BaseParser]] = {
    "pdf": PDFParser,
    "docx": DocxParser,
    "txt": TxtParser,
}


def process_file(file_path: str) -> ProcessedPaper:
    """主入口：根据文件扩展名选择 Parser，返回 ProcessedPaper"""
    ext = Path(file_path).suffix.lower().lstrip(".")
    parser_cls = PARSERS.get(ext)
    if not parser_cls:
        raise IngestionError(f"不支持的文件类型：{ext}")

    raw = parser_cls().parse(file_path)
    body_text, refs = extract_references(raw.text)
    paper = detect_structure(body_text)
    paper.references = refs
    paper.full_text = raw.text
    return paper
