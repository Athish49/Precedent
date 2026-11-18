"""Seed isolation guard.

The seed folder (the top-level package beside ``app`` in ``backend/``) is
optional: deleting it must change nothing about the application. So nothing
under ``app``, ``migrations``, ``scripts`` or ``tests`` may import from it,
read a file under it, or call one of its commands.

This test reads source files only. It never imports the seed package and it
passes whether or not the folder exists. CI runs an equivalent grep.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_SCANNED_DIRS = ("app", "migrations", "scripts", "tests")
_SELF = Path(__file__).resolve()
_SKIP_DIR_NAMES = {"__pycache__", ".venv", "node_modules"}

_PKG = "seed"

# A string that is a filesystem path into the folder: "seed", "seed/x",
# "backend/seed", "../seed/playbooks/data". Not "scripts/seed_playbooks.py".
_PATH_RE = re.compile(rf"(?:^|[/\\]){_PKG}(?:[/\\]|$)")
# A string that names a seed module: "seed.playbooks.load",
# "python -m seed.playbooks.load". Not "scripts.seed_playbooks.seed_all".
_MODULE_RE = re.compile(rf"(?:^|[\s\"'=]){_PKG}\.[A-Za-z_]")
# Fallback for a file that does not parse.
_IMPORT_LINE_RE = re.compile(rf"^\s*(?:import|from)\s+{_PKG}(?:[.\s,;]|$)")


def _python_files() -> list[Path]:
    files: list[Path] = []
    for name in _SCANNED_DIRS:
        root = _BACKEND / name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if _SKIP_DIR_NAMES.intersection(path.parts):
                continue
            if path.resolve() == _SELF:
                continue
            files.append(path)
    return sorted(files)


def _is_seed_module(name: str | None) -> bool:
    return name == _PKG or (name is not None and name.startswith(_PKG + "."))


def find_violations(source: str) -> list[tuple[int, str]]:
    """Return ``(line, reason)`` for each use of the seed folder in ``source``."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [
            (number, "imports the seed package")
            for number, line in enumerate(source.splitlines(), start=1)
            if _IMPORT_LINE_RE.match(line)
        ]

    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(_is_seed_module(alias.name) for alias in node.names):
                found.append((node.lineno, "imports the seed package"))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and _is_seed_module(node.module):
                found.append((node.lineno, "imports from the seed package"))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _PATH_RE.search(node.value):
                found.append((node.lineno, "string path points into the seed folder"))
            elif _MODULE_RE.search(node.value):
                found.append((node.lineno, "string names a seed module or command"))
    return sorted(found)


def test_scan_covers_the_application() -> None:
    files = _python_files()
    assert files, f"no Python files found under {_BACKEND}"
    scanned_roots = {path.relative_to(_BACKEND).parts[0] for path in files}
    assert {"app", "tests"} <= scanned_roots
    assert _SELF not in {path.resolve() for path in files}


def test_nothing_outside_seed_uses_seed() -> None:
    violations: list[str] = []
    for path in _python_files():
        source = path.read_text(encoding="utf-8")
        for line, reason in find_violations(source):
            violations.append(f"{path.relative_to(_BACKEND)}:{line}: {reason}")
    assert not violations, (
        "Application code must not depend on backend/seed/ "
        "(playbook_implementation.md section 3.0, rule 1). "
        "Seed code may import from app, never the reverse:\n" + "\n".join(violations)
    )


@pytest.mark.parametrize(
    "source",
    [
        "import seed\n",
        "import seed.playbooks.load\n",
        "import os, seed\n",
        "import seed as s\n",
        "from seed import common\n",
        "from seed.common import load_yaml\n",
        "def f():\n    from seed.playbooks import models\n",
        "try:\n    import seed\nexcept ImportError:\n    pass\n",
        "p = 'seed/playbooks/data/halcyon/taxonomy.yaml'\n",
        "p = 'backend/seed/README.md'\n",
        "p = ROOT / 'seed' / 'playbooks'\n",
        "p = '../seed'\n",
        "m = importlib.import_module('seed.playbooks.load')\n",
        "cmd = ['python', '-m', 'seed.playbooks.load']\n",
        "cmd = 'python -m seed.playbooks.validate'\n",
        "import seed\ndef broken(:\n",
    ],
)
def test_guard_detects(source: str) -> None:
    assert find_violations(source), f"guard missed: {source!r}"


@pytest.mark.parametrize(
    "source",
    [
        "from scripts.seed_playbooks import seed_all\n",
        "import scripts.seed_playbooks\n",
        "p = 'scripts/seed_playbooks.py'\n",
        "t = 'scripts.seed_playbooks.playbook_repo.list_playbooks'\n",
        "import random\nrandom.seed(7)\n",
        "seed = 42\nx = seed.bit_length()\n",
        "# import seed is forbidden here\n",
        "s = 'comes from the template seed, not executed contracts.'\n",
        "s = 'the template seed. Next sentence.'\n",
        "from . import seeding\n",
        "from .seed import thing\n",
        "import seedling\n",
        "p = 'data/seedlings/x.yaml'\n",
        "p = 'reseed/x'\n",
    ],
)
def test_guard_allows(source: str) -> None:
    assert find_violations(source) == []
