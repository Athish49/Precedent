> Source: copied verbatim from `playbook_implementation.md` section 2 (repository root). Section numbers are those of the source document.

# 2. The company: Halcyon Care, Inc.

All playbook content is written from this company's point of view.

| Fact | Value |
|---|---|
| Entity | Halcyon Care, Inc., a Delaware corporation, headquartered in Boston, Massachusetts |
| EU entity | Halcyon Care Ireland Ltd, Dublin |
| Product | Halcyon Engage: patient engagement and care coordination software (appointment reminders, secure messaging, intake forms, care-plan tracking). Integrates with hospital record systems over HL7 FHIR |
| Model | Multi-tenant SaaS, annual subscription, invoiced annually in advance |
| Customers | About 310: US hospital systems and physician groups (HIPAA covered entities) and EU private clinic groups |
| Size | 430 employees; $72M annual recurring revenue; median contract $165k a year; largest $2.4M |
| Hosting | AWS `us-east-1` and `us-west-2` for US customers; `eu-west-1` for EU customers |
| Certifications | SOC 2 Type II, ISO 27001, HITRUST r2 |
| Insurance | Cyber and technology errors and omissions: $10M aggregate. General liability: $2M |
| Regulatory position | Business associate under HIPAA; processor under GDPR; controller only for its own account and billing data |
| Legal team | General Counsel; two commercial counsel; one privacy counsel (also data protection officer); two contracts managers |
| Buy side | Halcyon also buys software and services, mainly cloud, messaging and analytics vendors, some of which handle PHI as subcontractors |

## 2.1 Defined terms to use in clause language

| Context | Terms |
|---|---|
| SaaS MSA (Halcyon sells) | "Halcyon", "Customer", "Services", "Customer Data", "Documentation", "Order Form", "Fees", "Subscription Term" |
| DPA | "Processor" (Halcyon), "Controller", "Personal Data", "Sub-processor", "Data Subject" |
| HIPAA overlay | "Business Associate" (Halcyon), "Covered Entity", "PHI", "Subcontractor", "Breach" |
| Mutual NDA | "Disclosing Party", "Receiving Party", "Confidential Information", "Purpose" |
| Vendor MSA (Halcyon buys) | "Halcyon", "Vendor", "Services", "Halcyon Data", "Fees" |

## 2.2 Context dimensions

| Key | Values |
|---|---|
| `deal_value_band` | `standard` (under $100k a year), `mid` ($100k to $500k), `enterprise` ($500k to $1.5M), `strategic` (over $1.5M) |
| `counterparty_tier` | `tier_1` (large health system or public body), `tier_2` (regional group), `tier_3` (small practice or startup) |
| `data_sensitivity` | `none`, `personal_data`, `phi`, `special_category` |
| `region` | `us`, `eu`, `uk`, `other` |
| `regimes` | multi-value: `hipaa`, `gdpr` |

## 2.3 Approver roles

| Key | Function | Level | Response time |
|---|---|---|---|
| `contracts_manager` | legal | 1 | 8 hours |
| `deal_desk` | finance | 2 | 8 hours |
| `commercial_counsel` | legal | 2 | 24 hours |
| `privacy_counsel` | privacy | 2 | 24 hours |
| `security_lead` | security | 2 | 24 hours |
| `vp_sales` | sales | 3 | 24 hours |
| `vp_customer_success` | delivery | 3 | 24 hours |
| `cfo` | finance | 4 | 48 hours |
| `general_counsel` | legal | 4 | 48 hours |

## 2.4 Risk appetite

These are the anchor positions. Content authors must stay consistent with them and extend the same logic to issues not listed. Vendor side unless marked.

