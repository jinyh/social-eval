from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}
UPLOAD_ROOT = Path("data/uploads")


def get_extension(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")


def validate_upload_filename(filename: str) -> str:
    ext = get_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext or 'unknown'}")
    return ext


async def save_upload_file(file: UploadFile, paper_id: str) -> Path:
    ext = validate_upload_filename(file.filename or "")
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_ROOT / f"{paper_id}.{ext}"
    content = await file.read()
    destination.write_bytes(content)
    return destination
