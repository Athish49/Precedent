import type { SolutionPageData } from '@/components/solutions/detail/types';

// Procurement & Sourcing — the "inbound / counterparty paper" story. Structured
// on the Harvey law-firms arc: every section is a DIFFERENT lens on the persona,
// never the same capability restated.
//   Pillars   = the three value themes (their template → your standards / volume
//               clears itself / the deviation surfaces however it's worded)
//   Use cases = concrete day-in-the-life workflows, each linking OUT to a product
// The persona's edge: procurement reviews agreements it did NOT write, at intake
// volume. Grounds only in real capabilities: Contract Analysis counterparty-paper
// mode, Autonomous Review, Redlining, Obligations & Monitoring.
export const procurement: SolutionPageData = {
  slug: 'procurement',
  name: 'Procurement & Sourcing',

  hero: {
    eyebrow: 'For Procurement & Sourcing',
    headline: 'Review vendor paper at the speed you sign it.',
    pitch:
      'Every inbound agreement arrives on the vendor’s template, not yours. Precedent reads it against your standards the moment it lands — so procurement stops staging paper for legal and starts clearing deals.',
  },

  heroImage: {
    label: 'Procurement — inbound paper intake queue mockup',
    gradient: 'linear-gradient(135deg, #f59e0b, #f97316, #ef4444)',
  },

  proof: {
    caption: 'The procurement teams clearing paper at volume run on Precedent',
    logos: ['Halcyon', 'Stiltmark', 'Northwind', 'Meridian', 'Aperture', 'Vantage'],
  },

  pillars: {
    sectionTitle: 'Built for paper you didn’t write',
    sectionIntro:
      'Procurement’s whole job is the inverse of drafting: reading someone else’s document, cold, against your own bar — hundreds of times a quarter. Precedent is built for exactly that.',
    items: [
      {
        icon: 'scale',
        title: 'Their template, measured against your bar',
        desc: 'You’re never marking up a familiar document — you’re reading a vendor’s cold. Precedent holds every inbound agreement up to your standards instead, so “is this acceptable to us?” is answered before a human opens it.',
      },
      {
        icon: 'search',
        title: 'The deviation surfaces however it’s worded',
        desc: 'No two vendor papers say the same thing the same way, so the dangerous term hides in language that reads standard until it isn’t. Precedent judges by meaning, not wording — the off-market clause surfaces no matter how the counterparty phrased it.',
      },
      {
        icon: 'bolt',
        title: 'Volume stops being a bottleneck',
        desc: 'Hundreds of agreements no longer queue behind a handful of reviewers. The routine, in-policy paper moves on its own and only genuine exceptions reach a person — so the sourcing cycle runs at intake speed, not review speed.',
      },
    ],
  },

  useCases: {
    sectionTitle: 'How procurement runs on Precedent',
    sectionIntro:
      'The intake pipeline you’re accountable for, broken into the moments you actually operate — each powered by a capability you can point a vendor to.',
    items: [
      {
        name: 'Read their paper against your standards',
        desc: 'Counterparty-paper mode reviews an inbound MSA, order form, or SaaS agreement against your positions across every risk class the moment it lands — severity-weighted, so a reviewer sees the real issues first instead of reading clause by clause.',
        mockupLabel: 'Counterparty-paper risk review',
        gradient: 'linear-gradient(135deg, #f59e0b, #f97316)',
        linkLabel: 'Contract Analysis',
        href: '/products/contract-analysis',
      },
      {
        name: 'Clear the routine automatically',
        desc: 'In-policy vendor paper that meets your bar clears on its own the instant it’s analyzed; only the agreements that genuinely need a lawyer escalate. The queue stops being the thing procurement waits on.',
        mockupLabel: 'Autonomous intake triage — auto-clear vs. escalate',
        gradient: 'linear-gradient(135deg, #f97316, #ef4444)',
        linkLabel: 'Autonomous Review',
        href: '/products/autonomous-review',
      },
      {
        name: 'Push back with redlines, not comments',
        desc: 'When a vendor’s clause misses your standard, it comes back as a surgical, counterparty-ready redline with rationale attached — so negotiating their terms takes minutes and the vendor gets edits they can accept, not a vague note.',
        mockupLabel: 'Counterparty-ready redlines with rationale',
        gradient: 'linear-gradient(135deg, #ef4444, #f59e0b)',
        linkLabel: 'Redlining & Negotiation',
        href: '/products/redlining',
      },
      {
        name: 'Watch every vendor commitment',
        desc: 'Renewal dates, price-lock windows, and notice periods are extracted from each signed agreement at ingest and monitored daily — so an auto-renewal or a termination deadline surfaces with time to act instead of after it fires.',
        mockupLabel: 'Vendor obligations monitor + renewal alerts',
        gradient: 'linear-gradient(135deg, #f59e0b, #ef4444)',
        linkLabel: 'Obligations & Monitoring',
        href: '/products/obligations',
      },
    ],
  },

  featured: {
    quote:
      'We used to stage every vendor MSA for legal and wait. Now the paper is triaged the moment it lands, the routine clears itself, and my team only touches the agreements that actually carry risk — on whatever template the vendor sent.',
    name: 'Renata Silva',
    role: 'Director of Procurement',
    firm: 'Halcyon',
    portraitGradient: 'linear-gradient(135deg, #f59e0b, #f97316, #ef4444)',
  },

  impact: {
    heading: 'What a clear pipeline looks like',
    stats: [
      { value: 70, suffix: '%', label: 'of routine vendor paper cleared without a reviewer' },
      { value: 5, suffix: '×', label: 'faster turnaround on inbound agreements' },
      { value: 100, suffix: '%', label: 'of vendor renewals tracked from signing' },
    ],
  },
};