| Issue | Preferred | Still green | Yellow, and who approves | Red |
|---|---|---|---|---|
| Liability cap | 12 months of Fees | Up to 12 months | Up to 18 months: `commercial_counsel`. Up to 24: `general_counsel`. Strategic deals up to 36: `general_counsel` with `cfo` | Above the yellow limit, or uncapped |
| Data breach super-cap | 2× annual Fees | 2× | Up to 3×, never above $5M: `general_counsel` | Above 3× or $5M, or uncapped |
| Cap carve-outs | Fraud, wilful misconduct, payment obligations | Plus IP indemnity | Uncapped confidentiality breach excluding Customer Data: `general_counsel` | Uncapped data breach; uncapped "any breach" |
| Consequential damages | Mutual exclusion | Mutual with listed exceptions matching the carve-outs | One-way exclusion favouring Customer: `commercial_counsel` | Exclusion removed |
| Payment terms | Net 30 | Net 45 | Net 60: `deal_desk` | Beyond 60 days |
| Late fees | 1.5% a month | 1.0% a month | None: `deal_desk` | Customer set-off rights against Fees |
| Renewal price increase | Up to 7% | Capped at 5% | Fixed price for a multi-year term: `deal_desk` | Price lock over 3 years |
| Initial term | 36 months | 12 months or more | Under 12 months: `vp_sales` | Month-to-month |
| Auto-renewal | 12-month renewals, 60 days' notice | 30 days' notice | No auto-renewal: `vp_sales` | Customer may cancel a renewal after it starts, with refund |
| Termination for convenience (Customer) | None | None | After month 12, on 90 days' notice, no refund: `vp_sales` with `deal_desk` | Any time, with refund of prepaid Fees |
| Cure period | 30 days | 30 days | 15 days: `commercial_counsel` | Under 10 days, or none |
| Uptime | 99.9% monthly | 99.9% | 99.95%: `vp_customer_success` | 99.99% or higher |
| Service credits | Capped at 10% of monthly Fees; sole remedy | Up to 15% | Up to 25%: `vp_customer_success` | Above 25%, or not the sole remedy |
| Breach notification | Without undue delay, within 72 hours of confirmation | 48 hours | 24 hours: `security_lead` with `privacy_counsel` | Under 24 hours, or from "suspicion" |
| Sub-processors | General authorisation, 30 days' notice, right to object | 30 days | 60 days' notice: `privacy_counsel` | Prior written consent for each sub-processor |
| Audit by Customer | Annual, 30 days' notice, SOC 2 report first | Same | On-site audit at Customer's cost: `security_lead` | Unannounced or unlimited audits |
| Governing law | Delaware | New York, Massachusetts, California; Ireland or England and Wales for EU and UK deals | Other US states: `commercial_counsel` | Any other jurisdiction, unless `general_counsel` approves |
| Data residency | US data in US regions; EU data in the EU region | Same | Named single region: `security_lead` | Single-tenant or on-premises deployment |
| Insurance evidence | Certificate on request, limits as held | Additional insured on general liability | Cyber limit above $10M: `cfo` | Unlimited or "adequate to cover all losses" |
| IP indemnity | Third-party infringement claims against the Services | Same | Extends to combinations Halcyon specified: `commercial_counsel` | First-party indemnity for any breach of the agreement |
| Publicity | Halcyon may list Customer by name and logo | With prior written consent | No publicity right: `contracts_manager` | Customer may publicise Halcyon performance data |
| NDA term and survival | 2-year term, 3-year survival | Up to 5-year survival | Indefinite survival for trade secrets only: `contracts_manager` | Perpetual survival for all information |
| NDA residuals | No residuals clause | None | Unaided-memory residuals excluding source code and PHI: `commercial_counsel` | Broad residuals clause |
| **Buy side:** vendor liability cap | 24 months of fees, data breach uncapped | 24 months with 5× super-cap | 12 months with 3× super-cap: `commercial_counsel` | Under 12 months, or data breach inside the general cap |
| **Buy side:** vendor breach notice | 48 hours | 72 hours | Over 72 hours: `security_lead` | No commitment |

## 2.5 Global red lines

Twelve red lines apply to every playbook. Task 3.2 writes them in full.

1. Uncapped aggregate liability for Halcyon.
2. Most-favoured-customer or price-parity commitments.
3. Exclusivity or non-compete obligations on Halcyon.
4. Assignment or exclusive licence of Halcyon's pre-existing intellectual property.
5. Commitments to build features or meet roadmap dates not in the Documentation.
6. Liquidated damages or penalties beyond capped service credits.
7. Unilateral right for the counterparty to amend the agreement.
8. Source code escrow with release on anything other than insolvency or abandonment.
9. Unannounced or unlimited audit or system access.
10. Use of Customer Data to train third-party models, or sale of data, by any party.
11. Governing law or venue in a jurisdiction outside the approved and escalated lists.
12. Indemnity for the counterparty's own negligence or breach.
