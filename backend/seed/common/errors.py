"""Exceptions raised by seed code."""

from __future__ import annotations

from pathlib import Path


class SeedError(Exception):
    """A seed command failed for a reason the user can act on.

    :func:`seed.common.cli.run` prints the message and exits with status 1
    instead of showing a traceback.
    """


class SeedFileError(SeedError):
    """A seed content file is missing, unreadable or malformed."""

    def __init__(self, path: Path | str, message: str) -> None:
        self.path = Path(path)
        self.message = message
        super().__init__(f"{self.path}: {message}")
