import type { ProductPageData } from '@/components/products/detail/types';

// Contract Analysis — maps to backend Service 2 (Analysis).
export const contractAnalysis: ProductPageData = {
  slug: 'contract-analysis',
  name: 'Contract Analysis',

  hero: {
    headline: 'Every risk, surfaced in seconds.',
    pitch: 'Precedent reads any contract and returns every risk, cited to the exact line.',
  },

  heroImage: {
    label: 'Contract Analysis — risk report mockup',
    gradient: 'linear-gradient(135deg, #f59e0b, #ef4444, #f43f5e)',
  },

  capabilities: {
    sectionTitle: 'See what you would have missed',
    sectionIntro:
      'Drop in any contract and Precedent flags missing clauses, prohibited terms, non-standard language, high-risk provisions, and vague or inconsistent wording — each one tied to the exact spot in the document.',
    cards: [
      {
        title: 'Caught before AI even looks',
        blurb:
          'A deterministic structural gate checks your clause-type list first — so missing and prohibited clauses are caught with certainty, not guessed.',
        mockupLabel: 'Structural gate — clause-type checklist',
        gradient: 'linear-gradient(135deg, #f59e0b, #ea580c)',
        points: [
          {
            title: 'Missing clauses, guaranteed',
            desc: 'The required clause list is checked structurally, so anything absent is flagged deterministically — no model needed.',
          },
          {
            title: 'Prohibited terms, blocked',
            desc: 'Clauses your team never accepts are detected the same way, before any AI weighs in.',
          },
          {
            title: 'Runs first, every time',
            desc: 'Layer 1 runs before content analysis, giving you a fast, reliable baseline you can trust.',
          },
        ],
      },
      {
        title: 'Knows whose paper it is',
        blurb:
          'Content analysis adapts to origin — it judges your own paper against your standards and counterparty paper against your preferred position.',
        mockupLabel: 'Paper-aware rubric — own vs counterparty',
        gradient: 'linear-gradient(135deg, #ef4444, #f43f5e)',
        points: [
          {
            title: 'Your paper, your standards',
            desc: 'On documents you drafted, Precedent flags non-standard, high-risk, and vague language against your own rubric.',
          },
          {
            title: 'Their paper, your position',
            desc: 'On counterparty paper, it measures every clause as a deviation from the position you prefer.',
          },
          {
            title: 'Reviewed in batches',
            desc: 'Content review is batched for speed, so even long agreements come back quickly.',
          },
        ],
      },
      {
        title: 'A risk score you can defend',
        blurb:
          'Precedent weighs every flag by severity using your playbook — never a naive average that lets a critical issue hide behind minor ones.',
        mockupLabel: 'Severity-weighted risk score',
        gradient: 'linear-gradient(135deg, #f43f5e, #ea580c)',
        points: [
          {
            title: 'Severity-weighted, not averaged',
            desc: 'A single critical clause moves the score the way it should — small issues can never dilute a real problem.',
          },
          {
            title: 'Weights from your playbook',
            desc: 'The scoring reflects the priorities you configure, so the number matches how your team actually thinks about risk.',
          },
        ],
      },
      {
        title: 'Cited down to the character',
        blurb:
          'Every flag points to the exact character offsets in the document, so your team goes straight to the issue instead of hunting for it.',
        mockupLabel: 'Character-level citation on every flag',
        gradient: 'linear-gradient(135deg, #ea580c, #ef4444)',
        points: [
          {
            title: 'Exact location, issue by issue',
            desc: 'Each finding is anchored to precise character offsets — no page-flipping, no ambiguity about what is being flagged.',
          },
          {
            title: 'Traceable and reviewable',
            desc: 'Because every claim is grounded in the text, findings are easy to verify and share with the deal team.',
          },
        ],
      },
    ],
  },

  spotlight: {
    kicker: 'Knows whose paper it is',
    title: 'Paper-Aware Analysis',
    tagline:
      'Precedent adjusts its rubric to the document in front of it — holding your own paper to your standards and measuring their paper against the position you prefer.',
    mockupLabel: 'Paper-aware rubric — own vs counterparty',
    gradient: 'linear-gradient(135deg, #ea580c, #ef4444, #f43f5e)',
  },

  impact: {
    heading: 'Analysis, by the numbers',
    stats: [
      { value: 30, suffix: '×', label: 'faster than a manual first-pass review' },
      { value: 100, suffix: '%', label: 'of flags cited to the exact text' },
      { value: 6, label: 'risk categories checked on every contract' },
    ],
    testimonials: [
      {
        quote:
          'The structural gate alone changed how we work — missing and prohibited clauses are caught with certainty before anyone reads a word. We stopped finding those the hard way.',
        name: 'Priya Nandakumar',
        role: 'Deputy General Counsel',
        firm: 'Halcyon Group',
      },
      {
        quote:
          'It knows whose paper it is. On counterparty drafts it flags exactly where they walked away from our position, and every flag lands on the precise line. Review is a fraction of the time.',
        name: 'Tomás Reyes',
        role: 'Director of Legal Operations',
        firm: 'Beacon Industries',
      },
    ],
  },

  catalog: {
    items: [
      {
        name: 'Missing clause',
        desc: 'Required clauses absent from the document, caught deterministically against your clause-type list.',
        mockupLabel: 'Missing clause',
        gradient: 'linear-gradient(135deg, #f59e0b, #ea580c)',
      },
      {
        name: 'Prohibited term',
        desc: 'Language your team never accepts, detected structurally before any AI review runs.',
        mockupLabel: 'Prohibited term',
        gradient: 'linear-gradient(135deg, #ef4444, #f43f5e)',
      },
      {
        name: 'Non-standard language',
        desc: 'Wording that drifts from your standards, flagged with your own paper held to your rubric.',
        mockupLabel: 'Non-standard language',
        gradient: 'linear-gradient(135deg, #f43f5e, #ea580c)',
      },
      {
        name: 'High-risk clause',
        desc: 'Provisions that carry outsized exposure, surfaced and severity-weighted into your risk score.',
        mockupLabel: 'High-risk clause',
        gradient: 'linear-gradient(135deg, #ea580c, #ef4444)',
      },
      {
        name: 'Vague or inconsistent terms',
        desc: 'Ambiguous or self-contradicting wording flagged and cited to the exact character offsets.',
        mockupLabel: 'Vague or inconsistent terms',
        gradient: 'linear-gradient(135deg, #f59e0b, #f43f5e)',
      },
    ],
  },
};
