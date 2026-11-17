import type { ProductPageData } from '@/components/products/detail/types';

// Drafting Studio — maps to backend Service 4 (Drafting).
export const draftingStudio: ProductPageData = {
  slug: 'drafting',
  name: 'Drafting Studio',

  hero: {
    headline: 'Never start from a blank page.',
    pitch: 'Precedent drafts from your own playbook and returns polished, review-ready language.',
  },

  heroImage: {
    label: 'Drafting Studio — editor mockup',
    gradient: 'linear-gradient(135deg, #6366f1, #8b5cf6, #d946ef)',
  },

  capabilities: {
    sectionTitle: 'Get more drafted with less effort',
    sectionIntro:
      'Your team’s hours go to strategy and negotiation while Precedent turns intent into a clean, review-ready draft in the background.',
    cards: [
      {
        title: 'One clause, your way',
        blurb:
          'Ask for any clause and Precedent returns your preferred language — reusing what already works before it ever writes something new.',
        mockupLabel: 'Clause cascade — playbook → frequency → AI',
        gradient: 'linear-gradient(135deg, #4f46e5, #7c3aed)',
        points: [
          {
            title: 'Playbook first',
            desc: 'If your playbook has a preferred clause for that type, you get it verbatim — deterministic, no model in the loop.',
          },
          {
            title: 'Then your most-used language',
            desc: 'No playbook entry? Precedent reuses the most common version from your last-N similar contracts, scoped by matter.',
          },
          {
            title: 'AI only as a last resort',
            desc: 'Only genuinely novel asks reach the model — keeping output consistent, fast, and inexpensive.',
          },
        ],
      },
      {
        title: 'A full first draft, on demand',
        blurb:
          'Turn a template and a handful of variables into a complete, formatted document — ready to open in the editor and refine.',
        mockupLabel: 'Document builder — template + variables',
        gradient: 'linear-gradient(135deg, #6366f1, #06b6d4)',
        points: [
          {
            title: 'Deterministic template engine',
            desc: 'Variables fill into your own templates exactly — no hallucinated structure, no surprises.',
          },
          {
            title: 'Optional AI polish',
            desc: 'Ask Precedent to smooth conditional clauses on demand — you decide when the model gets involved.',
          },
        ],
      },
      {
        title: 'Drafted from precedent',
        blurb:
          'Match the style of agreements you’ve already signed — Precedent searches your corpus and drafts in that voice.',
        mockupLabel: 'Precedent match — corpus vector search',
        gradient: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
        points: [
          {
            title: 'Search your own paper',
            desc: 'Vector search over your repository surfaces the closest precedent clauses to build from.',
          },
          {
            title: 'Style-matched generation',
            desc: 'The draft inherits the tone and structure of your executed agreements, not a generic template.',
          },
        ],
      },
      {
        title: 'Memos and letters, drafted',
        blurb:
          'Go beyond contracts — produce action letters and legal memos from a short prompt, grounded in the matter at hand.',
        mockupLabel: 'Memo drafting — action letter',
        gradient: 'linear-gradient(135deg, #a855f7, #6366f1)',
        points: [
          {
            title: 'Prompt to draft',
            desc: 'Describe what you need and get a structured, review-ready memo or letter in one pass.',
          },
          {
            title: 'Grounded in context',
            desc: 'Drafts pull from the contract and metadata already in Precedent, so references stay accurate.',
          },
        ],
      },
    ],
  },

  spotlight: {
    kicker: 'Under the hood',
    title: 'The Drafting Cascade',
    tagline:
      'Your playbook comes first, then your most-used language, then the model — so every draft is consistent, fast, and unmistakably yours.',
    mockupLabel: 'Cascade — playbook → frequency → AI',
    gradient: 'linear-gradient(135deg, #4338ca, #7c3aed, #c026d3)',
  },

  impact: {
    heading: 'Drafting, by the numbers',
    stats: [
      { value: 8, suffix: '×', label: 'faster to a first draft' },
      { value: 70, suffix: '%', label: 'of clauses served from your own language' },
      { value: 90, suffix: '%', label: 'less time spent on boilerplate' },
    ],
    testimonials: [
      {
        quote:
          'We stopped writing from scratch. Precedent hands us a draft that already reads like our house style, and we spend our time on the two clauses that actually matter.',
        name: 'Dana Whitfield',
        role: 'VP, Commercial Legal',
        firm: 'Northwind',
      },
      {
        quote:
          'The cascade is the trick — most of what comes back is our own approved language, so review is trivial. It feels less like AI writing and more like our playbook writing itself.',
        name: 'Marcus Lee',
        role: 'Head of Legal Operations',
        firm: 'Aperture',
      },
    ],
  },

  catalog: {
    items: [
      {
        name: 'Single-clause rewrite',
        desc: 'Rewrite or replace one clause on a natural-language prompt, drawing from your playbook and past language first.',
        mockupLabel: 'Clause rewrite',
        gradient: 'linear-gradient(135deg, #4f46e5, #7c3aed)',
      },
      {
        name: 'New document from template',
        desc: 'Generate a complete first draft from a template and a set of deal variables in seconds.',
        mockupLabel: 'Document from template',
        gradient: 'linear-gradient(135deg, #6366f1, #06b6d4)',
      },
      {
        name: 'Precedent-matched clause',
        desc: 'Draft a clause in the style of your executed agreements via corpus search.',
        mockupLabel: 'Precedent-matched clause',
        gradient: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
      },
      {
        name: 'Memo & action letter',
        desc: 'Produce legal memos and counterparty letters from a short prompt, grounded in the matter.',
        mockupLabel: 'Memo & letter',
        gradient: 'linear-gradient(135deg, #a855f7, #6366f1)',
      },
    ],
  },
};
