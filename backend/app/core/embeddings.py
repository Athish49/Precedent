"""Singleton sentence-transformers embedding loader with async interface."""

from __future__ import annotations

import asyncio

from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        from app.core.config import get_settings

        _model = SentenceTransformer(get_settings().embedding_model)
    return _model


def _encode(texts: list[str]) -> list[list[float]]:
    """Synchronous encode — runs in a threadpool to avoid blocking the event loop."""
    return _get_model().encode(texts, normalize_embeddings=True).tolist()  # type: ignore[return-value]


async def embed(texts: list[str]) -> list[list[float]]:
    """Encode *texts* into 384-dim float vectors.

    Runs the CPU-bound sentence-transformers model in a threadpool so the
    event loop is never blocked.  Deterministic: identical input → identical
    output (no dropout in inference mode).
    """
    return await asyncio.to_thread(_encode, texts)
