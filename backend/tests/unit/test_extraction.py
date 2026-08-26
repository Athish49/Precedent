"""Unit tests for app.services.document_processing.extraction.

All tests use synthetic in-memory contract strings — no file I/O.
"""

from datetime import date

from app.services.document_processing.extraction import (
    ContractMetadataDTO,
    PartyDTO,
    extract_metadata,
)

# ── Synthetic contract fixtures ────────────────────────────────────────────────

FULL_CONTRACT = """\
SERVICE AGREEMENT

This Service Agreement ("Agreement") is entered into as of January 1, 2024,
by and between Acme Corporation, a Delaware corporation ("Service Provider"),
and Beta Enterprises LLC, a California limited liability company ("Client").

1. GOVERNING LAW
   This Agreement shall be governed by the laws of the State of Delaware.

2. LIABILITY
   The aggregate liability cap shall not exceed $500,000 (five hundred thousand USD).

3. NOTICE
   Either party may terminate this Agreement upon 30 days prior notice.

4. RENEWAL
   This Agreement shall automatically renew for successive one-year terms.

5. PAYMENT
   All invoices are due within Net 30 days of receipt.

6. TERM
   This Agreement expires on December 31, 2024.
"""

EMPTY_CONTRACT = "This is a simple document with no contract-specific fields."

DEDUPE_CONTRACT = """\
This Agreement is entered into between Acme Inc. (hereinafter "Provider")
and Acme, Inc. ("also Provider") for testing purposes.
"""


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_extract_metadata_returns_tuple() -> None:
    """extract_metadata must return a (ContractMetadataDTO, list[PartyDTO]) tuple."""
    result = extract_metadata(FULL_CONTRACT)
    assert isinstance(result, tuple)
    assert len(result) == 2
    metadata, parties = result
    assert isinstance(metadata, ContractMetadataDTO)
    assert isinstance(parties, list)
    assert all(isinstance(p, PartyDTO) for p in parties)


def test_extract_parties() -> None:
    """ORG entities from FULL_CONTRACT should include Acme Corporation and Beta Enterprises."""
    _, parties = extract_metadata(FULL_CONTRACT)
    normalized_names = {p.normalized_name for p in parties}
    # spaCy should pick up at least one known org
    assert len(parties) > 0, "Expected at least one party to be extracted"
    # Check that names expected from the contract appear (flexible matching)
    found_acme = any("acme" in n for n in normalized_names)
    assert found_acme, f"Expected 'acme' in parties; got {normalized_names}"


def test_party_deduplication() -> None:
    """'Acme Inc.' and 'Acme, Inc.' must deduplicate to a single normalized party."""
    _, parties = extract_metadata(DEDUPE_CONTRACT)
    acme_parties = [p for p in parties if "acme" in p.normalized_name]
    got = [p.normalized_name for p in acme_parties]
    assert len(acme_parties) == 1, f"Expected exactly 1 deduplicated Acme party; got {got}"
    assert acme_parties[0].normalized_name == "acme inc"


def test_extract_governing_law() -> None:
    """'governed by the laws of the State of Delaware' → governing_law containing 'Delaware'."""
    metadata, _ = extract_metadata(FULL_CONTRACT)
    assert metadata.governing_law is not None
    assert "Delaware" in metadata.governing_law, (
        f"Expected 'Delaware' in governing_law; got {metadata.governing_law!r}"
    )


def test_extract_effective_date() -> None:
    """'entered into as of January 1, 2024' → effective_date == date(2024, 1, 1)."""
    metadata, _ = extract_metadata(FULL_CONTRACT)
    assert metadata.effective_date == date(2024, 1, 1), (
        f"Expected date(2024, 1, 1); got {metadata.effective_date}"
    )


def test_extract_notice_period() -> None:
    """'30 days prior notice' → notice_period_days == 30."""
    metadata, _ = extract_metadata(FULL_CONTRACT)
    assert metadata.notice_period_days == 30


def test_extract_auto_renewal_true() -> None:
    """'shall automatically renew' → auto_renewal is True."""
    metadata, _ = extract_metadata(FULL_CONTRACT)
    assert metadata.auto_renewal is True


def test_extract_no_match_returns_none() -> None:
    """Empty/irrelevant text → key metadata fields are None or empty."""
    metadata, parties = extract_metadata(EMPTY_CONTRACT)
    assert metadata.effective_date is None
    assert metadata.expiry_date is None
    assert metadata.governing_law is None
    assert metadata.liability_cap is None
    assert metadata.notice_period_days is None
    assert metadata.auto_renewal is None
    assert metadata.payment_terms is None
    assert metadata.financial_fields == {}
    assert metadata.milestone_dates == []


def test_extract_liability_cap() -> None:
    """'liability cap shall not exceed $500,000 USD' → {value: 500000.0, currency: 'USD'}."""
    metadata, _ = extract_metadata(FULL_CONTRACT)
    assert metadata.liability_cap is not None
    assert metadata.liability_cap["value"] == 500_000.0
    assert metadata.liability_cap["currency"] == "USD"


def test_extract_payment_terms() -> None:
    """'Net 30' → payment_terms == 'Net 30'."""
    metadata, _ = extract_metadata(FULL_CONTRACT)
    assert metadata.payment_terms == "Net 30"


def test_extract_expiry_date() -> None:
    """'expires on December 31, 2024' → expiry_date == date(2024, 12, 31)."""
    metadata, _ = extract_metadata(FULL_CONTRACT)
    assert metadata.expiry_date == date(2024, 12, 31), (
        f"Expected date(2024, 12, 31); got {metadata.expiry_date}"
    )


def test_parties_in_metadata() -> None:
    """parties in ContractMetadataDTO must be list of dicts with 'name' and 'role' keys."""
    metadata, _ = extract_metadata(FULL_CONTRACT)
    assert isinstance(metadata.parties, list)
    for party in metadata.parties:
        assert "name" in party
        assert "role" in party
        assert party["role"] == "unknown"
