import type { SolutionPageData } from '@/components/solutions/detail/types';

// Legal Operations — the lifecycle/CLM narrative (deliberately kept off a
// standalone Platform page). Structured on the Harvey law-firms arc: every
// section is a DIFFERENT lens on legal ops, never the same capability restated.
//   Pillars   = the three value themes (consolidate / see / self-serve control)
//   Use cases = concrete day-in-the-life workflows, each linking OUT to a product
// Grounds only in real capabilities: Playbooks (S6), Autonomous Review (S5),
// Analytics (S9), Obligations (S8), Repository (S7).
export const legalOps: SolutionPageData = {
  slug: 'legal-ops',
  name: 'Legal Operations',

  hero: {
    eyebrow: 'For Legal Operations',
    headline: 'Run the whole contract lifecycle from one system.',
    pitch:
      'Precedent gives legal ops one place to set the standards, enforce them on every deal, and see the whole portfolio — from first draft to final renewal.',
  },

  heroImage: {
    label: 'Legal Ops — lifecycle control room mockup',
    gradient: 'linear-gradient(135deg, #6366f1, #7c3aed, #0ea5e9)',
  },

  proof: {
    caption: 'The legal ops teams operating at scale run on Precedent',
    logos: ['Northwind', 'Aperture', 'Halcyon', 'Meridian', 'Lumen', 'Vantage'],
  },

  pillars: {
    sectionTitle: 'Built to operate the lifecycle',
    sectionIntro:
      'Legal ops is measured on throughput, consistency, and control. Precedent turns each of those from a hope into a system you own.',
    items: [
      {
        icon: 'layers',
        title: 'One standard, enforced on every deal',
        desc: 'Your preferred, acceptable, and prohibited positions stop living in wikis and senior lawyers’ heads. They become live rules that every contract is checked against — the same way, every time.',
      },
      {
        icon: 'chart',
        title: 'The whole portfolio, always in view',
        desc: 'Severity-weighted risk, upcoming renewals, and cycle-time sit on a live dashboard. When leadership asks what’s in the book, the answer is on screen — not a week of spreadsheet archaeology.',
      },
      {
        icon: 'route',
        title: 'Change the process yourself',
        desc: 'Update a fallback position or a review rule and it’s live on the next contract — no ticket, no template rev, no engineering in the loop. Standards stay current because you keep them current.',
      },
    ],
  },

  useCases: {
    sectionTitle: 'How legal ops runs on Precedent',
    sectionIntro:
      'The lifecycle you’re accountable for, broken into the moments you actually operate — each powered by a capability you control directly.',
    items: [
      {
        name: 'Standardize the playbook',
        desc: 'Seed a playbook from the contracts you’ve already signed, then encode preferred, acceptable, prohibited, and fallback positions once. It becomes the single definition of “our position” for the whole team.',
        mockupLabel: 'Playbook rule store, seeded from signed paper',
        gradient: 'linear-gradient(135deg, #6366f1, #3b82f6)',
        linkLabel: 'Playbooks & Standards',
        href: '/products/playbooks',
      },
      {
        name: 'Triage every intake',
        desc: 'New agreements are reviewed against the playbook the moment they land. Routine, in-policy paper clears on its own; only genuine exceptions escalate — so the queue stops being a bottleneck.',
        mockupLabel: 'Intake triage — auto-clear vs. escalate',
        gradient: 'linear-gradient(135deg, #7c3aed, #6366f1)',
        linkLabel: 'Autonomous Review',
        href: '/products/autonomous-review',
      },
      {
        name: 'Report to leadership',
        desc: 'Answer the GC’s questions live: how much risk is in the book, what a policy change would cost, how cycle-time is trending. The report is a dashboard, not a fire drill.',
        mockupLabel: 'Portfolio analytics dashboard',
        gradient: 'linear-gradient(135deg, #0ea5e9, #6366f1)',
        linkLabel: 'Analytics & Reporting',
        href: '/products/analytics',
      },
      {
        name: 'Watch renewals & obligations',
        desc: 'Key dates, notice windows, and obligations are extracted at ingest and monitored daily, so auto-renewals and deadlines surface with time to act instead of after they fire.',
        mockupLabel: 'Obligations monitor + renewal alerts',
        gradient: 'linear-gradient(135deg, #8b5cf6, #0ea5e9)',
        linkLabel: 'Obligations & Monitoring',
        href: '/products/obligations',
      },
      {
        name: 'Find any clause, instantly',
        desc: 'Keyword, faceted, and natural-language search across the whole repository, with amendments linked and versions comparable — one source of truth for every agreement the team has ever signed.',
        mockupLabel: 'Repository & smart search',
        gradient: 'linear-gradient(135deg, #3b82f6, #6366f1)',
        linkLabel: 'Repository & Search',
        href: '/products/repository',
      },
    ],
  },

  featured: {
    quote:
      'We stopped being the team that hunts for documents. The playbook is the standard, the dashboard is the report, and I change a rule myself the day we decide to. That’s the whole job, finally in one place.',
    name: 'Dana Whitfield',
    role: 'Head of Legal Operations',
    firm: 'Northwind',
    portraitGradient: 'linear-gradient(135deg, #4338ca, #6366f1, #8b5cf6)',
  },

  impact: {
    heading: 'What operated looks like',
    stats: [
      { value: 100, suffix: '%', label: 'of deals reviewed against one playbook' },
      { value: 1, suffix: '-day', label: 'to a playbook seeded from your own contracts' },
      { value: 0, label: 'engineering tickets to change a standard' },
    ],
  },
};
