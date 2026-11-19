"""CI guard assertions — run locally to mirror what CI checks."""

from __future__ import annotations

import subprocess
from pathlib import Path

# This file lives at backend/tests/unit/test_ci_guards.py, so the real
# backend/ folder is three parents up from here: unit -> tests -> backend.
#
# Previously this built `_BACKEND` as `.../backend/backend`, which does not
# exist, so every `_grep` call below searched a path with zero files and
# every guard in this file passed vacuously, without checking anything. Each
# test now asserts its target folder actually exists, so that exact failure
# mode (a guard silently passing on a path that is not there) cannot recur
# unnoticed.
_BACKEND = Path(__file__).parent.parent.parent
_APP = _BACKEND / "app"


def _grep(pattern: str, path: Path) -> list[str]:
    result = subprocess.run(
        ["grep", "-r", pattern, str(path), "--include=*.py"],
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def test_backend_paths_resolve():
    """Guard the guards: if this fails, every other test in this file would
    be passing vacuously on an empty search path."""
    assert _BACKEND.is_dir(), f"_BACKEND does not resolve to a real folder: {_BACKEND}"
    assert _APP.is_dir(), f"_APP does not resolve to a real folder: {_APP}"


def test_anthropic_import_only_in_core_llm():
    hits = _grep("import anthropic", _APP)
    violations = [h for h in hits if "/core/llm/" not in h]
    assert not violations, "'import anthropic' outside app/core/llm/:\n" + "\n".join(violations)


def test_document_processing_no_llm_import():
    dp_dir = _APP / "services" / "document_processing"
    assert dp_dir.is_dir(), f"guarded folder does not exist: {dp_dir}"
    hits = _grep("core.llm", dp_dir) + _grep("core/llm", dp_dir)
    assert not hits, "app/services/document_processing imports core/llm:\n" + "\n".join(hits)


def test_analytics_no_llm_import():
    an_dir = _APP / "services" / "analytics"
    assert an_dir.is_dir(), f"guarded folder does not exist: {an_dir}"
    hits = _grep("core.llm", an_dir) + _grep("core/llm", an_dir)
    assert not hits, "app/services/analytics imports core/llm:\n" + "\n".join(hits)


# Built from parts, not a literal, so this file does not itself trip the
# very guard it defines below (and does not trip the pre-existing,
# equivalent guard in test_extend_client.py, which scans for the literal
# string and excludes only its own file).
_EXTEND_HOST = "api" + ".extend.ai"


def test_no_extend_url_outside_extend_package():
    """The Extend API hostname appears only under app/core/extend/.

    Equivalent coverage already exists in
    ``tests/unit/test_extend_client.py::test_no_extend_url_outside_extend_package``
    (scans app/ and tests/, excludes the `extend` and `extend_eval`
    directories). This guard is added here too so the whole family of
    import/string-scope guards lives in one file and uses the same `_grep`
    helper and the now-repaired `_BACKEND` path.
    """
    extend_dir = _APP / "core" / "extend"
    assert extend_dir.is_dir(), f"guarded folder does not exist: {extend_dir}"
    hits = _grep(_EXTEND_HOST, _APP) + _grep(_EXTEND_HOST, _BACKEND / "tests")
    violations = [
        h
        for h in hits
        if "/app/core/extend/" not in h
        # tests/fixtures/extend_eval/ is legacy material task 0.3 removes;
        # excluded here the same way the existing guard in
        # test_extend_client.py excludes it, so this guard does not fail
        # before that task lands.
        and "/fixtures/extend_eval/" not in h
        # test_extend_client.py (task 0.1, not owned by this file) names the
        # literal string in its own comments/docstrings to describe its
        # equivalent guard, not to call the API; it excludes itself from its
        # own scan the same way.
        and "/tests/unit/test_extend_client.py:" not in h
    ]
    assert not violations, f"{_EXTEND_HOST!r} outside app/core/extend/:\n" + "\n".join(violations)


def test_core_extend_import_only_in_document_processing():
    """``core.extend`` (the Python import) is used only under
    app/services/document_processing/ — the one package allowed to talk to
    Extend (task 0.1/3.1)."""
    dp_dir = _APP / "services" / "document_processing"
    assert dp_dir.is_dir(), f"guarded folder does not exist: {dp_dir}"
    hits = _grep("core.extend", _APP) + _grep("core/extend", _APP)
    violations = [
        h
        for h in hits
        if "/services/document_processing/" not in h and "/core/extend/" not in h
    ]
    assert not violations, "'core.extend' imported outside document_processing:\n" + "\n".join(
        violations
    )
