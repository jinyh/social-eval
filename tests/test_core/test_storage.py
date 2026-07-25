from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi import UploadFile

from src.core import storage


def _docx_bytes() -> bytes:
    content = BytesIO()
    with ZipFile(content, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    return content.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("paper.pdf", b"%PDF-1.7\nminimal"),
        ("paper.docx", _docx_bytes()),
        ("paper.txt", "法学论文".encode()),
    ],
)
async def test_save_upload_validates_supported_content(
    tmp_path, monkeypatch, filename: str, content: bytes
) -> None:
    monkeypatch.setattr(storage, "UPLOAD_ROOT", tmp_path)
    upload = UploadFile(filename=filename, file=BytesIO(content))

    result = await storage.save_upload_file(upload, "paper-id")

    assert result.read_bytes() == content
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.asyncio
async def test_save_upload_rejects_extension_content_mismatch(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(storage, "UPLOAD_ROOT", tmp_path)
    upload = UploadFile(filename="paper.pdf", file=BytesIO(b"not-a-pdf"))

    with pytest.raises(ValueError, match="不是有效 PDF"):
        await storage.save_upload_file(upload, "paper-id")

    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_save_upload_rejects_oversize_and_removes_partial_file(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(storage, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(storage.settings, "upload_max_bytes", 8)
    upload = UploadFile(filename="paper.txt", file=BytesIO(b"0123456789"))

    with pytest.raises(ValueError, match="文件超过"):
        await storage.save_upload_file(upload, "paper-id")

    assert not list(tmp_path.iterdir())
