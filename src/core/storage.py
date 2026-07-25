from __future__ import annotations

from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fastapi import UploadFile

from src.core.config import settings

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}
UPLOAD_ROOT = Path("data/uploads")
CHUNK_SIZE = 1024 * 1024
MAX_DOCX_ENTRIES = 5000
MAX_DOCX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


def get_extension(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")


def validate_upload_filename(filename: str) -> str:
    ext = get_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext or 'unknown'}")
    return ext


async def save_upload_file(file: UploadFile, paper_id: str) -> Path:
    """分块保存并校验扩展名、容量与基本文件结构。"""

    ext = validate_upload_filename(file.filename or "")
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_ROOT / f"{paper_id}.{ext}"
    temporary = UPLOAD_ROOT / f".{paper_id}.{ext}.part"
    size = 0
    header = b""
    try:
        with temporary.open("wb") as target:
            while chunk := await file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > settings.upload_max_bytes:
                    raise ValueError(
                        f"文件超过 {settings.upload_max_bytes // (1024 * 1024)} MB 上限"
                    )
                if len(header) < 8:
                    header += chunk[: 8 - len(header)]
                target.write(chunk)
        if size == 0:
            raise ValueError("上传文件为空")
        _validate_file_content(temporary, ext, header)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def _validate_file_content(path: Path, extension: str, header: bytes) -> None:
    if extension == "pdf":
        if not header.startswith(b"%PDF-"):
            raise ValueError("文件扩展名为 PDF，但内容不是有效 PDF")
        return
    if extension == "docx":
        if not header.startswith(b"PK"):
            raise ValueError("文件扩展名为 DOCX，但内容不是有效 DOCX")
        try:
            with ZipFile(path) as archive:
                entries = archive.infolist()
                names = {entry.filename for entry in entries}
                total_size = sum(entry.file_size for entry in entries)
                if (
                    "[Content_Types].xml" not in names
                    or "word/document.xml" not in names
                ):
                    raise ValueError("DOCX 缺少必要的文档结构")
                if (
                    len(entries) > MAX_DOCX_ENTRIES
                    or total_size > MAX_DOCX_UNCOMPRESSED_BYTES
                ):
                    raise ValueError("DOCX 解压后内容异常，已拒绝上传")
        except BadZipFile as exc:
            raise ValueError("DOCX 压缩结构损坏") from exc
        return
    try:
        path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("TXT 必须使用 UTF-8 编码且不能包含二进制内容") from exc
