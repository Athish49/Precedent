"""Invariant checks for IngestResult (plan section 7.5, points 1–6).

Points 7–9 are database-level and belong to ingest.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.document_processing.fields import validate_value

if TYPE_CHECKING:
    from app.services.document_processing.types import IngestResult


class InvariantError(Exception):
    """Raised when one or more invariants are violated."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__(
            f"{len(violations)} invariant violation(s): " + "; ".join(violations)
        )


def check_result(
    result: "IngestResult",
    family_keys: frozenset[str],
    registry: dict,  # dict[str, FieldDef] from fields.py
) -> list[str]:
    """Return a list of violation strings.  Empty list means all pass.

    Never raises on malformed input – missing or None values are reported
    as violations instead.
    """
    violations: list[str] = []

    # ------------------------------------------------------------------
    # Guard: result must be usable
    # ------------------------------------------------------------------
    if result is None:
        violations.append("result is None")
        return violations

    document = getattr(result, "document", None)
    text: str = ""
    if document is None:
        violations.append("result.document is None")
    else:
        text = getattr(document, "text", None) or ""

    clauses = getattr(result, "clauses", ()) or ()
    fields = getattr(result, "fields", ()) or ()

    # ------------------------------------------------------------------
    # Invariant 1: canonical_text[char_start:char_end] == clause.text
    # ------------------------------------------------------------------
    for clause in clauses:
        try:
            start = clause.char_start
            end = clause.char_end
            expected = clause.text
            if text[start:end] != expected:
                violations.append(f"clause {clause.ordinal}: text slice mismatch")
        except Exception:
            violations.append(f"clause {clause.ordinal}: text slice mismatch")

    # ------------------------------------------------------------------
    # Invariant 2: level-1 clauses ordered, non-overlapping, covering
    # ------------------------------------------------------------------
    try:
        level1 = sorted(
            [c for c in clauses if getattr(c, "level", None) == 1],
            key=lambda c: c.ordinal,
        )
        if level1:
            # First must start at 0
            if level1[0].char_start != 0:
                violations.append(
                    f"level-1 clauses: overlap or gap at ordinal {level1[0].ordinal}"
                )
            # Last must end at len(text)
            if level1[-1].char_end != len(text):
                violations.append(
                    f"level-1 clauses: overlap or gap at ordinal {level1[-1].ordinal}"
                )
            # Adjacent pairs: no overlap, only whitespace gap
            for prev, curr in zip(level1, level1[1:]):
                if curr.char_start < prev.char_end:
                    # overlap
                    violations.append(
                        f"level-1 clauses: overlap or gap at ordinal {curr.ordinal}"
                    )
                elif text[prev.char_end : curr.char_start].strip() != "":
                    # non-whitespace gap
                    violations.append(
                        f"level-1 clauses: overlap or gap at ordinal {curr.ordinal}"
                    )
    except Exception:
        violations.append("level-1 clauses: error checking order/coverage")

    # ------------------------------------------------------------------
    # Invariant 3: child clause lies inside parent's range
    # ------------------------------------------------------------------
    ordinal_map = {c.ordinal: c for c in clauses}
    for clause in clauses:
        try:
            parent_ordinal = clause.parent_ordinal
            if parent_ordinal is None:
                continue
            parent = ordinal_map.get(parent_ordinal)
            if parent is None:
                violations.append(
                    f"clause {clause.ordinal}: outside parent range"
                )
                continue
            if not (
                parent.char_start <= clause.char_start
                and clause.char_end <= parent.char_end
            ):
                violations.append(
                    f"clause {clause.ordinal}: outside parent range"
                )
        except Exception:
            violations.append(f"clause {clause.ordinal}: outside parent range")

    # ------------------------------------------------------------------
    # Invariant 4: clause_type validity; preamble/signature_block ≤ 1
    # ------------------------------------------------------------------
    allowed_types = family_keys | frozenset({"preamble", "signature_block"})
    preamble_count = 0
    sig_count = 0
    for clause in clauses:
        try:
            ct = clause.clause_type
            if ct not in allowed_types:
                violations.append(
                    f"clause {clause.ordinal}: unknown clause_type '{ct}'"
                )
            if ct == "preamble":
                preamble_count += 1
                if preamble_count > 1:
                    violations.append("duplicate preamble")
            elif ct == "signature_block":
                sig_count += 1
                if sig_count > 1:
                    violations.append("duplicate signature_block")
        except Exception:
            violations.append(f"clause {clause.ordinal}: unknown clause_type")

    # ------------------------------------------------------------------
    # Invariant 5: field keys in registry; value has registered type
    # ------------------------------------------------------------------
    for field in fields:
        try:
            key = field.field_key
            if key not in registry:
                violations.append(f"field {key}: unknown key")
                continue
            field_def = registry[key]
            value = field.value
            result_val = validate_value(field_def, value)
            if result_val is None and value is not None:
                violations.append(f"field {key}: invalid value")
        except Exception as exc:
            try:
                violations.append(f"field {field.field_key}: invalid value")
            except Exception:
                violations.append("field <unknown>: invalid value")

    # ------------------------------------------------------------------
    # Invariant 6: when field has offsets, text[start:end] == quote
    # ------------------------------------------------------------------
    for field in fields:
        try:
            start = field.char_start
            end = field.char_end
            if start is None or end is None:
                continue
            quote = field.quote
            if text[start:end] != quote:
                violations.append(f"field {field.field_key}: quote offset mismatch")
        except Exception:
            violations.append(f"field {field.field_key}: quote offset mismatch")

    return violations
