# Individual Product Page — Template Spec (frozen)

One reusable, data-driven template that every product page uses. The canonical
implementation is **`/products/drafting`** (Drafting Studio) — it is frozen as the
reference. All layout, spacing, typography, and motion live in the shared
template; a product page is just a content object, so every page looks identical.

Modeled on Harvey's `/platform/agents`. Theme is ours: dark `#0a0a0a`, a
serif/sans mix (see type scale), boxy `rounded-lg` CTAs, gradient placeholder
mockups (swap for real screenshots later).

---

## Files (where things live)

| File | Role |
|---|---|
| `app/products/<slug>/page.tsx` | Thin route: SEO `metadata` + `<ProductPage data={…} />`. Only per-page thing. |
| `content/products/<slug>.ts` | **Pure data** — one `ProductPageData` object. |
| `components/products/detail/product-page.tsx` | Shell: renders sections in order; optional ones gate on data. |
| `components/products/detail/sections.tsx` | **All** layout, spacing, grid, type, animation, sticky-stacking, carousel. |
| `components/products/detail/types.ts` | The `ProductPageData` contract. |
| `app/globals.css` | Shared tokens: `.tx-h1…h4`, `.tx-lead/.tx-body`, `.page-container`, `.cap-stack-item`, `.reveal`. |

### To add a new product page
1. Create `content/products/<slug>.ts` exporting a `ProductPageData`.
2. Create `app/products/<slug>/page.tsx` with `metadata` + `<ProductPage data={…} />`.

No component or CSS edits needed — the look is guaranteed identical.

---

## Design system (shared)

**Layout — `.page-container`:** `max-width: 1728px`, gutters `28 → 32 → 36 → 40px`
(sm→md→lg→xl). A **12-column grid** (`gap 18px`); content is inset to **columns 2–11**.

**Type scale** (Harvey sizes, our fonts):

| Class | Font | Size (base→md→lg) | Used for |
|---|---|---|---|
| `.tx-h1` | serif, lh 1.05 | 48 → 72 → 80px | hero headline, stat numbers |
| `.tx-h2` | serif, lh 1.05 | 36 → 48 → 56px | spotlight title |
| `.tx-h3` | serif, lh 1.05 | 28 → 32 → 36px | testimonial quote |
| `.tx-h4` | **sans, 500**, lh 1.1 | 28 → 32 → 40px | section leads, capability block titles, impact heading |
| `.tx-lead` | sans, lh 1.3 | 20px | hero pitch, card blurb, section intro, spotlight tagline |
| `.tx-body` | sans, lh 1.3 | 16px | sub-points, catalog descriptions, stat labels, testimonial meta |
| `text-2xl` | sans, 500 | 24px | catalog list items |

Rule of thumb: **serif = display moments** (hero, spotlight title, stat numbers,
testimonial quote). **Sans-medium = section/block headings.**

**CTA button (`DemoButton`):** `h-12 px-5 rounded-lg`, white fill, medium. Label
"Request a Demo", links to `/home`.

**Motion:** hero fade-up (`Reveal`); hero image fade + scale-in; capability blocks
sticky-stack + mockup rise-from-bottom; stat count-up; testimonial auto-swipe;
catalog click-swap. All respect `prefers-reduced-motion`.

---

## Sections (order + intent + current build)

The story arc: **what is this + why care → show me → how it works → prove it →
where it fits → let's talk.**

### 0 — Nav / CTA footer (shared site chrome)
`Nav` at top, `CtaFooter` at bottom. Not part of the template file.

### 1 — Hero  `ProductHero`
- Breadcrumb `Products / [name]` (muted, small), tight to the nav.
- **Headline** (`tx-h1`, serif) in **cols 2–6** — catchy, benefit-led, 3–6 words.
- **Pitch + CTA** in **cols 8–11, bottom-aligned** (`self-end`): one concise
  declarative line (`tx-lead`, ~10–13 words) + the Request a Demo button.
- Data: `hero.headline`, `hero.pitch`.

### 2 — Hero image  `ProductHeroImage`
- Large 16:9 framed mockup, inset to **cols 2–11**, fades + scales in on scroll.
- Data: `heroImage.gradient` (placeholder), `heroImage.label` (future alt text).

