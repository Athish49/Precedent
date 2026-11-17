// Shared content contract for every "by team" Solutions page.
// One page = one `SolutionPageData` object fed into <SolutionPage />.
//
// The template follows the Harvey law-firms narrative arc — every section is a
// DIFFERENT lens on the same persona, never a re-list of the same capabilities:
//   §1 Hero            — position the team ("For Legal Operations")
//   §2 Proof           — social proof (fictional, self-consistent wordmarks)
//   §3 Pillars         — three honest value pillars ("Built for …")
//   §4 Use cases       — interactive day-in-the-life scenarios (the story)
//   §5 Featured quote  — one full-bleed testimonial
//   §6 Impact          — count-up outcome metrics
//
// Anti-yap rule: the four pillars, the use-case scenarios, and the metrics must
// each carry NEW information. Do not paraphrase the same capability three times.
// Optional product cross-links live on use cases (link OUT, never re-explain).

import type { Stat } from '@/components/products/detail/types';

export type { Stat };

// A small, fixed icon vocabulary rendered in sections.tsx. Pick the closest.
export type IconName =
  | 'clock'
  | 'shield'
  | 'layers'
  | 'bolt'
  | 'target'
  | 'chart'
  | 'lock'
  | 'search'
  | 'bell'
  | 'scale'
  | 'route'
  | 'check';

// §3 — one of three value pillars ("Built for <team>")
export type Pillar = {
  icon: IconName;
  title: string;
  desc: string;
};

// §4 — one day-in-the-life scenario in the interactive list ↔ mockup section.
// Each item must be a DISTINCT use of the platform, not a capability restated.
export type UseCase = {
  name: string; // the scenario, in the buyer's language ("Intake triage")
  desc: string;
  mockupLabel: string;
  gradient: string;
  // Optional cross-link OUT to the product page that powers this scenario.
  linkLabel?: string;
  href?: string;
};

// §5 — the single featured testimonial (portrait rendered as a gradient panel).
export type FeaturedQuote = {
  quote: string;
  name: string;
  role: string;
  firm: string;
  portraitGradient: string;
};

export type SolutionPageData = {
  slug: string;
  name: string; // "Legal Operations"

  // §1 Hero
  hero: {
    eyebrow: string; // "For Legal Operations"
    headline: string;
    pitch: string;
  };

  heroImage: {
    label: string;
    gradient: string;
  };

  // §2 Proof band — fictional company wordmarks (keep self-consistent with the
  // firms used in `featured` / metrics so the fiction never contradicts itself).
  proof: {
    caption: string; // e.g. "The teams moving fastest run on Precedent"
    logos: string[]; // 5–7 short wordmarks
  };

  // §3 Pillars — exactly three honest value pillars
  pillars: {
    sectionTitle: string;
    sectionIntro?: string;
    items: Pillar[]; // 3
  };

  // §4 Use cases — the interactive story (4–5 distinct scenarios)
  useCases: {
    sectionTitle: string;
    sectionIntro?: string;
    items: UseCase[]; // 4–5
  };

  // §5 Featured testimonial
  featured: FeaturedQuote;

  // §6 Impact — count-up metrics band
  impact: {
    heading: string;
    stats: Stat[]; // 3
  };
};
