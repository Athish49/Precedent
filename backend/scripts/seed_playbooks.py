"""T-039 — Pre-built playbook templates for NDA, DPA, SaaS MSA, HIPAA, GDPR.

Run directly:
    python -m scripts.seed_playbooks

Idempotent: skips any playbook whose name already exists in the database.
Returns a mapping of {playbook_name: rules_created} for each template.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import playbook_repo

# ---------------------------------------------------------------------------
# Template data
# ---------------------------------------------------------------------------

_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "NDA Standard",
        "practice_area": "nda",
        "precedence": 10,
        "rules": [
            {
                "clause_type": "confidentiality",
                "preferred_language": (
                    "Each party shall hold the other party's Confidential Information in strict "
                    "confidence and shall not disclose it to any third party without prior written "
                    "consent, using at least the same degree of care as it uses to protect its own "
                    "confidential information, but no less than reasonable care."
                ),
                "acceptable_variations": [
                    "Receiving party protects Confidential Information with reasonable care.",
                    "Confidential Information disclosed only on a need-to-know basis.",
                ],
                "prohibited_terms": [
                    "perpetual disclosure rights",
                    "unlimited disclosure",
                    "waiver of confidentiality",
                    "no obligation of confidentiality",
                ],
                "required": True,
                "risk_weight": 9.0,
                "escalation_threshold": 7.0,
            },
            {
                "clause_type": "intellectual_property",
                "preferred_language": (
                    "All intellectual property rights in any materials exchanged under this "
                    "Agreement remain with the disclosing party. Nothing herein grants the "
                    "receiving party any license or right to use the disclosing party's IP "
                    "except as necessary to evaluate the Proposed Transaction."
                ),
                "acceptable_variations": [
                    "No IP rights are transferred by virtue of this Agreement.",
                    "Disclosure grants no license under any patent, trademark, or copyright.",
                ],
                "prohibited_terms": [
                    "all rights waived",
                    "unrestricted license",
                    "irrevocable license to all IP",
                ],
                "required": True,
                "risk_weight": 8.0,
                "escalation_threshold": 6.0,
            },
            {
                "clause_type": "term",
                "preferred_language": (
                    "This Agreement shall remain in effect for two (2) years from the Effective "
                    "Date, unless earlier terminated by either party upon thirty (30) days' "
                    "written notice. Confidentiality obligations shall survive termination for "
                    "five (5) years."
                ),
                "acceptable_variations": [
                    "This Agreement shall be effective for three (3) years.",
                    "Either party may terminate on 60 days' notice.",
                ],
                "prohibited_terms": [
                    "no termination right",
                    "perpetual and irrevocable term",
                ],
                "required": True,
                "risk_weight": 5.0,
                "escalation_threshold": None,
            },
            {
                "clause_type": "governing_law",
                "preferred_language": (
                    "This Agreement shall be governed by and construed in accordance with the "
                    "laws of the State of Delaware, without regard to its conflict of laws rules."
                ),
                "acceptable_variations": [
                    "Governed by the laws of New York.",
                    "Governed by the laws of California.",
                ],
                "prohibited_terms": [],
                "required": False,
                "risk_weight": 3.0,
                "escalation_threshold": None,
            },
            {
                "clause_type": "entire_agreement",
                "preferred_language": (
                    "This Agreement constitutes the entire agreement between the parties with "
                    "respect to the subject matter hereof and supersedes all prior discussions, "
                    "representations, and agreements."
                ),
                "acceptable_variations": [
                    "This Agreement supersedes prior oral or written agreements on this subject.",
                ],
                "prohibited_terms": [],
                "required": False,
                "risk_weight": 2.0,
                "escalation_threshold": None,
            },
        ],
    },
    {
        "name": "DPA Standard",
        "practice_area": "dpa",
        "precedence": 10,
        "rules": [
            {
                "clause_type": "data_protection",
                "preferred_language": (
                    "Processor shall process Personal Data only on documented instructions from "
                    "Controller and shall implement appropriate technical and organisational "
                    "measures to ensure a level of security appropriate to the risk, including "
                    "encryption, pseudonymisation, and access controls."
                ),
                "acceptable_variations": [
                    "Personal Data processed solely for purposes described in Annex I.",
                    "Processor shall maintain records of all processing activities.",
                ],
                "prohibited_terms": [
                    "unrestricted processing",
                    "no consent required",
                    "data retention unlimited",
                    "processing without authorization",
                    "no security measures required",
                ],
                "required": True,
                "risk_weight": 10.0,
                "escalation_threshold": 7.0,
            },
            {
                "clause_type": "audit",
                "preferred_language": (
                    "Controller shall have the right, upon reasonable notice and not more than "
                    "once per calendar year, to audit Processor's processing activities, "
                    "facilities, and records relevant to this Agreement, or to mandate an "
                    "independent audit at Processor's cost."
                ),
                "acceptable_variations": [
                    "Processor shall provide audit reports prepared by independent third parties.",
                    "Controller may request copies of relevant audit certifications.",
                ],
                "prohibited_terms": [
                    "no audit rights",
                    "audit rights waived",
                ],
                "required": True,
                "risk_weight": 7.0,
                "escalation_threshold": None,
            },
            {
                "clause_type": "compliance",
                "preferred_language": (
                    "Processor shall comply with all applicable data protection laws and "
                    "regulations, including but not limited to GDPR, and shall promptly notify "
                    "Controller of any actual or suspected Personal Data Breach within 24 hours "
                    "of becoming aware."
                ),
                "acceptable_variations": [
                    "Processor shall notify Controller of any Data Breach within 72 hours.",
                    "Processor shall maintain compliance with applicable privacy regulations.",
                ],
                "prohibited_terms": [
                    "no breach notification required",
                    "compliance optional",
                    "no regulatory obligation",
                ],
                "required": True,
                "risk_weight": 8.0,
                "escalation_threshold": 6.0,
            },
            {
                "clause_type": "governing_law",
                "preferred_language": (
                    "This Agreement shall be governed by the law of the European Union member "
                    "state in which the Controller is established, without prejudice to any "
                    "mandatory provisions of applicable data protection law."
                ),
                "acceptable_variations": [
                    "Governed by English law.",
                ],
                "prohibited_terms": [],
                "required": False,
                "risk_weight": 3.0,
                "escalation_threshold": None,
            },
            {
                "clause_type": "term",
                "preferred_language": (
                    "This Agreement shall remain in effect for the duration of the underlying "
                    "services agreement and shall terminate upon the cessation of all processing "
                    "of Personal Data by Processor."
                ),
                "acceptable_variations": [
                    "This DPA terminates when the main services agreement terminates.",
                ],
                "prohibited_terms": [],
                "required": True,
                "risk_weight": 5.0,
                "escalation_threshold": None,
            },
        ],
    },
    {
        "name": "SaaS MSA Standard",
        "practice_area": "saas_msa",
        "precedence": 10,
        "rules": [
            {
                "clause_type": "payment",
                "preferred_language": (
                    "Customer shall pay all Fees within thirty (30) days of the invoice date. "
                    "Fees are non-refundable except as expressly set out in this Agreement. "
                    "Overdue amounts shall accrue interest at 1.5% per month or the maximum "
                    "rate permitted by law, whichever is lower."
                ),
                "acceptable_variations": [
                    "Payment due within 45 days of invoice.",
                    "Net 30 payment terms apply.",
                ],
                "prohibited_terms": [
                    "fees refundable at customer's discretion",
                    "no interest on late payments",
                ],
                "required": True,
                "risk_weight": 6.0,
                "escalation_threshold": None,
            },
            {
                "clause_type": "indemnification",
                "preferred_language": (
                    "Each party shall indemnify, defend, and hold harmless the other party from "
                    "and against any third-party claims arising from the indemnifying party's "
                    "gross negligence, wilful misconduct, or material breach of this Agreement, "
                    "subject to the limitations set out in the Limitation of Liability clause."
                ),
                "acceptable_variations": [
                    "Provider shall indemnify Customer for IP infringement claims.",
                    "Mutual indemnification for breach of representations.",
                ],
                "prohibited_terms": [
                    "unlimited indemnification",
                    "indemnify for consequential damages",
                    "indemnify regardless of negligence",
                ],
                "required": True,
                "risk_weight": 8.0,
                "escalation_threshold": 6.5,
            },
            {
                "clause_type": "limitation_of_liability",
                "preferred_language": (
                    "In no event shall either party's aggregate liability exceed the fees paid "
                    "or payable in the twelve (12) months preceding the claim. Neither party "
                    "shall be liable for indirect, incidental, special, or consequential damages, "
                    "even if advised of their possibility."
                ),
                "acceptable_variations": [
                    "Liability capped at fees paid in the prior six months.",
                    "Total liability shall not exceed $[X].",
                ],
                "prohibited_terms": [
                    "no limitation on liability",
                    "unlimited liability",
                    "limitation of liability waived",
                    "liable for all damages whatsoever",
                ],
                "required": True,
                "risk_weight": 9.0,
                "escalation_threshold": 7.5,
            },
            {
                "clause_type": "termination",
                "preferred_language": (
                    "Either party may terminate this Agreement for convenience upon sixty (60) "
                    "days' written notice. Either party may terminate immediately upon written "
                    "notice if the other party materially breaches this Agreement and fails to "
                    "cure such breach within thirty (30) days of receiving written notice."
                ),
                "acceptable_variations": [
                    "Termination for cause on 14 days' notice to cure.",
                    "Either party may terminate with 90 days' notice.",
                ],
                "prohibited_terms": [
                    "no termination right",
                    "automatic renewal without cancellation right",
                ],
                "required": True,
                "risk_weight": 7.0,
                "escalation_threshold": None,
            },
            {
                "clause_type": "warranties",
                "preferred_language": (
                    "Provider warrants that the Service will perform materially in accordance "
                    "with the Documentation. EXCEPT AS EXPRESSLY PROVIDED, THE SERVICE IS "
                    "PROVIDED 'AS IS' AND PROVIDER DISCLAIMS ALL OTHER WARRANTIES, EXPRESS "
                    "OR IMPLIED, INCLUDING IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS "
                    "FOR A PARTICULAR PURPOSE."
                ),
                "acceptable_variations": [
                    "Provider warrants 99.9% monthly uptime for the Service.",
                ],
                "prohibited_terms": [
                    "absolute warranty of uninterrupted service",
                    "guaranteed 100% uptime",
                    "provider liable for all defects",
                ],
                "required": True,
                "risk_weight": 6.0,
                "escalation_threshold": None,
            },
            {
                "clause_type": "intellectual_property",
                "preferred_language": (
                    "Provider retains all right, title, and interest in the Service and related "
                    "IP. Customer retains all right, title, and interest in Customer Data. "
                    "Customer grants Provider a limited license to use Customer Data solely to "
                    "provide the Service."
                ),
                "acceptable_variations": [
                    "All pre-existing IP of each party remains with that party.",
                ],
                "prohibited_terms": [
                    "customer IP assigned to provider",
                    "provider owns all customer data",
                ],
                "required": True,
                "risk_weight": 8.0,
                "escalation_threshold": 6.0,
            },
            {
                "clause_type": "dispute_resolution",
                "preferred_language": (
                    "The parties shall attempt to resolve any dispute through good-faith "
                    "negotiations for thirty (30) days before initiating formal proceedings. "
                    "Any unresolved dispute shall be submitted to binding arbitration under "
                    "the AAA Commercial Arbitration Rules."
                ),
                "acceptable_variations": [
                    "Disputes resolved by mediation then arbitration.",
                    "Jurisdiction of courts of Delaware agreed.",
                ],
                "prohibited_terms": [],
                "required": False,
                "risk_weight": 4.0,
                "escalation_threshold": None,
            },
        ],
    },
    {
        "name": "HIPAA Standard",
        "practice_area": "hipaa",
        "precedence": 15,
        "rules": [
            {
                "clause_type": "data_protection",
                "preferred_language": (
                    "Business Associate shall implement administrative, physical, and technical "
                    "safeguards to protect the confidentiality, integrity, and availability of "
                    "PHI as required by 45 C.F.R. Part 164, Subpart C. Business Associate shall "
                    "encrypt all PHI in transit and at rest using NIST-approved encryption."
                ),
                "acceptable_variations": [
                    "Business Associate complies with all HIPAA Security Rule requirements.",
                    "PHI shall be protected with industry-standard encryption.",
                ],
                "prohibited_terms": [
                    "PHI may be disclosed without authorization",
                    "no encryption required",
                    "unlimited retention of PHI",
                    "PHI shared freely with subcontractors",
                    "de-identification not required",
                ],
                "required": True,
                "risk_weight": 10.0,
                "escalation_threshold": 7.0,
            },
            {
                "clause_type": "compliance",
                "preferred_language": (
                    "Business Associate shall comply with all applicable requirements of the "
                    "HIPAA Privacy Rule (45 C.F.R. Part 164, Subpart E) and Security Rule "
                    "(45 C.F.R. Part 164, Subpart C), and shall report any Breach of Unsecured "
                    "PHI to Covered Entity without unreasonable delay and in no case later than "
                    "60 calendar days after discovery."
                ),
                "acceptable_variations": [
                    "Business Associate reports Security Incidents to Covered Entity in 24 hours.",
                ],
                "prohibited_terms": [
                    "no breach notification obligation",
                    "HIPAA compliance optional",
                    "PHI use unrestricted",
                    "no BAA required",
                ],
                "required": True,
                "risk_weight": 9.0,
                "escalation_threshold": 7.5,
            },
            {
                "clause_type": "audit",
                "preferred_language": (
                    "Business Associate shall maintain documentation of its policies and "
                    "procedures as required by 45 C.F.R. § 164.316, and shall make such "
                    "documentation available to HHS or Covered Entity upon request. "
                    "Business Associate shall conduct and document annual risk assessments."
                ),
                "acceptable_variations": [
                    "Annual HIPAA risk assessments conducted and provided to Covered Entity.",
                ],
                "prohibited_terms": [
                    "audit rights waived",
                    "no documentation required",
                ],
                "required": True,
                "risk_weight": 8.0,
                "escalation_threshold": None,
            },
            {
                "clause_type": "confidentiality",
                "preferred_language": (
                    "Business Associate shall not use or disclose PHI other than as permitted "
                    "or required by this Agreement or as required by law, and shall ensure that "
                    "its agents and subcontractors agree to the same restrictions."
                ),
                "acceptable_variations": [
                    "PHI shall only be used to perform services under the main agreement.",
                ],
                "prohibited_terms": [
                    "PHI may be used for marketing without consent",
                    "no restriction on PHI use",
                ],
                "required": True,
                "risk_weight": 9.0,
                "escalation_threshold": 7.0,
            },
            {
                "clause_type": "termination",
                "preferred_language": (
                    "Upon termination of this Agreement, Business Associate shall, at the "
                    "direction of Covered Entity, return or destroy all PHI received from, "
                    "or created on behalf of, Covered Entity. Business Associate shall certify "
                    "in writing that all PHI has been returned or destroyed."
                ),
                "acceptable_variations": [
                    "PHI shall be returned to Covered Entity within 30 days of termination.",
                ],
                "prohibited_terms": [
                    "PHI retained indefinitely after termination",
                    "no return or destruction of PHI required",
                ],
                "required": True,
                "risk_weight": 6.0,
                "escalation_threshold": None,
            },
            {
                "clause_type": "indemnification",
                "preferred_language": (
                    "Business Associate shall indemnify and hold harmless Covered Entity from "
                    "and against any claims, losses, damages, or regulatory penalties arising "
                    "from Business Associate's breach of this Agreement or violation of "
                    "applicable HIPAA regulations."
                ),
                "acceptable_variations": [
                    "Business Associate shall indemnify Covered Entity for HIPAA violations.",
                ],
                "prohibited_terms": [
                    "no indemnification for HIPAA violations",
                    "Covered Entity indemnifies Business Associate for BA failures",
                ],
                "required": True,
                "risk_weight": 8.0,
                "escalation_threshold": 6.5,
            },
        ],
    },
    {
        "name": "GDPR Standard",
        "practice_area": "gdpr",
        "precedence": 15,
        "rules": [
            {
                "clause_type": "data_protection",
                "preferred_language": (
                    "Processor shall process Personal Data only on documented instructions from "
                    "Controller, shall ensure that persons authorised to process Personal Data "
                    "have committed themselves to confidentiality, and shall implement "
                    "appropriate technical and organisational measures required by Article 32 GDPR."
                ),
                "acceptable_variations": [
                    "Personal Data processing is limited to purposes specified in Annex I.",
                    "Processor implements measures consistent with ISO 27001 or equivalent.",
                ],
                "prohibited_terms": [
                    "data subject rights waived",
                    "no DPA required",
                    "transfers without adequate safeguards",
                    "no right to erasure",
                    "processing beyond original purpose without consent",
                    "personal data sold to third parties",
                ],
                "required": True,
                "risk_weight": 10.0,
                "escalation_threshold": 7.0,
            },
            {
                "clause_type": "compliance",
                "preferred_language": (
                    "Processor shall assist Controller in fulfilling its obligations under "
                    "Articles 32 to 36 GDPR, including data protection impact assessments, "
                    "and shall notify Controller without undue delay after becoming aware of "
                    "a Personal Data Breach, providing all information necessary for Controller "
                    "to comply with its Article 33 notification obligation within 72 hours."
                ),
                "acceptable_variations": [
                    "Processor provides breach notification to Controller within 24 hours.",
                    "Processor assists with DPIAs and consultation with supervisory authorities.",
                ],
                "prohibited_terms": [
                    "breach notification waived",
                    "GDPR compliance not applicable",
                    "supervisory authority access denied",
                ],
                "required": True,
                "risk_weight": 9.0,
                "escalation_threshold": 7.0,
            },
            {
                "clause_type": "audit",
                "preferred_language": (
                    "Processor shall make available to Controller all information necessary to "
                    "demonstrate compliance with Article 28 GDPR and shall allow for and "
                    "contribute to audits, including inspections, conducted by Controller or "
                    "a mandated auditor, subject to reasonable notice."
                ),
                "acceptable_variations": [
                    "Processor provides annual third-party audit reports to Controller.",
                    "Controller may audit Processor's processing activities on reasonable notice.",
                ],
                "prohibited_terms": [
                    "audit rights excluded",
                    "no audit access permitted",
                ],
                "required": True,
                "risk_weight": 7.0,
                "escalation_threshold": None,
            },
            {
                "clause_type": "governing_law",
                "preferred_language": (
                    "This Agreement is governed by the law of the EU member state in which "
                    "the Controller has its principal place of business. The parties submit "
                    "to the exclusive jurisdiction of the courts of that member state."
                ),
                "acceptable_variations": [
                    "Governed by German law with jurisdiction of Berlin courts.",
                    "Governed by Irish law with jurisdiction of Dublin courts.",
                ],
                "prohibited_terms": [],
                "required": True,
                "risk_weight": 5.0,
                "escalation_threshold": None,
            },
            {
                "clause_type": "notices",
                "preferred_language": (
                    "Any notices under this Agreement shall be in writing and delivered to "
                    "the data protection contacts specified by each party. The Processor "
                    "shall promptly notify Controller of any changes to its sub-processor list "
                    "and of any regulator inquiries regarding data processing under this Agreement."
                ),
                "acceptable_variations": [
                    "Notices sent by email to the designated DPO of each party.",
                ],
                "prohibited_terms": [],
                "required": True,
                "risk_weight": 6.0,
                "escalation_threshold": None,
            },
            {
                "clause_type": "termination",
                "preferred_language": (
                    "Upon termination, Processor shall, at Controller's choice, delete or return "
                    "all Personal Data to Controller, and delete existing copies unless "
                    "EU or member state law requires storage. Processor shall certify "
                    "deletion in writing within 30 days of termination."
                ),
                "acceptable_variations": [
                    "Personal Data deleted within 30 days of termination unless required by law.",
                ],
                "prohibited_terms": [
                    "Personal Data retained indefinitely after termination",
                    "no deletion obligation",
                ],
                "required": True,
                "risk_weight": 5.0,
                "escalation_threshold": None,
            },
        ],
    },
]

# ---------------------------------------------------------------------------
# Seed logic (callable from tests and from __main__)
# ---------------------------------------------------------------------------


async def seed_all(session: AsyncSession) -> dict[str, int]:
    """Seed all template playbooks into *session*.

    Returns a mapping of {playbook_name: rules_created}.
    Skips any playbook whose name already exists (idempotent).
    """
    existing = await playbook_repo.list_playbooks(session)
    existing_names = {pb.name for pb in existing}

    counts: dict[str, int] = {}
    for template in _TEMPLATES:
        name: str = template["name"]
        if name in existing_names:
            print(f"  skip {name!r} (already exists)")
            counts[name] = 0
            continue

        pb = await playbook_repo.create_playbook(
            session,
            name=name,
            practice_area=template["practice_area"],
            precedence=template["precedence"],
        )

        created = 0
        for rule_def in template["rules"]:
            rd = dict(rule_def)
            await playbook_repo.create_rule(
                session,
                playbook_id=pb.id,
                clause_type=rd.pop("clause_type"),
                preferred_language=rd.pop("preferred_language", ""),
                **rd,
            )
            created += 1

        await session.commit()
        print(f"  seeded {name!r} with {created} rules")
        counts[name] = created

    return counts


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


async def _main() -> None:
    from app.core.config import get_settings
    from app.db.base import get_session_factory, init_db

    settings = get_settings()
    init_db(settings.database_url)
    factory = get_session_factory()

    print("Seeding playbooks...")
    async with factory() as session:
        counts = await seed_all(session)

    total_rules = sum(counts.values())
    seeded = sum(1 for v in counts.values() if v > 0)
    skipped = len(counts) - seeded
    print(f"Done — {total_rules} rules created across {seeded} playbooks ({skipped} skipped).")


if __name__ == "__main__":
    asyncio.run(_main())
