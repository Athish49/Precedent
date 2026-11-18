"""Locations of seed content inside ``backend/seed/``."""

from __future__ import annotations

from pathlib import Path

from seed.common.errors import SeedError

SEED_ROOT: Path = Path(__file__).resolve().parent.parent
"""The ``backend/seed`` folder."""

DEFAULT_DATASET = "halcyon"


def data_dir(category: str, dataset: str = DEFAULT_DATASET) -> Path:
    """Return ``backend/seed/<category>/data/<dataset>``.

    The folder is not required to exist; callers decide whether that is an error.
    """
    for part in (category, dataset):
        if not part or "/" in part or "\\" in part or part in {".", ".."}:
            raise SeedError(f"invalid seed path component: {part!r}")
    return SEED_ROOT / category / "data" / dataset
