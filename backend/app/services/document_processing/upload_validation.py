"""Upload validation for document processing (task 2.8).

No database or network imports.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import zipfile
from dataclasses import dataclass

from app.api.errors import AppError

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"
_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._ -]")


@dataclass(frozen=True)
class ValidatedUpload:
    source_format: str   # "pdf" or "docx"
    sha256: str          # hex digest
    size_bytes: int
    safe_filename: str   # sanitized filename safe for storage keys


def validate_upload(filename: str, data: bytes, max_mb: int) -> ValidatedUpload:
    """Validate uploaded file bytes and return a :class:`ValidatedUpload`.

    Raises :class:`AppError` on any validation failure.
    """
    # 1. Empty data check
    if len(data) == 0:
        raise AppError(400, "empty_file", "Uploaded file is empty.")

    # 2. Size limit
    if len(data) > max_mb * 1024 * 1024:
        raise AppError(
            413,
            "file_too_large",
            f"File exceeds the {max_mb} MB limit.",
        )

    # 3. Detect type from first bytes
    if data[:5] == _PDF_MAGIC:
        source_format = "pdf"
    elif data[:4] == _ZIP_MAGIC:
        # Must be a DOCX (ZIP containing word/document.xml)
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                has_word = "word/document.xml" in zf.namelist()
        except zipfile.BadZipFile:
            has_word = False
        if not has_word:
            raise AppError(400, "unsupported_format", "File is a ZIP archive but not a DOCX.")
        source_format = "docx"
    else:
        raise AppError(400, "unsupported_format", "File format is not supported (expected PDF or DOCX).")

    # 4. SHA-256
    digest = hashlib.sha256(data).hexdigest()

    # 5. Safe filename
    safe = _make_safe_filename(filename, source_format)

    return ValidatedUpload(
        source_format=source_format,
        sha256=digest,
        size_bytes=len(data),
        safe_filename=safe,
    )


def _make_safe_filename(filename: str, source_format: str) -> str:
    # Strip directory components
    base = os.path.basename(filename)

    # Replace unsafe characters with underscores
    base = _SAFE_CHARS.sub("_", base)

    # Remove leading dots
    base = base.lstrip(".")

    # If empty after sanitizing, use a generic name
    if not base:
        base = "upload"

    # Force correct extension
    expected_ext = f".{source_format}"
    # Strip any existing extension and add the correct one
    name_no_ext, _ext = os.path.splitext(base)
    if not name_no_ext:
        name_no_ext = "upload"
    base = name_no_ext + expected_ext

    # Truncate to 120 characters max (preserving extension)
    if len(base) > 120:
        ext = expected_ext
        max_stem = 120 - len(ext)
        base = name_no_ext[:max_stem] + ext

    return base
