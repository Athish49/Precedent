import type { ProductPageData } from '@/components/products/detail/types';

// Redlining & Negotiation — maps to backend Service 3 + Negotiation Memory Store.
export const redliningNegotiation: ProductPageData = {
  slug: 'redlining',
  name: 'Redlining & Negotiation',

  hero: {
    headline: 'Redlines that remember how you negotiate.',
    pitch: 'Precedent turns flagged clauses into surgical redlines and returns counterparty-ready comments.',
  },

  heroImage: {
    label: 'Redlining & Negotiation — tracked-change editor mockup',
    gradient: 'linear-gradient(135deg, #10b981, #14b8a6, #0ea5e9)',
  },

  capabilities: {
    sectionTitle: 'Close deals faster, on your terms',
    sectionIntro:
      'Every flagged clause comes back as a clean tracked change — replacement text, alternatives, rationale, and a comment your counterparty can read — so review turns into a decision, not a rewrite.',
    cards: [
      {
        title: 'One suggestion, fully assembled',
        blurb:
          'For each flagged clause, Precedent returns a single bundled edit — replacement language plus everything you need to send it, defend it, and fall back if needed.',
        mockupLabel: 'Bundled suggestion — replacement + alternatives + rationale + comment',
        gradient: 'linear-gradient(135deg, #10b981, #0ea5e9)',
        points: [
          {
            title: 'Replacement plus alternatives',
            desc: 'You get the preferred replacement text and 2–3 alternative phrasings, so you can pick the wording that fits the deal.',
          },
          {
            title: 'Plain-language rationale',
            desc: 'A short explanation says why the edit matters — no legalese, ready to share with the business.',
          },
          {
            title: 'Counterparty-ready comment',
            desc: 'A negotiation comment ships with every redline, so you can send the markup without drafting the ask from scratch.',
          },
        ],
      },
      {
        title: 'Shaped by how they settle',
        blurb:
          'The Negotiation Memory Store reads how this counterparty has closed similar clauses before and tunes each suggestion to what actually lands.',
        mockupLabel: 'Negotiation Memory — acceptance rates + last-closed language',
        gradient: 'linear-gradient(135deg, #14b8a6, #06b6d4)',
        points: [
          {
            title: 'Acceptance rates per position',
            desc: 'Precedent knows how often each fallback position has been accepted by this counterparty and leads with what tends to stick.',
          },
          {
            title: 'Last-closed language',
            desc: 'Suggestions anchor to the exact wording you last agreed on with them, so you stop re-litigating settled ground.',
          },
          {
            title: 'Every deal makes the next smarter',
            desc: 'Each accept or reject you make is logged, so the memory sharpens with every negotiation.',
          },
        ],
      },
      {
        title: 'Dial the pressure',
        blurb:
          'A stance mode governs how hard Precedent pushes — set Light, Balanced, or Firm to match the relationship and the leverage.',
        mockupLabel: 'Stance modes — Light / Balanced / Firm',
        gradient: 'linear-gradient(135deg, #059669, #0284c7)',
        points: [
          {
            title: 'Light to Firm',
            desc: 'Choose how aggressively suggestions push, from conciliatory to protective, in one control.',
          },
          {
            title: 'Consistent posture',
            desc: 'The whole document redlines to one negotiating stance, so your position stays coherent across every clause.',
          },
        ],
      },
      {
        title: 'Adjust on the fly',
        blurb:
          'Swap to your fallback language in one click, or refine any redline with a plain instruction — Precedent re-diffs instantly.',
        mockupLabel: 'Fallback toggle + refine on your instruction',
        gradient: 'linear-gradient(135deg, #0d9488, #0ea5e9)',
        points: [
          {
            title: 'Preferred ↔ fallback toggle',
            desc: 'Flip between preferred and fallback wording with a single toggle and the tracked changes re-render immediately.',
          },
          {
            title: 'Refine with an instruction',
            desc: 'Tell Precedent what to change in plain language and it revises the redline over as many passes as you need.',
          },
          {
            title: 'Surgical by design',
            desc: 'A non-interference check keeps edits scoped to the flagged spans — the rest of the document stays untouched.',
          },
        ],
      },
    ],
  },

  spotlight: {
    kicker: 'Every deal makes the next one smarter',
    title: 'Negotiation Memory',
    tagline:
      'Precedent learns each counterparty’s patterns — what they accept, where they push back, and the language you last closed on — so your redlines arrive pre-tuned to what actually gets signed.',
    mockupLabel: 'Negotiation Memory Store — counterparty patterns',
    gradient: 'linear-gradient(135deg, #047857, #0891b2, #0ea5e9)',
  },

  impact: {
    heading: 'Negotiation, by the numbers',
    stats: [
      { value: 6, suffix: '×', label: 'faster to a sendable redline' },
      { value: 85, suffix: '%', label: 'of edits accepted as first drafted' },
      { value: 40, suffix: '%', label: 'fewer negotiation rounds per deal' },
    ],
    testimonials: [
      {
        quote:
          'The redline comes back with the ask already written and the fallback ready to go. We stopped drafting comments and started making decisions — deals close a round or two sooner.',
        name: 'Priya Nandakumar',
        role: 'Director, Commercial Contracts',
        firm: 'Meridian',
      },
      {
        quote:
          'It remembers how each counterparty settles, so we lead with what they actually accept instead of guessing. Every negotiation leaves the next one sharper.',
        name: 'Elliot Vance',
        role: 'Associate General Counsel',
        firm: 'Coriolis',
      },
    ],
  },

  catalog: {
    items: [
      {
        name: 'Preferred position',
        desc: 'Lead with your strongest replacement language, tuned to how this counterparty has settled the clause before.',
        mockupLabel: 'Preferred position',
        gradient: 'linear-gradient(135deg, #10b981, #0ea5e9)',
      },
      {
        name: 'Alternative language',
        desc: 'Choose from 2–3 alternative phrasings when the preferred wording needs to flex to the deal.',
        mockupLabel: 'Alternative language',
        gradient: 'linear-gradient(135deg, #14b8a6, #06b6d4)',
      },
      {
        name: 'Plain-language rationale',
        desc: 'See a short, jargon-free explanation of why the edit matters, ready to share with the business.',
        mockupLabel: 'Plain-language rationale',
        gradient: 'linear-gradient(135deg, #059669, #0284c7)',
      },
      {
        name: 'Counterparty comment',
        desc: 'Send the markup with a negotiation comment already drafted for the other side to read.',
        mockupLabel: 'Counterparty comment',
        gradient: 'linear-gradient(135deg, #0d9488, #0ea5e9)',
      },
      {
        name: 'Refine with an instruction',
        desc: 'Adjust any redline with a natural-language instruction and Precedent re-diffs over multiple passes.',
        mockupLabel: 'Refine with an instruction',
        gradient: 'linear-gradient(135deg, #047857, #0891b2)',
      },
    ],
  },
};
