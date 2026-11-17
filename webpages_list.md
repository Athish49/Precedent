# Precedent — Marketing Site Plan (living doc)

The public/marketing site for `frontend_v2`. This supersedes the original reconciled plan; the sections below reflect what's actually built and the decisions that reshaped the remaining work.

## Guiding principles

- **Two axes, not one.** Separate **Products** (what the platform *does* — one per backend capability) from **Solutions** (who it's *for*). This is the biggest lever for feeling like a real enterprise (Salesforce / Ironclad / Harvey pattern).
- **Every page must earn its place with real, product-true content.** A page ships only if it carries material *not already on Home/Products* that is *(a)* **resonance** (a buyer sees their own workflow) or *(b)* **insight** (they learn something real). Persona-flavored restatement of features is not content — it reads as yapping and kills the enterprise feel.
- **Mechanics live on product pages; solutions pages link out to them** and spend their own real estate on pain + workflow + outcome. This is the anti-repetition guardrail.
- **Honesty guardrail.** Every claim traces to a real capability and must not imply a Non-Goal: no e-signature, no integrations, no SSO/auth, no multi-user collaboration, no counterparty portals. The product's thesis is **deterministic-first — *your* standards, from *your* paper** — not an invented legal-knowledge oracle. No page may claim regulatory expertise the product doesn't hold.
- **No Platform page (deliberate).** A standalone `/platform` "how it all fits" page would re-deliver, at length, what Home + Products + individual product pages already say — the exact repetition we're avoiding. The lifecycle/CLM narrative instead lives on the **Legal Ops** solution page.
- **Explicitly excluded:** Pricing, Integrations (a stated Non-Goal), and a standalone Platform page.

---

## Status snapshot

### ✅ Built

| Page | Route | Notes |
|---|---|---|
| Home / Landing | `/` | Full landing: hero, problem, capabilities, how-it-works, autonomous, deterministic, security, services, impact, testimonials, FAQ, CTA/footer |
| Products overview | `/products` | Scroll-lit alternating product journey |
| **9 product spotlights** | `/products/*` | contract-analysis, redlining, autonomous-review, drafting, playbooks, document-intelligence, repository, obligations, analytics — each driven by a `content/products/*.ts` data file through the shared `product-page.tsx` template |

The product-page engine (one dynamic template: hero → capabilities → spotlight → impact → catalog) is complete and is the model for the Solutions template below.

### ⬜ To build — see the curated Solutions plan and Tier 4 below.

---

## The Solutions layer — curated (this replaces the original 9-page Tier 3)

### Why it changed: the evidence

The original plan bet on **by-contract-type** pages (SaaS/MSA · NDA · DPA · HIPAA) as the strong axis, "grounded in real playbook practice-area routing." Checking the product (`content/products/playbooks.ts`) showed what practice-area routing actually is: a **routing-and-precedence mechanism** — Precedent detects which rule-sets apply (HIPAA/GDPR/MSA/NDA/DPA) and merges them in a fixed order — and the rules themselves are **seeded from the customer's own executed contracts**, not from a built-in regulatory library.

So the product deliberately does **not** carry deep per-area legal expertise. A `/solutions/dpa` page citing GDPR Art. 28 sub-processor flowdown, SCCs, and breach windows as if Precedent were a privacy-law oracle would be **inventing content the product doesn't have** — contradicting its deterministic-first thesis, and transparent to any domain expert.

**This inverts the original bet:** by-contract-type is the *weak* axis for this product; **by-team is the strong one**, because those pages describe workflows built from capabilities confirmed to be real.

### ✅ Build — 4 pages (by-team)

| Page | Route | The new thing it carries (not on any product page) |
|---|---|---|
| **Solutions overview** | `/solutions` | The hub. Absorbs the **In-house Legal** narrative as its primary persona. Includes a light "works across your paper — MSA · NDA · DPA · BAA" band linking to the Playbooks routing story (this is how the contract-type axis is represented). |
| **Legal Operations** | `/solutions/legal-ops` | The **lifecycle / CLM story** (kept off a Platform page) + playbook ownership, self-service rule CRUD, portfolio reporting. The natural home for the end-to-end narrative. |
| **Procurement & Sourcing** | `/solutions/procurement` | The **inbound / counterparty-paper** angle — reviewing paper you didn't write, at vendor-intake volume. Grounded in the real own-vs-counterparty-paper mode. A genuinely different pain than the drafting-first product framing. |
| **Sales / Deal Desk** | `/solutions/sales` | A **different buyer** (revenue org, not legal): speed-to-close, autonomous review + the hard-stop escalation gate as "self-serve with guardrails," unblocking deals without a legal bottleneck. |

### ✂️ Cut — with content re-homed (editorial decisions, not omissions)

- **In-house Legal** → folded into the Solutions overview as the primary persona. The whole site already speaks to them; a standalone page would restate the home page.
- **Compliance & Privacy** → folded into the **Obligations & Monitoring** product page (ongoing monitoring lives there) + a mention on the overview. A standalone page would need regulatory depth the product doesn't carry.
- **SaaS/MSA · NDA · DPA · HIPAA (all 4 by-contract-type)** → **not standalone pages.** Represented as the "works across your paper" band on the Solutions overview, linking to the Playbooks routing capability. Standalone regulatory-depth pages would force invented content; thin "we route the right rules" pages would just duplicate the Playbooks routing card.

### Shared Solutions template (the anti-yap engine)

One reusable template, structured so a page *cannot* just re-explain features:

1. **Persona hook** — their pain, in their language (not the product's).
2. **"What's actually hard about this"** — the specific, credible friction for this buyer.
3. **Before → after workflow** — a concrete day-in-the-life / scenario. *The page's own real estate.*
4. **How it plays out** — which capabilities apply, framed as outcomes, **linking out** to product pages for mechanics.
5. **Outcome band** — metrics that matter to *this* buyer.
6. **CTA.**

---

## Tier 4 — Trust, Company & Conversion (to build)

| Page | Route | Delivers |
|---|---|---|
| **Security & Trust** | `/security` | Honest posture: data handling, deterministic/auditable-by-design story, no-model-training commitment, model-usage transparency — **plus a "what we don't claim yet" block** (no SSO/tenancy/e-sign). Turns Non-Goals into a credibility signal. |
| **Company / About** | `/company` | Vision, the "why deterministic-first" founding thesis, audience (in-house counsel / legal ops), closing CTA. *(Nav already links here — currently 404.)* |
| **Resources** | `/resources` | Hub: Insights/blog, Guides (playbook-building, redline-stance), a contract-AI Glossary. A few flagship posts sell technical credibility cheaply. |
| **Customers** | `/customers` | 2–3 illustrative case studies with before/after metrics (placeholder-honest). |
| **Contact / Request a demo** | `/demo` | Two paths (book-a-demo form + general contact) and a "what happens next" 3-step so the form isn't a void. |

### Utility / footer
`/privacy`, `/terms`, `/changelog`, accessibility statement, `/sitemap`, and a **404**.

---

## Build priority (remaining work)

| Priority | Pages | Why |
|---|---|---|
| **Now** | Solutions overview + Legal Ops + Procurement + Sales; prune nav & footer to the 4 real Solutions links | The two-axis layer is what pushes this from "nice project" to "real enterprise"; it also fixes the currently-broken Solutions mega-menu (9 links → 404) and Company link |
| **Next** | Security & Trust, Company | Honest Security page + founding thesis round out credibility |
| **Polish** | Resources, Customers, Demo, legal/utility pages, 404 | Depth and completeness |

## Known cleanup implied by this plan

- **Nav mega-menu** (`components/nav.tsx`) currently lists **9 Solutions links** (5 team + 4 contract-type). Prune to the 4 real pages so the menu never points at 404s / thin pages.
- **Footer** (`components/landing/cta-footer.tsx`) Solutions column and most Company/Resources/legal links are `#` placeholders — wire up as those pages ship.
- **CTAs** ("Book a Demo" → `#`) should point to `/demo` once built.
