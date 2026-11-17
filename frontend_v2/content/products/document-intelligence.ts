import type { ProductPageData } from '@/components/products/detail/types';

// Document Intelligence — maps to backend Service 5 (in-editor intelligence).
export const documentIntelligence: ProductPageData = {
  slug: 'document-intelligence',
  name: 'Document Intelligence',

  hero: {
    headline: 'Ask any contract anything.',
    pitch: 'Precedent answers in plain English and cites the exact clause behind every word.',
  },

  heroImage: {
    label: 'Document Intelligence — in-editor Q&A mockup',
    gradient: 'linear-gradient(135deg, #3b82f6, #06b6d4, #0ea5e9)',
  },

  capabilities: {
    sectionTitle: 'Understand any contract in seconds',
    sectionIntro:
      'Instead of scrolling a fifty-page agreement, ask it a question. Precedent reads the contract directly and hands back an answer you can trust and trace.',
    cards: [
      {
        title: 'Cited Q&A you can prove',
        blurb:
          'Ask any contract a question in plain English and get an answer drawn straight from the clause text — with a citation to the exact line.',
        mockupLabel: 'Cited Q&A — question → answer → source clause',
        gradient: 'linear-gradient(135deg, #3b82f6, #06b6d4)',
        points: [
          {
            title: 'Answers from the actual text',
            desc: 'Precedent reads the contract’s clause array directly — no black-box retrieval, so answers reflect what the document really says.',
          },
          {
            title: 'Character-level citations',
            desc: 'Every answer links to the exact line it came from, so you can verify the source in one click.',
          },
          {
            title: 'Plain-English in, plain-English out',
            desc: 'Ask the way you’d ask a colleague; get a clear answer instead of a keyword search result.',
          },
        ],
      },
      {
        title: 'Risk-aware summaries',
        blurb:
          'A summary that surfaces what actually matters — grounded on the contract’s metadata and analysis flags, not a generic recap.',
        mockupLabel: 'Risk-aware summary — metadata + flags',
        gradient: 'linear-gradient(135deg, #06b6d4, #0ea5e9)',
        points: [
          {
            title: 'Grounded on real analysis',
            desc: 'Summaries build on the contract’s metadata and risk flags, so the important terms rise to the top.',
          },
          {
            title: 'Redline-thread summaries too',
            desc: 'Collapse a long back-and-forth into a clear recap of what changed and where negotiation stands.',
          },
        ],
      },
      {
        title: 'Easy Prompt',
        blurb:
          'Describe what you want in plain English and Precedent turns it into a structured legal action — then routes it to the right tool.',
        mockupLabel: 'Easy Prompt — NL request → structured action',
        gradient: 'linear-gradient(135deg, #0ea5e9, #6366f1)',
        points: [
          {
            title: 'Natural language to action',
            desc: 'A free-form request becomes a structured legal action — no menus, no syntax to learn.',
          },
          {
            title: 'Routed automatically',
            desc: 'Precedent sends the action to drafting or redlining, so your intent turns into work without a detour.',
          },
        ],
      },
      {
        title: 'In-editor research',
        blurb:
          'Ask a question that reaches beyond the page — Precedent searches the web and synthesizes it with your contract’s context.',
        mockupLabel: 'Chat2 research — web + contract context',
        gradient: 'linear-gradient(135deg, #6366f1, #3b82f6)',
        points: [
          {
            title: 'Web, grounded in your contract',
            desc: 'Research answers weave outside sources together with the specifics of the document you’re in.',
          },
          {
            title: 'Cited and inline',
            desc: 'Results come back as an inline answer with sources, right where you’re working — no tab-switching.',
          },
        ],
      },
    ],
  },

  spotlight: {
    kicker: 'Every answer is provable',
    title: 'Cited Q&A',
    tagline:
      'Every answer traces back to the exact clause it came from. Precedent reads the contract text directly, so what you get is grounded, citable, and yours to verify.',
    mockupLabel: 'Cited Q&A — answer with character-level citation',
    gradient: 'linear-gradient(135deg, #2563eb, #06b6d4, #0ea5e9)',
  },

  impact: {
    heading: 'Intelligence, by the numbers',
    stats: [
      { value: 30, suffix: '×', label: 'faster to an answer than reading the contract' },
      { value: 100, suffix: '%', label: 'of answers traced to a source clause' },
      { value: 85, suffix: '%', label: 'less time spent hunting for the right clause' },
    ],
    testimonials: [
      {
        quote:
          'I stopped skimming contracts to find one term. I ask Precedent, get the answer, and click straight to the clause it came from. Verification takes seconds.',
        name: 'Priya Nandakumar',
        role: 'Senior Counsel',
        firm: 'Meridian',
      },
      {
        quote:
          'The summaries actually know what’s risky, because they’re built on our analysis flags. New hires get up to speed on a deal in minutes instead of an afternoon.',
        name: 'Tom García',
        role: 'Director, Contracts',
        firm: 'Halcyon',
      },
    ],
  },

  catalog: {
    items: [
      {
        name: 'Ask a question',
        desc: 'Ask any contract a plain-English question and get an answer drawn from the clause text, cited to the exact line.',
        mockupLabel: 'Ask a question',
        gradient: 'linear-gradient(135deg, #3b82f6, #06b6d4)',
      },
      {
        name: 'Summarize a contract',
        desc: 'Get a risk-aware summary grounded on the contract’s metadata and analysis flags.',
        mockupLabel: 'Summarize a contract',
        gradient: 'linear-gradient(135deg, #06b6d4, #0ea5e9)',
      },
      {
        name: 'Summarize a redline thread',
        desc: 'Collapse a long negotiation thread into a clear recap of what changed and where it stands.',
        mockupLabel: 'Summarize a redline thread',
        gradient: 'linear-gradient(135deg, #0ea5e9, #38bdf8)',
      },
      {
        name: 'Easy Prompt',
        desc: 'Turn a natural-language request into a structured legal action and route it to drafting or redlining.',
        mockupLabel: 'Easy Prompt',
        gradient: 'linear-gradient(135deg, #0ea5e9, #6366f1)',
      },
      {
        name: 'Research a question',
        desc: 'Search the web and synthesize it with your contract’s context, returned as an inline cited answer.',
        mockupLabel: 'Research a question',
        gradient: 'linear-gradient(135deg, #6366f1, #3b82f6)',
      },
      {
        name: 'Navigate clauses',
        desc: 'Jump around the document instantly with a deterministic clause-navigation index.',
        mockupLabel: 'Navigate clauses',
        gradient: 'linear-gradient(135deg, #2563eb, #0ea5e9)',
      },
    ],
  },
};
