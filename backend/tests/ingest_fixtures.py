"""Loader for recorded Extend API fixtures used in ingest tests.

Each fixture case lives under tests/fixtures/ingest/<name>/ and contains:
  extract.json  — Extend extract_run response
  parse.json    — Extend parse_run response
  answers.json  — Expected field values for the case
"""

from __future__ import annotations

import json
from pathlib import Path

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "ingest"


def all_cases() -> list[str]:
    """Return the names of all fixture cases (subdirectories with extract.json)."""
    return sorted(
        p.name
        for p in _FIXTURES_DIR.iterdir()
        if p.is_dir() and (p / "extract.json").exists()
    )


def load_case(name: str) -> tuple[dict, list[dict], dict]:
    """Load a fixture case by name.

    Returns:
        (extract_dict, parse_blocks, answers)

        extract_dict  — the full extract_run response dict
        parse_blocks  — blocks flattened across all chunks:
                        [block for chunk in data["output"]["chunks"]
                         for block in chunk["blocks"]]
        answers       — the answers dict
    """
    case_dir = _FIXTURES_DIR / name
    if not case_dir.is_dir():
        raise FileNotFoundError(f"Fixture case not found: {name!r} (looked in {case_dir})")

    with open(case_dir / "extract.json") as f:
        extract_dict = json.load(f)

    with open(case_dir / "parse.json") as f:
        parse_data = json.load(f)

    parse_blocks: list[dict] = [
        block
        for chunk in parse_data["output"]["chunks"]
        for block in chunk["blocks"]
    ]

    with open(case_dir / "answers.json") as f:
        answers = json.load(f)

    return extract_dict, parse_blocks, answers
