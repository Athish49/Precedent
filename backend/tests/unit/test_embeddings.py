"""Unit tests for app.core.embeddings."""

from app.core.embeddings import embed

EXPECTED_DIM = 384


async def test_embed_dimension() -> None:
    """Each vector must be exactly 384 floats."""
    result = await embed(["hello world"])
    assert len(result) == 1
    assert len(result[0]) == EXPECTED_DIM


async def test_embed_determinism() -> None:
    """Same input must produce bitwise-identical output."""
    text = ["contract termination clause"]
    first = await embed(text)
    second = await embed(text)
    assert first == second


async def test_embed_batch() -> None:
    """Number of output vectors must match number of input texts."""
    texts = ["alpha", "beta", "gamma", "delta"]
    result = await embed(texts)
    assert len(result) == len(texts)
    for vec in result:
        assert len(vec) == EXPECTED_DIM
