"""Build the synthetic contract corpus DOCX files (task 5.2).

Reads the plain-text/markdown source contracts under
``seed/contracts/data/halcyon/source/`` and writes one DOCX file per source
file under ``seed/contracts/data/halcyon/docx/``, using ``python-docx``.

Run as:

    python -m seed.contracts.build

This is pure content tooling: it reads and writes files under
``backend/seed/`` only, and does not touch the database, the object store or
any file outside the seed folder. It does not import from ``app`` and is not
imported by ``app`` (see playbook_implementation.md section 3.0).

Source lines that are HTML comments (``<!-- ... -->``) are authoring-only
annotations - e.g. notes about why a clause deviates from Halcyon's standard
position, or about a clause that a template intentionally omits - and are
skipped entirely: they are never written into the DOCX body, so a review of
the rendered contract never sees the answer key for its own deviations.

Documents are ingested through the live Extend Parse+Extract pipeline
(``document_processing_plan.md`` section 5), not through a heading-detection
heuristic of our own, so the formatting choices here matter for a different
reason than they used to: they make the corpus look and structure itself
like a real, numbered contract, the way Extend's Parse step expects to see
one. A line starting with decimal numbering (``1.``, ``1.1``, ``2.3.4``) or
written in full capital letters is given the Word "Heading 1" or "Heading 2"
paragraph style, matching how a real contract template is normally typed.
This gives Extend's parser two independent signals to find the same
heading — the DOCX paragraph style and the numbered/capitalised text itself
— so the corpus exercises the pipeline's section-detection logic (task 2.3)
the same way a real uploaded contract would, on both signals, however the
file is read.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from docx import Document
from docx.shared import Pt

SOURCE_DIR = Path(__file__).parent / "data" / "halcyon" / "source"
DOCX_DIR = Path(__file__).parent / "data" / "halcyon" / "docx"

# Top-level numbered heading: "1.", "1 ", "12." etc. followed by a space and
# text, with no further dot-number after the first segment.
_RE_TOP_HEADING = re.compile(r"^\s*\d+\.\s+\S")
# Sub-heading: "1.1", "2.3" etc.
_RE_SUB_HEADING = re.compile(r"^\s*\d+\.\d+(\.\d+)*\s+\S")
# A line that is entirely capital letters (ignoring punctuation/digits/spaces)
# and at least 4 characters long, e.g. "MASTER SUBSCRIPTION AGREEMENT".
_RE_ALL_CAPS = re.compile(r"^[A-Z0-9 ,.'()/&-]{4,}$")


def _classify(line: str) -> str:
    """Return ``"h1"``, ``"h2"`` or ``"body"`` for a non-empty source line."""
    stripped = line.strip()
    if _RE_SUB_HEADING.match(stripped):
        return "h2"
    if _RE_TOP_HEADING.match(stripped):
        return "h1"
    if _RE_ALL_CAPS.match(stripped) and any(c.isalpha() for c in stripped):
        return "h1"
    return "body"


def build_docx(source_path: Path, output_path: Path) -> int:
    """Convert one source text file to a DOCX file.

    Returns the number of paragraphs written (for reporting / sanity checks).
    """
    text = source_path.read_text(encoding="utf-8")
    document = Document()

    # Keep the default body font modest so page-count stays in the 6-15 page
    # range the task asks for; this has no effect on parsing, only on how
    # the file looks if opened in Word.
    style = document.styles["Normal"]
    style.font.size = Pt(11)

    paragraph_count = 0
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("<!--") and line.endswith("-->"):
            # Authoring-only annotation (e.g. "<!-- Deviation 1 of 4: ... -->"
            # or "<!-- Gap Note: ... -->"). These are notes for whoever
            # maintains the source contract about why a clause reads the way
            # it does, or about a clause that is intentionally absent. They
            # must never reach the rendered contract text, since a model
            # reviewing the DOCX is supposed to find these facts on its own
            # rather than read the answer key. Skip entirely: not written as
            # a paragraph and not counted.
            continue
        kind = _classify(line)
        if kind == "h1":
            document.add_heading(line, level=1)
        elif kind == "h2":
            document.add_heading(line, level=2)
        else:
            document.add_paragraph(line)
        paragraph_count += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(output_path))
    return paragraph_count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the source files that would be converted, without writing any DOCX file.",
    )
    args = parser.parse_args()

    if not SOURCE_DIR.is_dir():
        raise SystemExit(f"Source directory not found: {SOURCE_DIR}")

    source_files = sorted(SOURCE_DIR.glob("*.md"))
    if not source_files:
        raise SystemExit(f"No source contracts found under {SOURCE_DIR}")

    if args.dry_run:
        for source_path in source_files:
            output_path = DOCX_DIR / (source_path.stem + ".docx")
            print(f"would write {output_path} from {source_path.name}")
        print(f"\n{len(source_files)} source contract(s) would be built (--dry-run, nothing written)")
        return

    DOCX_DIR.mkdir(parents=True, exist_ok=True)

    total = 0
    for source_path in source_files:
        output_path = DOCX_DIR / (source_path.stem + ".docx")
        count = build_docx(source_path, output_path)
        total += 1
        print(f"wrote {output_path.relative_to(DOCX_DIR.parent.parent.parent.parent)} "
              f"({count} paragraphs)")

    print(f"\n{total} DOCX file(s) written to {DOCX_DIR}")


if __name__ == "__main__":
    main()
