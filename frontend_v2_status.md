# frontend_v2 — Status Report (as of 2026-11-15)

Scope: `frontend_v2/` only (the new frontend). Old frontend is `frontend/` (has a real app UI, not part of this effort).

## Summary
- **Marketing site**: in progress, not complete.
- **Application (dashboard) site**: not started in `frontend_v2` (no `/app`, `/dashboard` routes, no app route group at all).

## Marketing site — pages built

| Group | Page | Route | Copy | Visuals |
|---|---|---|---|---|
| Landing | Home | `/` | Real | Placeholder (gradient `Mockup` boxes + DOM-built mockups in `components/landing/mockups.tsx`; `public/` has only `bg.png`) |
| Products overview | Products | `/products` | Real | Placeholder |
| Products (template) | Contract Analysis | `/products/contract-analysis` | Real | Placeholder |
| | Redlining & Negotiation | `/products/redlining` | Real | Placeholder |
| | Autonomous Review | `/products/autonomous-review` | Real | Placeholder |
| | Drafting Studio | `/products/drafting` | Real | Placeholder |
| | Playbooks & Standards | `/products/playbooks` | Real | Placeholder |
| | Document Intelligence | `/products/document-intelligence` | Real | Placeholder |
| | Repository & Search | `/products/repository` | Real | Placeholder |
| | Obligations & Monitoring | `/products/obligations` | Real | Placeholder |
| | Analytics & Reporting | `/products/analytics` | Real | Placeholder |
| Solutions overview | Solutions | `/solutions` | Real | Placeholder |
| Solutions (template) | Legal Operations | `/solutions/legal-ops` | Real | Placeholder |
| | Procurement & Sourcing | `/solutions/procurement` | Real | Placeholder |
| | Sales / Deal Desk | `/solutions/sales` | Real | Placeholder |

**Visuals note**: every "image" slot across Landing/Products/Solutions is a CSS-gradient placeholder div (code comment: *"Swap for a real `<Image />` later"*), not a screenshot or real app DOM mockup. No actual product screenshots exist anywhere in `frontend_v2`.

**Copy note**: all content (`content/products/*.ts`, `content/solutions/*.ts`) is real, product-specific, non-lorem. No TODO/FIXME/"coming soon" strings found.

## Marketing site — pages NOT built
- `/security` (Security & Trust)
- `/company` (About) — **nav already links here → 404**
- `/resources` (Blog/Guides/Glossary hub)
- `/customers` (case studies)
- `/demo` (contact / request-a-demo form)
- Utility: `/privacy`, `/terms`, `/changelog`, accessibility statement, `/sitemap`, custom 404

## Known broken/placeholder wiring
- Footer "Company" and "Resources" columns → all `href="#"`.
- Footer bottom links (Privacy, Terms, Security) → `href="#"`.
- Every "Book a Demo" CTA (hero, FAQ, footer) → `href="#"`.
- Nav "Company" link → points to `/company`, which doesn't exist (404).

## Application (dashboard) pages
- **Not started in `frontend_v2`.** No app/dashboard route group exists.
- A real reference implementation of the application UI exists in the **old** `frontend/` project: `app/(app)/*` with home, drafting, repository, contracts, playbooks, counterparties, automations, obligations, analytics, settings. Useful as a functional/content reference when building the new application UI, not as code to reuse directly.

## For the next agent
- Marketing: swap placeholder gradient mockups for real visuals/screenshots; build the 5 missing Tier-4 pages; wire up all `#` links.
- Application: build from scratch in `frontend_v2`; old `frontend/app/(app)/*` shows what pages/features are expected.
