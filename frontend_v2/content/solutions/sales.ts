import type { SolutionPageData } from '@/components/solutions/detail/types';

// Sales / Deal Desk — the buyer is the revenue org, not legal. The pain is that
// legal review bottlenecks deals; the promise is speed-to-close with guardrails.
// Structured on the Harvey law-firms arc: every section is a DIFFERENT lens.
//   Pillars   = the three value themes (self-serve speed / guardrails / a
//               forecastable close date)
//   Use cases = concrete day-in-the-life deal moments, each linking OUT to a product
// Grounds only in real capabilities: Autonomous Review (S5), Playbooks &
// Standards (S6), Redlining & Negotiation, Analytics & Reporting.
export const sales: SolutionPageData = {
  slug: 'sales',
  name: 'Sales / Deal Desk',

  hero: {
    eyebrow: 'For Sales / Deal Desk',
    headline: 'Close deals without waiting in the legal queue.',
    pitch:
      'Precedent clears routine paper automatically against pre-approved positions, so reps get a redline in minutes and only genuine risk ever reaches a lawyer.',
  },

  heroImage: {
    label: 'Sales / Deal Desk — deal velocity board mockup',
    gradient: 'linear-gradient(135deg, #10b981, #14b8a6, #0ea5e9)',
  },

  proof: {
    caption: 'The revenue teams closing fastest run their paper on Precedent',
    logos: ['Lumen', 'Vantage', 'Northwind', 'Aperture', 'Meridian', 'Halcyon'],
  },

  pillars: {
    sectionTitle: 'Built to move deals, not stall them',
    sectionIntro:
      'Revenue is measured on cycle time and close rate. Precedent turns the last mile — legal review — from a queue you wait on into a fast path you control, without loosening a single standard.',
    items: [
      {
        icon: 'bolt',
        title: 'Self-serve review, safe by default',
        desc: 'Routine paper clears itself against positions legal already approved. Reps get a sendable redline in minutes instead of dropping the deal into a queue and hoping — because the guardrails, not a human, decide what’s safe.',
      },
      {
        icon: 'shield',
        title: 'Legal as backstop, not bottleneck',
        desc: 'Only clauses that breach a real limit escalate. Counsel stops rubber-stamping the standard 90% and spends their judgment on the deals that actually need it — so the same team clears far more paper.',
      },
      {
        icon: 'clock',
        title: 'A close date you can forecast',
        desc: 'When routine turnaround is measured in minutes and escalations are the visible exception, cycle time stops being a guess. Deal desk commits close dates on real numbers instead of gut feel.',
      },
    ],
  },

  useCases: {
    sectionTitle: 'How a deal moves on Precedent',
    sectionIntro:
      'The moments a rep and deal desk actually live through, from first counterparty paper to end-of-quarter — each powered by a capability legal owns and you get to use.',
    items: [
      {
        name: 'Send a contract for review',
        desc: 'Drop the counterparty’s paper in and it’s reviewed against your pre-approved playbook the moment it lands. In-policy, on-stance clauses clear on their own; only genuine exceptions stop for a lawyer — so nothing routine waits in a queue.',
        mockupLabel: 'Autonomous review — auto-clear vs. escalate',
        gradient: 'linear-gradient(135deg, #10b981, #14b8a6)',
        linkLabel: 'Autonomous Review',
        href: '/products/autonomous-review',
      },
      {
        name: 'See what you can concede',
        desc: 'Before you get on the call, the preferred, acceptable, prohibited, and fallback positions are right there — so a rep knows a small edit is fine to accept and a real dealbreaker isn’t, without pinging legal to ask.',
        mockupLabel: 'Pre-approved playbook positions',
        gradient: 'linear-gradient(135deg, #14b8a6, #0ea5e9)',
        linkLabel: 'Playbooks & Standards',
        href: '/products/playbooks',
      },
      {
        name: 'Handle a counterparty redline',
        desc: 'A customer sends edits back and the on-stance response comes as clean, tracked changes with fallback language ready to send. The counterparty ask turns around in minutes instead of stalling the deal for days.',
        mockupLabel: 'Fast on-stance redline',
        gradient: 'linear-gradient(135deg, #059669, #0284c7)',
        linkLabel: 'Redlining & Negotiation',
        href: '/products/redlining',
      },
      {
        name: 'Forecast the quarter',
        desc: 'See turnaround, throughput, and exactly where deals slow down — so deal desk can tell the VP which contracts will clear this week and commit a pipeline number that holds up.',
        mockupLabel: 'Cycle-time & throughput dashboard',
        gradient: 'linear-gradient(135deg, #0d9488, #0ea5e9)',
        linkLabel: 'Analytics & Reporting',
        href: '/products/analytics',
      },
    ],
  },

  featured: {
    quote:
      'Standard paper used to sit in the legal queue for days. Now it clears in minutes and only the real exceptions land on a lawyer’s desk. My reps stopped escalating every tiny edit because the guardrails already tell them what’s safe — so we commit close dates we can actually hit.',
    name: 'Camila Reyes',
    role: 'Director, Deal Desk',
    firm: 'Lumen',
    portraitGradient: 'linear-gradient(135deg, #059669, #14b8a6, #0ea5e9)',
  },

  impact: {
    heading: 'What velocity looks like',
    stats: [
      { value: 90, suffix: '%', label: 'of routine deals cleared without a lawyer' },
      { value: 8, suffix: '×', label: 'faster turnaround on standard paper' },
      { value: 70, suffix: '%', label: 'fewer contracts escalated to legal' },
    ],
  },
};
