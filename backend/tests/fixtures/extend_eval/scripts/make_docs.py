"""Build synthetic test contracts with known answers. Usage: make_docs.py OUT_DIR"""
import json
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

TITLE = "MASTER SERVICES AGREEMENT"
PREAMBLE = (
    'This Master Services Agreement (the "Agreement") is entered into as of March 3, 2025 '
    '(the "Effective Date") by and between Halcyon Systems, Inc., a Delaware corporation with '
    'offices at 400 Harbor Street, Boston, Massachusetts 02110 ("Supplier"), and Northwind Retail '
    'Group LLC, an Ohio limited liability company with offices at 1200 Lakeshore Avenue, '
    'Cleveland, Ohio 44114 ("Customer").'
)

# (number, title, family, [paragraphs])
SECTIONS = [
    ("1", "Definitions", "definitions", [
        '"Confidential Information" means all non-public information disclosed by one party to the other, '
        "whether orally or in writing, that is designated as confidential or that reasonably should be understood to be confidential.",
        '"Services" means the hosted inventory analytics services described in Exhibit A.',
        '"Fees" means the amounts set out in the fee schedule in Section 4.',
    ]),
    ("2", "Services", "scope_of_services", [
        "Supplier shall provide the Services to Customer in accordance with this Agreement and each Order Form.",
        "(a) Supplier shall perform the Services in a professional and workmanlike manner.",
        "(b) Customer shall provide Supplier with the access and information reasonably required to perform the Services.",
    ]),
    ("3", "Term and Renewal", "term", [
        "This Agreement commences on the Effective Date and continues for an initial term of three (3) years.",
        "Thereafter, this Agreement shall automatically renew for successive renewal terms of twelve (12) months each, "
        "unless either party gives written notice of non-renewal at least",
        "90 days before the end of the then-current term.",
    ]),
    ("4", "Fees and Payment", "payment", [
        "Customer shall pay the Fees set out in the table below. Supplier shall invoice Customer annually in advance.",
        "__TABLE__",
        "All invoices are due and payable within forty-five (45) days after the invoice date. Late amounts accrue interest "
        "at 1.5% per month. Fees are exclusive of taxes.",
    ]),
    ("5", "Service Levels", "service_levels", [
        "Supplier shall make the Services available with a monthly uptime of at least 99.9%. Supplier shall respond to "
        "Severity 1 incidents within 2 hours.",
    ]),
    ("6", "Confidentiality", "confidentiality", [
        "Each party shall protect the other party's Confidential Information using at least reasonable care and shall not "
        "disclose it to any third party without the disclosing party's prior written consent.",
        "The obligations in this Section survive for five (5) years after termination or expiration of this Agreement.",
    ]),
    ("7", "Data Protection and Security", "data_protection", [
        "Supplier shall process personal data only in accordance with the Data Processing Agreement attached as Exhibit B "
        "and applicable law, including the GDPR where it applies.",
        "Supplier shall notify Customer of any confirmed security breach affecting Customer data within 72 hours.",
    ]),
    ("8", "Intellectual Property", "intellectual_property", [
        "Supplier retains all intellectual property rights in the Services. Customer retains all rights in Customer data. "
        "I. No rights are granted except as expressly set out in this Agreement.",
    ]),
    ("9", "Warranties and Disclaimer", "warranties", [
        "Supplier warrants that the Services will conform in all material respects to the documentation for a period of "
        "ninety (90) days from delivery.",
        "EXCEPT AS EXPRESSLY SET OUT IN THIS AGREEMENT, SUPPLIER DISCLAIMS ALL WARRANTIES, WHETHER EXPRESS OR IMPLIED, "
        "INCLUDING ANY WARRANTY OF MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.",
    ]),
    ("10", "Indemnification", "indemnification", [
        "Supplier shall defend and indemnify Customer against any third-party claim alleging that the Services infringe "
        "any patent, copyright or trade secret.",
        "(a) Customer shall give Supplier prompt written notice of the claim.",
        "(b) Supplier shall have sole control of the defence and settlement of the claim.",
        "30 days after receipt of notice, Supplier shall assume the defence of the claim.",
    ]),
    ("11", "Limitation of Liability", "limitation_of_liability", [
        "IN NO EVENT SHALL EITHER PARTY BE LIABLE FOR ANY INDIRECT, INCIDENTAL OR CONSEQUENTIAL DAMAGES.",
        "Each party's total aggregate liability arising out of this Agreement shall not exceed the greater of (i) the Fees "
        "paid or payable in the twelve (12) months preceding the claim and (ii) $500,000.",
        "The limitations in this Section do not apply to a party's fraud, gross negligence or wilful misconduct, or to a "
        "breach of Section 6 (Confidentiality).",
    ]),
    ("12", "Termination", "termination", [
        "Either party may terminate this Agreement for material breach if the breach is not cured within thirty (30) days "
        "after written notice.",
        "Customer may terminate this Agreement for convenience upon sixty (60) days' written notice to Supplier. Supplier "
        "has no right to terminate for convenience.",
    ]),
    ("13", "Governing Law and Disputes", "governing_law", [
        "This Agreement is governed by the laws of the State of New York, without regard to its conflict of laws rules.",
        "Any dispute arising out of this Agreement shall be resolved exclusively by the state and federal courts located in "
        "New York County, New York. The parties agree that arbitration shall not apply to any dispute under this Agreement.",
    ]),
    ("14", "General", "miscellaneous", [
        "Neither party may assign this Agreement without the prior written consent of the other party, except to a successor "
        "in a merger or sale of substantially all of its assets.",
        "Notices must be in writing and sent to the addresses set out above. Notices to Supplier must be marked for the "
        "attention of the Legal Department.",
        "This Agreement is the entire agreement between the parties and may be amended only in a writing signed by both "
        "parties. Neither party is liable for delay caused by a force majeure event.",
    ]),
]

