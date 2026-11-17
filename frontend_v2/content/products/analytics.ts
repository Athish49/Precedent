import type { ProductPageData } from '@/components/products/detail/types';

// Analytics & Reporting — maps to backend Service 9 (Analytics).
export const analyticsReporting: ProductPageData = {
  slug: 'analytics',
  name: 'Analytics & Reporting',

  hero: {
    headline: 'Your whole portfolio at a glance.',
    pitch: 'Precedent reads your live contract data and returns fast, deterministic dashboards and reports.',
  },

  heroImage: {
    label: 'Analytics & Reporting — dashboard mockup',
    gradient: 'linear-gradient(135deg, #6366f1, #8b5cf6, #a855f7)',
  },

  capabilities: {
    sectionTitle: 'See every contract, without asking a soul',
    sectionIntro:
      'These are straight reads over your portfolio — no AI, no waiting. Every number rolls up from the fields already extracted across your contracts, so the view is always current and always exact.',
    cards: [
      {
        title: 'Portfolio risk, severity-weighted',
        blurb:
          'One roll-up of risk across your entire book — weighted by severity, never a naive average that hides the deals that matter.',
        mockupLabel: 'Portfolio risk — severity-weighted roll-up',
        gradient: 'linear-gradient(135deg, #7c3aed, #a855f7)',
        points: [
          {
            title: 'Weighted, not averaged',
            desc: 'High-severity findings carry their real weight, so a handful of dangerous contracts never disappear into a friendly-looking mean.',
          },
          {
            title: 'Reads from Contract Analysis',
            desc: 'The report rolls up the risk already scored per contract — no re-analysis, just an aggregate over live results.',
          },
          {
            title: 'Portfolio-wide in one read',
            desc: 'See the risk posture of your whole book in a single view, refreshed the moment the underlying data changes.',
          },
        ],
      },
      {
        title: 'Contract value, tracked across the book',
        blurb:
          'Sum and group the financial fields across your portfolio so you always know what your contracts are actually worth.',
        mockupLabel: 'Contract value — financial roll-up',
        gradient: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
        points: [
          {
            title: 'Totals you can trust',
            desc: 'Deterministic sums over the extracted financial fields — the same math every time, straight from your data.',
          },
          {
            title: 'Grouped the way you think',
            desc: 'Break value down by the dimensions that matter to you and see where the money in your portfolio sits.',
          },
        ],
      },
      {
        title: 'Tabular review with natural-language columns',
        blurb:
          'One row per contract, one column per field — then add question columns and turn your whole portfolio into a spreadsheet you can query.',
        mockupLabel: 'Tabular review — one row per contract',
        gradient: 'linear-gradient(135deg, #8b5cf6, #d946ef)',
        points: [
          {
            title: 'A grid over your extracted fields',
            desc: 'Every contract becomes a row, every field a column — the whole portfolio laid out to scan, sort, and compare.',
          },
          {
            title: 'Ask your book a question',
            desc: 'Add a natural-language column and each cell answers for its contract, served instantly from cached Q&A.',
          },
        ],
      },
      {
        title: 'Renewal dashboard',
        blurb:
          'Upcoming renewals, their risk, and the recommendation — all in one place so nothing slips and every decision has context.',
        mockupLabel: 'Renewal dashboard — dates, risk, recommendation',
        gradient: 'linear-gradient(135deg, #a855f7, #6366f1)',
        points: [
          {
            title: 'Dates that surface themselves',
            desc: 'Upcoming renewal dates roll up from Obligations, so what needs attention rises to the top on its own.',
          },
          {
            title: 'Risk and recommendation, side by side',
            desc: 'Each renewal arrives with its risk and the suggested action, so you decide with full context, not guesswork.',
          },
        ],
      },
    ],
  },

  spotlight: {
    kicker: 'Query your whole book',
    title: 'Tabular Review',
    tagline:
      'One row per contract, one column per field — then add natural-language columns and turn your entire portfolio into a spreadsheet you can ask questions of.',
    mockupLabel: 'Tabular Review — portfolio as a queryable spreadsheet',
    gradient: 'linear-gradient(135deg, #4338ca, #7c3aed, #a855f7)',
  },

  impact: {
    heading: 'Reporting, by the numbers',
    stats: [
      { value: 100, suffix: '%', label: 'deterministic — the same read every time' },
      { prefix: '<', value: 2, suffix: 's', label: 'to load a portfolio-wide view' },
      { value: 12, suffix: 'k+', label: 'contracts rolled up in a single dashboard' },
    ],
    testimonials: [
      {
        quote:
          'We used to spend a week building a portfolio risk deck. Now it is a dashboard that is already right — severity-weighted, current, and impossible to argue with.',
        name: 'Priya Nair',
        role: 'Director, Legal Operations',
        firm: 'Meridian',
      },
      {
        quote:
          'Tabular review turned our repository into a spreadsheet we can actually query. I add a question column and the whole book answers in seconds. It changed how our team works.',
        name: 'Tom Alvarez',
        role: 'Associate General Counsel',
        firm: 'Cobalt',
      },
    ],
  },

  catalog: {
    items: [
      {
        name: 'Intelligence dashboard',
        desc: 'Aggregate the extracted fields across all your contracts into one live contract-intelligence view.',
        mockupLabel: 'Intelligence dashboard',
        gradient: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
      },
      {
        name: 'Portfolio risk',
        desc: 'A severity-weighted roll-up of risk across the book — never a naive average.',
        mockupLabel: 'Portfolio risk',
        gradient: 'linear-gradient(135deg, #7c3aed, #a855f7)',
      },
      {
        name: 'Contract value',
        desc: 'Sum and group the financial fields across your portfolio to track total contract value.',
        mockupLabel: 'Contract value',
        gradient: 'linear-gradient(135deg, #6366f1, #d946ef)',
      },
      {
        name: 'Tabular review',
        desc: 'One row per contract, one column per field — with natural-language question columns you can query.',
        mockupLabel: 'Tabular review',
        gradient: 'linear-gradient(135deg, #8b5cf6, #d946ef)',
      },
      {
        name: 'Renewal dashboard',
        desc: 'Upcoming renewal dates, their risk, and the recommendation, all in one view.',
        mockupLabel: 'Renewal dashboard',
        gradient: 'linear-gradient(135deg, #a855f7, #6366f1)',
      },
    ],
  },
};
