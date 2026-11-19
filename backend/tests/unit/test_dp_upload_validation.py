"""Tests for task 2.8 — upload_validation."""

from __future__ import annotations

import io
import zipfile

import pytest

from app.api.errors import AppError
from app.services.document_processing.upload_validation import ValidatedUpload, validate_upload

PDF_MAGIC = b"%PDF-"


def _make_zip(entries: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _make_docx() -> bytes:
    return _make_zip({"word/document.xml": "<w:document/>"})


# ── Error cases ───────────────────────────────────────────────────────────────


def test_empty_file():
    with pytest.raises(AppError) as exc_info:
        validate_upload("test.pdf", b"", 25)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "empty_file"


def test_file_too_large():
    # 26 MB of valid PDF bytes
    data = PDF_MAGIC + b"x" * (26 * 1024 * 1024)
    with pytest.raises(AppError) as exc_info:
        validate_upload("test.pdf", data, 25)
    assert exc_info.value.status_code == 413
    assert exc_info.value.code == "file_too_large"


def test_zip_not_docx():
    data = _make_zip({"not_word.xml": "data"})
    with pytest.raises(AppError) as exc_info:
        validate_upload("file.zip", data, 25)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "unsupported_format"


def test_unsupported_format():
    with pytest.raises(AppError) as exc_info:
        validate_upload("file.txt", b"hello world", 25)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "unsupported_format"


# ── Happy-path cases ──────────────────────────────────────────────────────────


def test_pdf_named_as_docx():
    # PDF magic bytes but .docx extension -> detected as pdf
    data = PDF_MAGIC + b"x" * 100
    result = validate_upload("file.docx", data, 25)
    assert result.source_format == "pdf"
    assert result.safe_filename.endswith(".pdf")


def test_valid_docx():
    data = _make_docx()
    result = validate_upload("contract.docx", data, 25)
    assert result.source_format == "docx"
    assert result.safe_filename == "contract.docx"


def test_valid_pdf():
    data = PDF_MAGIC + b"x" * 100
    result = validate_upload("document.pdf", data, 25)
    assert isinstance(result, ValidatedUpload)
    assert result.source_format == "pdf"
    assert len(result.sha256) == 64
    assert result.size_bytes == len(data)
    assert result.safe_filename == "document.pdf"


def test_path_traversal():
    data = PDF_MAGIC + b"x" * 100
    result = validate_upload("../../etc/passwd.pdf", data, 25)
    assert "/" not in result.safe_filename
    assert ".." not in result.safe_filename


def test_leading_dot_removed():
    data = PDF_MAGIC + b"x" * 100
    result = validate_upload(".hidden.pdf", data, 25)
    assert not result.safe_filename.startswith(".")


def test_long_filename_truncated():
    long_name = "a" * 200 + ".pdf"
    data = PDF_MAGIC + b"x" * 100
    result = validate_upload(long_name, data, 25)
    assert len(result.safe_filename) <= 120


def test_sha256_correctness():
    import hashlib

    data = PDF_MAGIC + b"test data"
    result = validate_upload("test.pdf", data, 25)
    assert result.sha256 == hashlib.sha256(data).hexdigest()


def test_special_chars_in_filename():
    data = PDF_MAGIC + b"x" * 100
    result = validate_upload("my contract (v2)!@#.pdf", data, 25)
    # Only safe chars remain
    import re
    assert re.fullmatch(r"[A-Za-z0-9._ -]+", result.safe_filename)