FEE_TABLE = [("Item", "Annual Fee"), ("Platform subscription", "$210,000"), ("Premium support", "$40,000"),
             ("Total annual Fees", "$250,000")]
WITNESS = "IN WITNESS WHEREOF, the parties have executed this Agreement as of the Effective Date."
SIGS = [
    ["HALCYON SYSTEMS, INC.", "By: /s/ Dana Whitfield", "Name: Dana Whitfield", "Title: Chief Revenue Officer",
     "Date: March 1, 2025"],
    ["NORTHWIND RETAIL GROUP LLC", "By: /s/ Priya Raman", "Name: Priya Raman", "Title: General Counsel",
     "Date: March 3, 2025"],
]

ANSWERS = {
    "contract_type": "MSA",
    "title": "Master Services Agreement",
    "parties": [
        {"name": "Halcyon Systems, Inc.", "role_label": "Supplier", "entity_type": "corporation", "jurisdiction": "Delaware"},
        {"name": "Northwind Retail Group LLC", "role_label": "Customer", "entity_type": "limited liability company",
         "jurisdiction": "Ohio"},
    ],
    "signatories": [
        {"printed_name": "Dana Whitfield", "title": "Chief Revenue Officer", "party": "Halcyon Systems, Inc.",
         "signed_date": "2025-03-01"},
        {"printed_name": "Priya Raman", "title": "General Counsel", "party": "Northwind Retail Group LLC",
         "signed_date": "2025-03-03"},
    ],
    "effective_date": "2025-03-03",
    "expiry_date": "2028-03-03 (derived; not stated)",
    "initial_term_months": 36,
    "auto_renewal": True,
    "renewal_term_months": 12,
    "renewal_notice_days": 90,
    "governing_law": "New York",
    "dispute_resolution": "litigation",
    "dispute_venue": "New York County, New York",
    "liability_cap_amount": 500000,
    "liability_cap_basis": "greater of fees in prior 12 months and $500,000",
    "liability_exclusions": ["fraud", "gross negligence", "wilful misconduct", "breach of confidentiality"],
    "total_contract_value": 250000,
    "currency": "USD",
    "payment_terms_days": 45,
    "termination_for_convenience": True,
    "termination_for_convenience_party": "Customer only",
    "termination_notice_days": 60,
    "cure_period_days": 30,
    "assignment_allowed_without_consent": False,
    "confidentiality_period_years": 5,
    "warranty_period_days": 90,
    "sla_uptime_percent": 99.9,
    "sla_response_time_hours": 2,
    "breach_notification_hours": 72,
    "data_processing_agreement": True,
    "gdpr_applicable": True,
    "sections": [{"number": n, "title": t, "family": f} for n, t, f, _ in SECTIONS],
}


def add_table(d):
    t = d.add_table(rows=len(FEE_TABLE), cols=2)
    t.style = "Table Grid"
    for i, (a, b) in enumerate(FEE_TABLE):
        t.rows[i].cells[0].text = a
        t.rows[i].cells[1].text = b


def add_page_field(paragraph):
    run = paragraph.add_run()
    for tag, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if tag:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), tag)
        else:
            el = OxmlElement("w:instrText")
            el.text = text
        run._r.append(el)


def header_footer(d):
    s = d.sections[0]
    s.header.paragraphs[0].text = "Halcyon Systems, Inc. - Confidential"
    fp = s.footer.paragraphs[0]
    fp.add_run("MSA-2025-0147    Page ")
    add_page_field(fp)
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER


def signature(d):
    d.add_paragraph(WITNESS)
    for block in SIGS:
        for line in block:
            d.add_paragraph(line)
        d.add_paragraph("")


def styled(path):
    d = Document()
    header_footer(d)
    d.add_heading(TITLE, 0)
    d.add_paragraph(PREAMBLE)
    for n, title, _, paras in SECTIONS:
        d.add_heading(f"{n}. {title}", 1)
        for p in paras:
            add_table(d) if p == "__TABLE__" else d.add_paragraph(p)
    signature(d)
    d.save(path)


def unstyled(path):
    """Law-firm style: no heading styles, bold run-in headings."""
    d = Document()
    header_footer(d)
    p = d.add_paragraph()
    p.add_run(TITLE).bold = True
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.add_paragraph(PREAMBLE)
    for n, title, _, paras in SECTIONS:
        first = True
        for body in paras:
            if body == "__TABLE__":
                add_table(d)
                continue
            p = d.add_paragraph()
            if first:
                p.add_run(f"{n}. {title}. ").bold = True
                first = False
            if body.startswith('"'):
                term, rest = body.split('" ', 1)
                p.add_run(term + '"').bold = True
                p.add_run(" " + rest)
            else:
                p.add_run(body)
    signature(d)
    d.save(path)


styled(OUT / "msa_styled.docx")
unstyled(OUT / "msa_runin.docx")
(OUT / "answers.json").write_text(json.dumps(ANSWERS, indent=2))
print("wrote", sorted(p.name for p in OUT.iterdir()))