### 3 — Capability deep-dive  `CapabilityCards`  ← the core section
- **Section lead** (half-width): `sectionTitle` (`tx-h4`) + `sectionIntro` (`tx-lead`).
- **Sticky-stacking blocks:** each block pins at the same offset (top 88px) with a
  solid background; the next block slides up and **covers the previous one, which
  stays fixed underneath** (Harvey's ValueProps effect). Desktop only.
- Each block = **header** (title `tx-h4` left half + blurb `tx-lead` right ~40%,
  hairline on top) then **content** (mockup left half, rises in on scroll +
  **2–3 sub-points** right ~40%: each `title` (`tx-body` medium) + `desc`).
- **Flexible: 3–5 cards.** Data: `capabilities.{sectionTitle, sectionIntro, cards[]}`.

### 4 — Feature spotlight  `Spotlight`  *(optional)*
- Rounded raised panel: mockup left, centered on right → `kicker` (uppercase eyebrow)
  + `title` (`tx-h2`, serif) + `tagline` (`tx-lead`). Rises in on scroll.
- Harvey's "Introducing Memory" moment. Data: `spotlight` (omit to skip).

### 5 — Impact + proof  `ImpactMetrics`  *(optional)*
- Raised band. **Heading** (`tx-h4`) left cols 2–5; **3 stats** right cols 7–11,
  each a big serif number (`tx-h1`, **count-up on scroll**) + label, hairline-separated.
  First stat is top-aligned with the heading.
- **Testimonial carousel** directly below (compact — metrics + testimonial share one
  viewport): attribution (name/role/firm) left + serif quote (`tx-h3`) right,
  auto-advancing right→left every 6s, with clickable dots.
- Data: `impact.{heading, stats[], testimonials[]}` (omit to skip).

### 6 — "In action" catalog  `InActionCatalog`  *(optional)*
- Pure-black band. **No heading.** Left (cols 2–6): a list of modes/scenarios
  (`text-2xl`); **click** an item to switch (active is bright + reveals its `desc`,
  rest dimmed). Right (cols 8–11): the mockup swaps to match, **top-aligned** with
  the list. Data: `catalog.items[]` (omit to skip).

> Mockups everywhere are **gradient placeholder panels with no on-image text**;
> the `label`/`mockupLabel` fields are retained only for future alt text.

---

## Data contract (`ProductPageData`)

```ts
{
  slug: string;
  name: string;                         // breadcrumb label
  hero:      { headline; pitch };
  heroImage: { label; gradient };
  capabilities: {
    sectionTitle; sectionIntro;
    cards: { title; blurb; mockupLabel; gradient;
             points: { title; desc }[] }[];   // 3–5 cards, 2–3 points each
  };
  spotlight?: { kicker; title; tagline; mockupLabel; gradient };
  impact?:    { heading;
                stats: { prefix?; value: number; suffix?; label }[];  // value = count-up target
                testimonials: { quote; name; role; firm }[] };
  catalog?:   { items: { name; desc; mockupLabel; gradient }[] };
}
```

Optional sections (`spotlight`, `impact`, `catalog`) render only when present —
**length is flexible per product; drop any that lack meaningful content.**

### Content conventions (decided)
- **Metrics** — use impressive **placeholder** numbers now (swap when real data exists).
- **Testimonials** — **placeholder** attributed quotes for now.
- **Catalog** — adapt its meaning per product (flag types / drafting modes / search
  types / etc.).
- **Pitch** — keep to ~10–13 words, declarative "[Product] does X and returns Y".

---

## Per-product content map (grounded in the backend, S1–S9)

Slugs match the nav. `/products/drafting` is built; the rest follow the same template.

### 1. Drafting Studio  `/products/drafting`  (S4) — **built**
- **Hero:** "Never start from a blank page." — first drafts, clauses, memos in minutes.
- **Cards:** cost-tiered cascade (playbook → frequency → LLM) · first-draft documents
  from templates + variables · precedent-matched drafting · memos & action letters.
- **Spotlight:** "The Drafting Cascade" (playbook first, then your language, then AI).
- **Metrics:** drafting time ↓, % served from your own language, boilerplate time ↓.
- **Catalog:** Single-clause rewrite · New document from template · Precedent-matched clause · Memo/letter.

### 2. Playbooks & Standards  `/products/playbooks`  (S6)
- **Hero:** "Your standards, enforced on every deal."
- **Cards:** one-time AI bootstrap from your corpus · self-service rule CRUD ·
  practice-area routing (HIPAA/GDPR/MSA/NDA/DPA) · feeds analysis + redlining.
- **Catalog:** Preferred · Acceptable variations · Prohibited · Fallback language.

### 3. Contract Analysis  `/products/contract-analysis`  (S2)
- **Hero:** "Every risk, surfaced in seconds."
- **Cards:** deterministic structural gate before AI · paper-origin-aware analysis ·
  severity-weighted scoring (never averaged) · character-level citations.
- **Catalog:** Missing clause · Prohibited term · Non-standard · High-risk · Vague/inconsistent.

### 4. Redlining & Negotiation  `/products/redlining`  (S3 + NMS)
- **Hero:** "Redlines that remember how you negotiate."
- **Cards:** bundled suggestion (replacement + alternatives + explanation + comment) ·
  Negotiation Memory patterns per counterparty · stance modes · fallback toggle + refine.
- **Catalog:** Preferred position · Alternatives · Rationale · Counterparty comment · Refine.

### 5. Autonomous Review  `/products/autonomous-review`  (Review Pipeline)
- **Hero:** "Routine review, handled end to end."
- **Cards:** event-triggered pipeline · hard-stop gate · semi-autonomous auto-apply
  with rationale · every decision logged to memory.
- **Catalog:** Auto-apply · Escalate · Hard-stops · Audit trail.

### 6. Document Intelligence  `/products/document-intelligence`  (S5)
- **Hero:** "Ask any contract anything."
- **Cards:** cited Q&A (reads the clause array) · risk-aware summaries · Easy Prompt
  (NL → structured action) · Chat2 web research.
- **Catalog:** Q&A · Summarize · Redline summary · Easy Prompt · Research · Navigate.

### 7. Repository & Search  `/products/repository`  (S7)
- **Hero:** "Every contract, searchable to the clause."
- **Cards:** faceted + full-text search · Smart Search (NL → filters + semantic) ·
  version & amendment linking · redline history per clause type.
- **Catalog:** Keyword · Faceted · Smart Search · Versions · Redline history.

### 8. Obligations & Monitoring  `/products/obligations`  (S8)
- **Hero:** "Never miss a deadline or renewal again."
- **Cards:** obligation extraction at ingest · deterministic daily monitor ·
  bundled renewal rec + compliance check · on-demand compliance.
- **Catalog:** Deadline alerts · Renewal recs · Compliance checks · Acknowledgements.

### 9. Analytics & Reporting  `/products/analytics`  (S9)
- **Hero:** "Your whole portfolio at a glance."
- **Cards:** portfolio risk (severity-weighted) · contract-value tracking · tabular
  review with NL columns · renewal dashboard.
- **Catalog:** Intelligence · Portfolio risk · Value · Tabular · Renewals.
