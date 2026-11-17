import type { ProductPageData } from '@/components/products/detail/types';

// Repository & Search — maps to backend Service 7 (Repository & Search).
export const repositorySearch: ProductPageData = {
  slug: 'repository',
  name: 'Repository & Search',

  hero: {
    headline: 'Every contract, searchable to the clause.',
    pitch: 'Precedent stores every agreement and returns the exact clause you need in seconds.',
  },

  heroImage: {
    label: 'Repository & Search — results mockup',
    gradient: 'linear-gradient(135deg, #14b8a6, #22c55e, #06b6d4)',
  },

  capabilities: {
    sectionTitle: 'Find anything in your paper, instantly',
    sectionIntro:
      'One home for every contract you sign, with three ways to search — so the answer, the version, or the precedent you need is never more than a query away.',
    cards: [
      {
        title: 'Search the whole portfolio',
        blurb:
          'Combine full-text keyword search with faceted metadata filters to narrow thousands of agreements down to the handful that matter.',
        mockupLabel: 'Keyword + facets — portfolio results',
        gradient: 'linear-gradient(135deg, #0d9488, #22c55e)',
        points: [
          {
            title: 'Full-text keyword search',
            desc: 'Search every word across every contract in the repository and jump straight to the matching language.',
          },
          {
            title: 'Faceted metadata filters',
            desc: 'Filter by contract type, counterparty, status, effective-date range, and value range — stack facets to pinpoint results.',
          },
          {
            title: 'Built for the whole corpus',
            desc: 'The single source of truth for every contract, from the moment it lands at ingest.',
          },
        ],
      },
      {
        title: 'Smart Search — just ask',
        blurb:
          'Type a plain-English question and Precedent turns it into precise structured filters, adds meaning-based search, and merges the results.',
        mockupLabel: 'Smart Search — NL to filters',
        gradient: 'linear-gradient(135deg, #14b8a6, #06b6d4)',
        points: [
          {
            title: 'Natural language to filters',
            desc: 'A plain-English question becomes structured metadata filters automatically — no query syntax to learn.',
          },
          {
            title: 'Optional semantic search',
            desc: 'A meaning-based pass finds contracts that match your intent even when they never use your exact words.',
          },
          {
            title: 'Merged for the best answer',
            desc: 'Structured and semantic results are merged into one ranked list, so the strongest matches surface first.',
          },
        ],
      },
      {
        title: 'Versions & amendments, linked',
        blurb:
          'Every amendment, addendum, and revision is tied back to the agreement it belongs to, so you always see the full lineage.',
        mockupLabel: 'Version tree — parent-child links',
        gradient: 'linear-gradient(135deg, #059669, #10b981)',
        points: [
          {
            title: 'Parent-child linking',
            desc: 'Amendments, addenda, and versions are connected to their parent agreement automatically.',
          },
          {
            title: 'Always version-aware',
            desc: 'See the complete history of an agreement in one place and know which version is current at a glance.',
          },
        ],
      },
      {
        title: 'Redline history per clause',
        blurb:
          'Look up the positions you have taken on any clause type before — the prior redlines that show how you have negotiated.',
        mockupLabel: 'Redline history — by clause type',
        gradient: 'linear-gradient(135deg, #0891b2, #22c55e)',
        points: [
          {
            title: 'History by clause type',
            desc: 'Pull the prior positions you have taken on a clause, scoped to the type you are working on.',
          },
          {
            title: 'Learn from your own paper',
            desc: 'See how similar clauses were negotiated before, so your next position is grounded in precedent.',
          },
        ],
      },
    ],
  },

  spotlight: {
    kicker: 'Just ask',
    title: 'Smart Search',
    tagline:
      'Ask a question the way you would ask a colleague. Precedent turns plain English into precise filters, layers in meaning-based search, and returns exactly the contracts you meant.',
    mockupLabel: 'Smart Search — question to results',
    gradient: 'linear-gradient(135deg, #0d9488, #16a34a, #06b6d4)',
  },

  impact: {
    heading: 'Search, by the numbers',
    stats: [
      { value: 100, suffix: '%', label: 'of contracts embedded on write for instant search' },
      { value: 30, suffix: '×', label: 'faster to the clause you need' },
      { value: 95, suffix: '%', label: 'of searches answered on the first query' },
    ],
    testimonials: [
      {
        quote:
          'We used to lose an afternoon hunting for the right precedent across shared drives. Now I ask a question in plain English and the exact clause is in front of me before I finish my coffee.',
        name: 'Priya Ramesh',
        role: 'Senior Counsel',
        firm: 'Halcyon',
      },
      {
        quote:
          'Version linking alone changed how we work — every amendment sits under its agreement, and I can see the full redline history on a clause without opening a single file.',
        name: 'Tomás Herrera',
        role: 'Director, Contracts',
        firm: 'Meridian',
      },
    ],
  },

  catalog: {
    items: [
      {
        name: 'Keyword search',
        desc: 'Full-text search across every contract in the repository, straight to the matching language.',
        mockupLabel: 'Keyword search',
        gradient: 'linear-gradient(135deg, #0d9488, #22c55e)',
      },
      {
        name: 'Faceted filters',
        desc: 'Narrow by contract type, counterparty, status, effective-date range, and value range.',
        mockupLabel: 'Faceted filters',
        gradient: 'linear-gradient(135deg, #059669, #10b981)',
      },
      {
        name: 'Smart Search',
        desc: 'Turn a plain-English question into structured filters plus semantic search, merged into one result.',
        mockupLabel: 'Smart Search',
        gradient: 'linear-gradient(135deg, #14b8a6, #06b6d4)',
      },
      {
        name: 'Version history',
        desc: 'See every amendment, addendum, and revision linked to its parent agreement.',
        mockupLabel: 'Version history',
        gradient: 'linear-gradient(135deg, #0891b2, #16a34a)',
      },
      {
        name: 'Redline history',
        desc: 'Look up the prior positions you have taken on any clause type across your paper.',
        mockupLabel: 'Redline history',
        gradient: 'linear-gradient(135deg, #10b981, #06b6d4)',
      },
    ],
  },
};
