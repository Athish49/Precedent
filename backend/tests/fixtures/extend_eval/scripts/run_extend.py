"""Send test docs to Extend. Usage: run_extend.py DOCS_DIR OUT_DIR KEY_FILE tier file [file...]
tier = light | performance. Saves raw JSON responses to OUT_DIR."""
import json
import sys
import time
from pathlib import Path

import httpx

DOCS, OUT, KEY_FILE, TIER = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
FILES = sys.argv[5:]
OUT.mkdir(parents=True, exist_ok=True)
H = {"Authorization": f"Bearer {KEY_FILE.read_text().strip()}", "x-extend-api-version": "2026-02-09"}
BASE = "https://api.extend.ai"
c = httpx.Client(headers=H, timeout=120)

S, N, B, I = ["string", "null"], ["number", "null"], ["boolean", "null"], ["integer", "null"]
FAMILIES = ["definitions", "scope_of_services", "term", "payment", "service_levels", "confidentiality",
            "data_protection", "intellectual_property", "warranties", "indemnification", "limitation_of_liability",
            "termination", "governing_law", "dispute_resolution", "assignment", "notices", "force_majeure",
            "insurance", "miscellaneous", "other", None]
SCHEMA = {
    "type": "object",
    "properties": {
        "contract_type": {"type": S, "enum": ["MSA", "NDA", "SOW", "DPA", "SaaS", "other", None]},
        "title": {"type": S, "description": "Title of the agreement as written at the top of the document"},
        "parties": {"type": "array", "description": "The legal entities that are parties to the agreement. Not individuals, not courts, not states.",
                    "items": {"type": "object", "properties": {
                        "name": {"type": S, "description": "Full legal name"},
                        "role_label": {"type": S, "description": "Defined term used for this party, e.g. Supplier, Customer"},
                        "entity_type": {"type": S, "description": "e.g. corporation, limited liability company"},
                        "jurisdiction": {"type": S, "description": "State or country of organisation"},
                        "address": {"type": S}}}},
        "signatories": {"type": "array", "description": "People who signed, from the signature block",
                        "items": {"type": "object", "properties": {
                            "printed_name": {"type": S}, "title": {"type": S},
                            "party_name": {"type": S, "description": "Legal entity the person signed for"},
                            "is_signed": {"type": B},
                            "signed_date": {"type": S, "extend:type": "date"}}}},
        "effective_date": {"type": S, "extend:type": "date"},
        "expiry_date": {"type": S, "extend:type": "date", "description": "Only if an explicit end date is stated. Do not compute."},
        "initial_term_months": {"type": I},
        "auto_renewal": {"type": B},
        "renewal_term_months": {"type": I},
        "renewal_notice_days": {"type": I, "description": "Days of notice required to prevent renewal"},
        "governing_law": {"type": S, "description": "Jurisdiction only, e.g. New York"},
        "dispute_resolution": {"type": S, "enum": ["litigation", "arbitration", "mediation", None],
                               "description": "The mechanism that actually applies. If arbitration is excluded, do not answer arbitration."},
        "dispute_venue": {"type": S},
        "liability_cap_amount": {"type": N, "description": "Fixed monetary cap, if any number is stated"},
        "liability_cap_basis": {"type": S, "description": "How the cap is defined, in a short phrase"},
        "liability_exclusions": {"type": "array", "items": {"type": "string"},
                                 "description": "Carve-outs to which the liability cap does not apply"},
        "total_contract_value": {"type": N, "description": "Total annual fees"},
        "currency": {"type": S, "description": "ISO 4217 code"},
        "payment_terms_days": {"type": I, "description": "Days after invoice by which payment is due"},
        "termination_for_convenience": {"type": B},
        "termination_for_convenience_party": {"type": S, "description": "Which party or parties may terminate for convenience"},
        "termination_notice_days": {"type": I, "description": "Notice for termination for convenience"},
        "cure_period_days": {"type": I},
        "assignment_allowed_without_consent": {"type": B},
        "confidentiality_period_years": {"type": I},
        "warranty_period_days": {"type": I},
        "sla_uptime_percent": {"type": N},
        "sla_response_time_hours": {"type": N},
        "breach_notification_hours": {"type": I},
        "data_processing_agreement": {"type": B},
        "gdpr_applicable": {"type": B},
        "clauses": {"type": "array", "description": "Every top-level numbered section of the agreement, in order. Do not include sub-clauses.",
                    "items": {"type": "object", "properties": {
                        "section_number": {"type": S}, "title": {"type": S},
                        "family": {"type": S, "enum": FAMILIES}}}},
    },
}


def post(path, **kw):
    r = c.post(BASE + path, **kw)
    if r.status_code >= 400:
        print("  ERROR", path, r.status_code, r.text[:600])
        return None
    return r.json()


def poll(path, label):
    t0 = time.time()
    while True:
        r = c.get(BASE + path)
        if r.status_code >= 400:
            print("  ERROR GET", path, r.status_code, r.text[:400])
            return None, time.time() - t0
        j = r.json()
        if j.get("status") in ("PROCESSED", "FAILED", "CANCELLED"):
            print(f"  {label}: {j['status']} in {time.time() - t0:.0f}s", j.get("failureReason") or "",
                  "usage:", json.dumps(j.get("usage"))[:200])
            return j, time.time() - t0
        if time.time() - t0 > 600:
            print("  timeout", label)
            return j, time.time() - t0
        time.sleep(3)


for name in FILES:
    stem = f"{Path(name).stem}_{Path(name).suffix[1:]}_{TIER}"
    print("==", name, TIER)
    with open(DOCS / name, "rb") as fh:
        up = post("/files/upload", files={"file": (name, fh)})
    if not up:
        continue
    fid = up["id"]
    print("  file", fid, up.get("type"))

    # 1. standalone parse
    pr = post("/parse_runs", json={"file": {"id": fid}, "config": {
        "engine": f"parse_{TIER}", "target": "markdown", "chunkingStrategy": {"type": "document"},
        "blockOptions": {"tables": {"targetFormat": "markdown"}}}})
    if pr:
        pj, _ = poll(f"/parse_runs/{pr['id']}", "parse")
        (OUT / f"{stem}_parse.json").write_text(json.dumps(pj, indent=1))

    # 2. extract
    er = post("/extract_runs", json={"file": {"id": fid}, "config": {
        "baseProcessor": f"extraction_{TIER}", "parseConfig": {"engine": f"parse_{TIER}"},
        "schema": SCHEMA, "advancedOptions": {"citationsEnabled": True}}})
    if er:
        ej, _ = poll(f"/extract_runs/{er['id']}", "extract")
        (OUT / f"{stem}_extract.json").write_text(json.dumps(ej, indent=1))
        prid = (ej or {}).get("parseRunId")
        if prid:
            r = c.get(f"{BASE}/parse_runs/{prid}")
            print("  parse run via extract's parseRunId:", prid, "->", r.status_code,
                  "chunks" if r.status_code == 200 and (r.json().get("output") or {}).get("chunks") else r.text[:200])
            if r.status_code == 200:
                (OUT / f"{stem}_extract_parse.json").write_text(json.dumps(r.json(), indent=1))
