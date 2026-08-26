"""CI guard assertions — run locally to mirror what CI checks."""

from __future__ import annotations

import subprocess
from pathlib import Path

_BACKEND = Path(__file__).parent.parent.parent / "backend"
_APP = _BACKEND / "app"


def _grep(pattern: str, path: Path) -> list[str]:
    result = subprocess.run(
        ["grep", "-r", pattern, str(path), "--include=*.py"],
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def test_anthropic_import_only_in_core_llm():
    hits = _grep("import anthropic", _APP)
    violations = [h for h in hits if "/core/llm/" not in h]
    assert not violations, "'import anthropic' outside app/core/llm/:\n" + "\n".join(violations)


def test_document_processing_no_llm_import():
    dp_dir = _APP / "services" / "document_processing"
    hits = _grep("core.llm", dp_dir) + _grep("core/llm", dp_dir)
    assert not hits, "app/services/document_processing imports core/llm:\n" + "\n".join(hits)


def test_analytics_no_llm_import():
    an_dir = _APP / "services" / "analytics"
    hits = _grep("core.llm", an_dir) + _grep("core/llm", an_dir)
    assert not hits, "app/services/analytics imports core/llm:\n" + "\n".join(hits)
