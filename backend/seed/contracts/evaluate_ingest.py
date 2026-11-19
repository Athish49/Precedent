"""Corpus run against live Extend (task 6.2).

Uploads each of the 12 seed DOCX contracts (plus 2 converted to PDF) through
the real ``ExtendClient``, runs Extract with the schema from
``app.services.document_processing.fields.build_extract_schema``, fetches
Parse blocks, and runs them through the pure pipeline
(``app.services.document_processing.pipeline.build_result``) with
``own_org_names=["Halcyon Care"]``.

No database writes happen anywhere in this script. Results are compared
against ``seed/contracts/data/halcyon/fields_expected.yaml`` and a report is
printed to stdout. The caller is responsible for turning that report into
``document_processing_verification.md``.

Run as:

    cd backend && .venv/bin/python -m seed.contracts.evaluate_ingest

Requires ``EXTEND_API_KEY`` in ``backend/.env``. This is the one script in
the whole programme allowed to make live calls to the Extend API. The key is
read once from the ``.env`` file and passed directly to the client
constructor; it is never logged, printed or written to any output file.

This script lives under ``seed/`` and may import from ``app`` (seed code is
allowed to; the reverse is not -- see ``document_processing_implementation.md``
section 1).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values
from rapidfuzz import fuzz

from app.core.extend.client import ExtendClient
from app.services.document_processing.clause_typing import FamilyIndex
from app.services.document_processing.fields import REGISTRY
from app.services.document_processing.invariants import InvariantError
from app.services.document_processing.pipeline import NoTextError, build_result

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

_BACKEND = Path(__file__).resolve().parents[2]
_DOCX_DIR = _BACKEND / "seed" / "contracts" / "data" / "halcyon" / "docx"
_EXPECTED_PATH = _BACKEND / "seed" / "contracts" / "data" / "halcyon" / "fields_expected.yaml"
_ENV_PATH = _BACKEND / ".env"

OWN_ORG_NAMES = ["Halcyon Care"]

# Pinned Extend facts (document_processing_implementation.md section 3).
_EXTEND_BASE_URL = "https://api.extend.ai"
_EXTRACT_PROCESSOR = "extraction_light"
_EXTRACT_VERSION = "3.8.0"
_PARSE_ENGINE = "parse_light"
_PARSE_VERSION = "1.0.0"
_POLL_INTERVAL_SECONDS = 3
_TIMEOUT_SECONDS = 600

# Two contracts also run through the PDF path (one MSA, one DPA). A tuple,
# not a set: iteration order must be deterministic, since the cost ceiling
# may be reached partway through and whichever one runs first is the one
# that gets billed (confirmed live: an earlier set here is why the first
# run processed 07 before 01).
_PDF_CASE_FILES = (
    "01_saas_msa_own_clean",
    "07_dpa_counterparty_subprocessor_breach",
)

# Credit guardrail: stop issuing new Extract runs once usage looks like it is
# running far above the ~250-credit ceiling from the implementation doc.
_COST_CEILING_CREDITS = 250.0
_COST_WARN_CREDITS = 220.0


# ---------------------------------------------------------------------------
# FamilyIndex from the real migrations (same technique as
# tests/unit/test_dp_pipeline_replay.py: no database, no network).
# ---------------------------------------------------------------------------


def _load_migration_module(filename: str):
    path = _BACKEND / "migrations" / "versions" / filename
    spec = importlib.util.spec_from_file_location(f"_migration_{filename}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_taxonomy() -> tuple[FamilyIndex, list[str]]:
    """Return (FamilyIndex, agreement_type_keys) from the real migration data."""
    m010 = _load_migration_module("010_playbook_lookups.py")
    m016 = _load_migration_module("016_doc_proc_schema_a.py")

    rows: list[dict[str, Any]] = [
        {"key": fam["key"], "synonyms": fam["synonyms"]} for fam in m010._CLAUSE_FAMILIES
    ]
    for fam in m016._NEW_FAMILIES:
        rows.append({"key": fam["key"], "synonyms": json.loads(fam["synonyms"])})
    assert len(rows) == 31

    agreement_type_keys = [
        t["key"] for t in m010._AGREEMENT_TYPES if t["kind"] == "agreement"
    ]
    assert agreement_type_keys == ["nda", "saas_msa", "dpa", "vendor_msa"]

    return FamilyIndex.from_rows(rows), agreement_type_keys


# ---------------------------------------------------------------------------
# PDF conversion (soffice, if available)
# ---------------------------------------------------------------------------


def _find_soffice() -> str | None:
    for candidate in ("soffice", "/opt/homebrew/bin/soffice", "/usr/bin/soffice"):
        try:
            result = subprocess.run(
                [candidate, "--version"], capture_output=True, timeout=15
            )
            if result.returncode == 0:
                return candidate
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
    return None


def _convert_to_pdf(soffice: str, docx_path: Path, out_dir: Path) -> Path | None:
    try:
        result = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx_path)],
            capture_output=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    pdf_path = out_dir / (docx_path.stem + ".pdf")
    return pdf_path if pdf_path.exists() else None


# ---------------------------------------------------------------------------
# Field matching (same spirit as tests/unit/test_dp_pipeline_replay.py, with
# extra handling for: null-expected fields, derived expiry_date, and
# descriptive dollar-amount answers in a numeric-typed field).
# ---------------------------------------------------------------------------


def _free_text_matches(value: Any, answer: Any) -> bool:
    v = str(value).strip().lower()
    a = str(answer).strip().lower()
    if not a:
        return not v
    if v in a or a in v:
        return True
    v_tokens = {t for t in re.findall(r"[a-z0-9$,.]+", v) if len(t) > 2}
    a_tokens = {t for t in re.findall(r"[a-z0-9$,.]+", a) if len(t) > 2}
    if not a_tokens:
        return False
    overlap = v_tokens & a_tokens
    return len(overlap) / len(a_tokens) >= 0.3


def _numeric_from_text(text: str) -> float | None:
    m = re.search(r"[\d][\d,]*(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


@dataclass
class FieldOutcome:
    key: str
    matched: bool
    expected: Any
    got: Any
    note: str = ""


def _score_field(field_key: str, by_key: dict[str, Any], expected: dict[str, Any]) -> FieldOutcome:
    field_def = REGISTRY[field_key]
    exp_val = expected.get(field_key)
    fv = by_key.get(field_key)
    got_val = fv.value if fv is not None else None

    # expiry_date: the pipeline derives this from effective_date +
    # initial_term_months when no explicit date is stated (plan 5.5 point
    # 4). fields_expected.yaml deliberately records null unless an explicit
    # calendar date is written (task 6.1's own rule), so a derived value
    # here is correct system behaviour, not a miss.
    if field_key == "expiry_date":
        if exp_val is None:
            if fv is not None and fv.source == "derived":
                return FieldOutcome(field_key, True, exp_val, got_val, "derived (expected: no explicit date)")
            if fv is None:
                return FieldOutcome(field_key, True, exp_val, got_val)
            return FieldOutcome(field_key, False, exp_val, got_val, "extract returned a value where none was expected")
        expected_date = str(exp_val).split(" ")[0]
        matched = fv is not None and str(got_val) == expected_date
        return FieldOutcome(field_key, matched, exp_val, got_val)

    if exp_val is None:
        matched = fv is None
        return FieldOutcome(field_key, matched, exp_val, got_val)

    if fv is None:
        return FieldOutcome(field_key, False, exp_val, got_val, "not extracted")

    if field_def.kind in ("integer",):
        try:
            matched = int(got_val) == int(exp_val)
        except (TypeError, ValueError):
            matched = False
        return FieldOutcome(field_key, matched, exp_val, got_val)

    if field_def.kind == "number":
        # total_value_amount's expected answers are often descriptive
        # ("$180,000 annual subscription fee plus ..."), not a bare number,
        # because the source states a composite fee. Extract a number from
        # the expected text and compare within 1%.
        if isinstance(exp_val, str):
            exp_num = _numeric_from_text(exp_val)
            if exp_num is None:
                matched = False
                note = "expected value has no extractable number"
            else:
                try:
                    matched = abs(float(got_val) - exp_num) <= max(1.0, 0.01 * exp_num)
                except (TypeError, ValueError):
                    matched = False
                note = "numeric-from-text comparison (descriptive expected value)"
            return FieldOutcome(field_key, matched, exp_val, got_val, note)
        try:
            matched = abs(float(got_val) - float(exp_val)) <= max(1.0, 0.01 * float(exp_val))
        except (TypeError, ValueError):
            matched = False
        return FieldOutcome(field_key, matched, exp_val, got_val)

    if field_def.kind == "boolean":
        matched = got_val is exp_val
        return FieldOutcome(field_key, matched, exp_val, got_val)

    if field_def.kind == "date":
        matched = str(got_val) == str(exp_val)
        return FieldOutcome(field_key, matched, exp_val, got_val)

    # string / enum / string_list -> free-text fuzzy match
    matched = _free_text_matches(got_val, exp_val)
    return FieldOutcome(field_key, matched, exp_val, got_val)


TIER1_KEYS = [k for k, fd in REGISTRY.items() if fd.tier == 1]


# ---------------------------------------------------------------------------
# Section recall / false splits / typing accuracy
# ---------------------------------------------------------------------------


def _normalize_number(s: str | None) -> str | None:
    if s is None:
        return None
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _normalize_title(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


@dataclass
class SectionMatch:
    expected_number: str
    expected_title: str
    expected_family: str | None
    found: bool
    found_clause: Any = None


_TITLE_SANITY_MIN = 35  # loose: just rules out a wildly wrong title on a number match


def _match_sections(result_clauses: list[Any], expected_sections: list[dict]) -> list[SectionMatch]:
    """Match each expected section to at most one result clause.

    One-to-one: a clause that has already satisfied one expected entry is
    removed from the candidate pool and cannot satisfy a second (the
    original version of this function let one clause satisfy several
    expected entries via a plain number lookup with no title check, which
    could silently inflate recall/typing and undercount false splits --
    confirmed on contract 7, where the pipeline itself warned
    ``section_not_anchored:9 Sub-processors`` yet an earlier version of this
    function still counted section 9 as found).

    A number match is also sanity-checked against the title (loose
    threshold -- this is not meant to be strict, just to catch a clause
    whose number happens to collide with the wrong expected entry).
    """
    level1 = [c for c in result_clauses if c.level == 1]
    has_preamble = next((c for c in level1 if c.clause_type == "preamble"), None)
    has_signature = next((c for c in level1 if c.clause_type == "signature_block"), None)

    # Mutable pool of unclaimed candidates, consumed as they are matched.
    #
    # `signature_block`-typed clauses are included here (unlike `preamble`,
    # which can never correspond to a named section): a trailing schedule
    # can legitimately type as `signature_block` when its hint family says
    # so (e.g. "Schedule D: Signature and Execution"), and such a clause
    # must still be matchable against its own named expected entry. The
    # generic `has_signature` presence check below (for the "signature"
    # sentinel entry) does not consume from this pool, so it cannot
    # conflict with a named section also matching the same physical clause.
    pool = [c for c in level1 if c.clause_type != "preamble"]

    out: list[SectionMatch] = []
    for sec in expected_sections:
        number = str(sec["number"])
        title = sec.get("title") or ""
        family = sec.get("clause_family")

        if number == "preamble":
            out.append(SectionMatch(number, title, family, has_preamble is not None, has_preamble))
            continue
        if number == "signature":
            out.append(SectionMatch(number, title, family, has_signature is not None, has_signature))
            continue

        exp_title_norm = _normalize_title(title)
        norm = _normalize_number(number)

        clause = None
        # Prefer an exact number match whose title isn't wildly wrong.
        candidates = [c for c in pool if c.section_number and _normalize_number(c.section_number) == norm]
        for c in candidates:
            if fuzz.token_sort_ratio(exp_title_norm, _normalize_title(c.title)) >= _TITLE_SANITY_MIN:
                clause = c
                break
        if clause is None and candidates:
            # Number matched but title sanity failed on every candidate;
            # still prefer the best-scoring one over no match at all, since
            # a hint-anchored clause's title is Extract's own wording and
            # may legitimately differ from the answer key's paraphrase.
            clause = max(candidates, key=lambda c: fuzz.token_sort_ratio(exp_title_norm, _normalize_title(c.title)))

        if clause is None:
            # Fall back to fuzzy title match (exhibits/schedules/annexes are
            # often anchored under a slightly different literal number).
            best = None
            best_score = 0.0
            for c in pool:
                score = fuzz.token_sort_ratio(exp_title_norm, _normalize_title(c.title))
                if score > best_score:
                    best_score = score
                    best = c
            if best is not None and best_score >= 75:
                clause = best

        if clause is not None:
            pool.remove(clause)
        out.append(SectionMatch(number, title, family, clause is not None, clause))

    return out


def _false_splits(result_clauses: list[Any], matches: list[SectionMatch]) -> int:
    level1 = [c for c in result_clauses if c.level == 1]
    matched_clause_ids = {id(m.found_clause) for m in matches if m.found_clause is not None}
    extras = [c for c in level1 if c.clause_type not in ("preamble", "signature_block") and id(c) not in matched_clause_ids]
    return len(extras)


# ---------------------------------------------------------------------------
# Per-contract evaluation
# ---------------------------------------------------------------------------


@dataclass
class ContractReport:
    contract_id: int
    file: str
    kind: str  # "docx" or "pdf"
    seconds: float = 0.0
    credits: float | None = None
    status: str = "ok"  # ok | no_text | invariant_error | extend_error
    error: str = ""
    field_outcomes: list[FieldOutcome] = field(default_factory=list)
    section_matches: list[SectionMatch] = field(default_factory=list)
    false_splits: int = 0
    typing_total: int = 0
    typing_correct: int = 0
    counterparty_expected: str | None = None
    counterparty_got: str | None = None
    counterparty_correct: bool | None = None
    warnings: tuple[str, ...] = ()


async def _run_one(
    client: ExtendClient,
    schema: dict,
    family_index: FamilyIndex,
    agreement_type_keys: list[str],
    contract_id: int,
    file_stem: str,
    data: bytes,
    filename: str,
    kind: str,
    expected: dict,
) -> ContractReport:
    report = ContractReport(contract_id=contract_id, file=file_stem, kind=kind)
    t0 = time.monotonic()
    try:
        file_id = await client.upload(filename, data)
        run = await client.extract(file_id, schema)
        blocks = await client.parse_output(run.parse_run_id)
    except Exception as exc:  # noqa: BLE001 - record and continue the corpus run
        report.status = "extend_error"
        report.error = f"{type(exc).__name__}: {exc}"
        report.seconds = time.monotonic() - t0
        return report

    report.seconds = time.monotonic() - t0
    usage = run.usage or {}
    # "credits" is the extract-only charge; "totalCredits" includes the
    # paired parse run, which we also consume via parse_output(). Use the
    # full figure for cost tracking.
    report.credits = usage.get("totalCredits") or usage.get("credits") or usage.get("creditsUsed")

    try:
        result = build_result(
            run.value,
            run.metadata,
            blocks,
            family_index=family_index,
            agreement_type_keys=agreement_type_keys,
            own_org_names=OWN_ORG_NAMES,
        )
    except NoTextError as exc:
        report.status = "no_text"
        report.error = str(exc)
        return report
    except InvariantError as exc:
        report.status = "invariant_error"
        # exc.args[0] is the formatted message *string* InvariantError's
        # own __init__ passes to super().__init__(); joining it with "; "
        # would join its characters, not its violations. Use the
        # violations list the exception actually carries.
        report.error = "; ".join(exc.violations) if exc.violations else str(exc)
        return report

    report.warnings = result.warnings

    # Fields
    for key in TIER1_KEYS:
        by_key = {fv.field_key: fv for fv in result.fields}
        outcome = _score_field(key, by_key, expected["fields"])
        report.field_outcomes.append(outcome)

    # Sections / typing / false splits
    expected_sections = expected["sections"]
    matches = _match_sections(list(result.clauses), expected_sections)
    report.section_matches = matches
    report.false_splits = _false_splits(list(result.clauses), matches)

    # typing accuracy: only count sections with a family in the taxonomy
    for m in matches:
        if not m.expected_family or m.expected_family not in family_index.keys:
            continue
        report.typing_total += 1
        if m.found and m.found_clause is not None and getattr(m.found_clause, "clause_type", None) == m.expected_family:
            report.typing_correct += 1

    # Counterparty
    report.counterparty_expected = expected.get("counterparty")
    cp = next((p for p in result.parties if p.role == "counterparty"), None)
    report.counterparty_got = cp.name if cp is not None else None
    if report.counterparty_expected is not None:
        report.counterparty_correct = _free_text_matches(
            report.counterparty_got or "", report.counterparty_expected
        )

    return report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(reports: list[ContractReport], family_index: FamilyIndex) -> None:
    """Print per-contract detail, then the plan section 2 marks.

    DOCX and PDF reports are scored separately: plan section 2's marks are
    about the corpus of real contracts, and pooling a PDF re-run of one
    contract in with the 12-contract DOCX corpus would double-count that
    contract. The PDF reports are printed as their own DOCX-vs-PDF
    comparison instead of folded into the aggregate.

    Section recall is judged **per document** (>=90% on every single
    contract), not as a pooled aggregate across contracts -- this matches
    how ``tests/unit/test_dp_pipeline_replay.py`` already reads the same
    mark for the four-case fixture. The aggregate is still printed, but
    labelled as a reference figure, not the mark itself.
    """
    print("\n" + "=" * 100)
    print("CORPUS RUN AGAINST LIVE EXTEND -- per-contract results")
    print("=" * 100)

    docx_reports = [r for r in reports if r.kind == "docx"]
    pdf_reports = [r for r in reports if r.kind == "pdf"]

    per_field_all: dict[str, list[bool]] = {k: [] for k in TIER1_KEYS}
    total_typing_total = 0
    total_typing_correct = 0
    total_anchored_with_family = 0  # denominator for the typing-on-anchored-only line
    total_counterparty_checked = 0
    total_counterparty_correct = 0
    total_credits = 0.0
    any_credits = False
    per_doc_recall: list[tuple[str, int, int]] = []  # (file, found, expected)

    for r in reports:
        print(f"\n--- contract {r.contract_id} ({r.file}, {r.kind}) ---")
        print(f"  status: {r.status}  seconds: {r.seconds:.1f}  credits: {r.credits}")
        if r.error:
            print(f"  error: {r.error}")
        if r.warnings:
            print(f"  warnings: {list(r.warnings)}")
        if isinstance(r.credits, (int, float)):
            total_credits += r.credits
            any_credits = True
        if r.status != "ok":
            continue

        matched = sum(1 for o in r.field_outcomes if o.matched)
        print(f"  fields: {matched}/{len(r.field_outcomes)} matched")
        for o in r.field_outcomes:
            if not o.matched:
                print(f"    MISS {o.key}: expected={o.expected!r} got={o.got!r} {o.note}")
            if r.kind == "docx":
                per_field_all[o.key].append(o.matched)

        exp_count = len(r.section_matches)
        found_count = sum(1 for m in r.section_matches if m.found)
        if r.kind == "docx":
            per_doc_recall.append((r.file, found_count, exp_count))
        print(f"  sections: {found_count}/{exp_count} found; false splits: {r.false_splits}")
        for m in r.section_matches:
            if not m.found:
                print(f"    NOT ANCHORED: {m.expected_number} {m.expected_title!r} (family={m.expected_family})")

        if r.kind == "docx":
            total_typing_total += r.typing_total
            total_typing_correct += r.typing_correct
            total_anchored_with_family += sum(
                1 for m in r.section_matches
                if m.found and m.expected_family and m.expected_family in family_index.keys
            )
        if r.typing_total:
            print(f"  typing: {r.typing_correct}/{r.typing_total}")

        if r.counterparty_correct is not None:
            if r.kind == "docx":
                total_counterparty_checked += 1
                total_counterparty_correct += int(r.counterparty_correct)
            print(
                f"  counterparty: expected={r.counterparty_expected!r} got={r.counterparty_got!r} "
                f"correct={r.counterparty_correct}"
            )

    print("\n" + "=" * 100)
    print("AGGREGATE -- plan section 2 marks (DOCX contracts only; PDF reported above, separately)")
    print("=" * 100)

    print(f"\nTier 1 field accuracy (across the {len(docx_reports)} DOCX contracts where the field is scored):")
    for key in sorted(per_field_all):
        outcomes = per_field_all[key]
        if not outcomes:
            print(f"  {key:35s}  no data")
            continue
        pct = sum(outcomes) / len(outcomes)
        mark = "MET" if pct >= 0.85 else "NOT MET"
        print(f"  {key:35s} {sum(outcomes):3d}/{len(outcomes):3d}  {pct:6.1%}  {mark}")

    print("\nSection recall -- PER DOCUMENT (the actual mark is >=90% on EVERY document):")
    below_90 = []
    total_found = total_exp = 0
    for file, found, exp in per_doc_recall:
        rate = found / exp if exp else 1.0
        total_found += found
        total_exp += exp
        tag = "OK" if rate >= 0.90 else "BELOW 90%"
        if rate < 0.90:
            below_90.append(file)
        print(f"  {file:48s} {found:3d}/{exp:<3d} = {rate:6.1%}  {tag}")
    agg_rate = total_found / total_exp if total_exp else 0.0
    print(f"  (aggregate across all DOCX contracts, reference only, NOT the mark itself: "
          f"{total_found}/{total_exp} = {agg_rate:.1%})")
    print(f"Section recall mark: {'MET' if not below_90 else 'NOT MET'} "
          f"({len(below_90)}/{len(per_doc_recall)} documents below 90%: {below_90})")

    total_false_splits = sum(r.false_splits for r in docx_reports)
    max_false_splits_per_doc = max((r.false_splits for r in docx_reports), default=0)
    print(f"\nFalse splits: {total_false_splits} total across {len(docx_reports)} DOCX contracts, "
          f"max {max_false_splits_per_doc} in any single document "
          f"(mark: at most 1 per document -> {'MET' if max_false_splits_per_doc <= 1 else 'NOT MET'})")

    typing_rate = total_typing_correct / total_typing_total if total_typing_total else 0.0
    print(f"\nClause typing accuracy: {total_typing_correct}/{total_typing_total} = {typing_rate:.1%} "
          f"({'MET' if typing_rate >= 0.85 else 'NOT MET'}, mark is >=85%)")
    if total_anchored_with_family:
        anchored_rate = total_typing_correct / total_anchored_with_family
        print(f"  (of which, restricted to sections that WERE anchored -- isolates clause_typing.py "
              f"from the sections.py/hinting gap above: {total_typing_correct}/{total_anchored_with_family} "
              f"= {anchored_rate:.1%})")

    if total_counterparty_checked:
        cp_rate = total_counterparty_correct / total_counterparty_checked
        print(f"\nCounterparty correct: {total_counterparty_correct}/{total_counterparty_checked} = {cp_rate:.1%}")

    if pdf_reports:
        print("\nPDF-path contracts (reported separately, not pooled into the marks above):")
        for r in pdf_reports:
            matched = sum(1 for o in r.field_outcomes if o.matched)
            found_count = sum(1 for m in r.section_matches if m.found)
            print(f"  {r.file}: fields {matched}/{len(r.field_outcomes)}, "
                  f"sections {found_count}/{len(r.section_matches)}, typing {r.typing_correct}/{r.typing_total}")

    failed = [r for r in reports if r.status != "ok"]
    print(f"\nFailures (not ok): {len(failed)}/{len(reports)}")
    for r in failed:
        print(f"  {r.file} ({r.kind}): {r.status} -- {r.error}")

    if any_credits:
        print(f"\nTotal credits used (where usage reported it): {total_credits:.1f}")
    else:
        print("\nTotal credits used: not reported by the API usage payload "
              "(see raw usage dicts printed per contract, if any).")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    env = dotenv_values(_ENV_PATH)
    api_key = env.get("EXTEND_API_KEY")
    if not api_key:
        print("EXTEND_API_KEY not found in backend/.env; aborting.", file=sys.stderr)
        sys.exit(1)

    family_index, agreement_type_keys = _load_taxonomy()

    from app.services.document_processing.fields import build_extract_schema

    schema = build_extract_schema(agreement_type_keys, sorted(family_index.keys))

    expected_doc = yaml.safe_load(_EXPECTED_PATH.read_text())
    expected_by_file = {c["file"]: c for c in expected_doc["contracts"]}

    docx_files = sorted(_DOCX_DIR.glob("*.docx"))
    assert len(docx_files) == 12, f"expected 12 seed docx files, found {len(docx_files)}"

    soffice = _find_soffice()
    pdf_tmp_dir = Path(tempfile.mkdtemp(prefix="dp_eval_pdf_"))
    pdf_jobs: list[tuple[str, Path]] = []
    if soffice is None:
        print("No LibreOffice/soffice found; PDF-path sub-task will be SKIPPED, reported as such.")
    else:
        for stem in _PDF_CASE_FILES:
            docx_path = _DOCX_DIR / f"{stem}.docx"
            pdf_path = _convert_to_pdf(soffice, docx_path, pdf_tmp_dir)
            if pdf_path is not None:
                pdf_jobs.append((stem, pdf_path))
            else:
                print(f"PDF conversion failed for {stem}; skipping its PDF-path run.")

    client = ExtendClient(
        api_key=api_key,
        base_url=_EXTEND_BASE_URL,
        extract_processor=_EXTRACT_PROCESSOR,
        extract_version=_EXTRACT_VERSION,
        parse_engine=_PARSE_ENGINE,
        parse_version=_PARSE_VERSION,
        poll_interval=_POLL_INTERVAL_SECONDS,
        timeout=_TIMEOUT_SECONDS,
    )

    reports: list[ContractReport] = []
    # Starts at 0 for every run of this script. On 2026-11-18, diagnosing
    # a schema bug that has since been fixed at the source in
    # fields.build_extract_schema cost an *additional* 67.2 credits before
    # this loop ever started: 4 live extract+parse runs on the 14-page
    # contract 01, each with a valid minimal schema that Extend accepted
    # and billed normally (a malformed schema -- the bug itself -- gets a
    # 400 and is never billed, confirmed live; only the probes built to
    # find and confirm the correct shape were billed). That 67.2 is
    # one-time, external to this script, and is reported separately in
    # document_processing_verification.md section 7 -- it must NOT be
    # hardcoded here, or every future run of this script would hit the
    # ceiling about 67 credits early for no reason.
    running_credits = 0.0

    try:
        for idx, docx_path in enumerate(docx_files, start=1):
            stem = docx_path.stem
            expected = expected_by_file.get(stem)
            if expected is None:
                print(f"No fields_expected.yaml entry for {stem}; skipping.", file=sys.stderr)
                continue
            data = docx_path.read_bytes()
            print(f"\n[{idx}/12] Uploading + extracting {stem} (docx) ...", flush=True)
            r = await _run_one(
                client, schema, family_index, agreement_type_keys,
                expected["id"], stem, data, docx_path.name, "docx", expected,
            )
            reports.append(r)
            if isinstance(r.credits, (int, float)):
                running_credits += r.credits
            print(f"  done in {r.seconds:.1f}s, status={r.status}, running credit estimate={running_credits:.1f}")
            if running_credits >= _COST_WARN_CREDITS:
                print(
                    f"WARNING: running credit estimate {running_credits:.1f} is approaching the "
                    f"{_COST_CEILING_CREDITS:.0f}-credit ceiling.",
                    file=sys.stderr,
                )
            if running_credits >= _COST_CEILING_CREDITS:
                print(
                    "STOPPING: credit ceiling reached; not issuing further Extract runs.",
                    file=sys.stderr,
                )
                break

        for stem, pdf_path in pdf_jobs:
            # Found live, 2026-11-18: the DOCX loop's ceiling check above
            # only guarded itself; without this check, the PDF loop would
            # keep issuing billed Extract runs after the ceiling had
            # already been reached by the DOCX corpus alone. (The first
            # live run of this script hit exactly that: the ceiling was
            # reached right as this loop started, and the process had to
            # be killed externally after one PDF run had already been
            # dispatched and billed -- see document_processing_verification.md
            # section 7.)
            if running_credits >= _COST_CEILING_CREDITS:
                print(
                    "STOPPING: credit ceiling already reached before the PDF-path "
                    "sub-task; skipping remaining PDF conversions.",
                    file=sys.stderr,
                )
                break
            expected = expected_by_file.get(stem)
            if expected is None:
                continue
            data = pdf_path.read_bytes()
            print(f"\nUploading + extracting {stem} (pdf) ...", flush=True)
            r = await _run_one(
                client, schema, family_index, agreement_type_keys,
                expected["id"], stem, data, pdf_path.name, "pdf", expected,
            )
            reports.append(r)
            if isinstance(r.credits, (int, float)):
                running_credits += r.credits
            print(f"  done in {r.seconds:.1f}s, status={r.status}, running credit estimate={running_credits:.1f}")
    finally:
        await client._client.aclose()

    _print_report(reports, family_index)

    print(f"\nPDF-path sub-task: {'completed, ' + str(len(pdf_jobs)) + ' contract(s)' if pdf_jobs else 'SKIPPED'}")
    print(f"Total estimated credits used: {running_credits:.1f}")


if __name__ == "__main__":
    asyncio.run(main())
