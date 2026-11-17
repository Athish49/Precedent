// Shared content contract for every individual product page.
// One page = one `ProductPageData` object fed into <ProductPage />.

export type Stat = {
  prefix?: string;
  value: number; // animated count-up target
  suffix?: string; // e.g. '%', 'k+', '×', 'M'
  label: string;
};

export type Testimonial = {
  quote: string;
  name: string;
  role: string;
  firm: string;
};

export type CapabilityCard = {
  title: string; // sans-medium heading (tx-h4) for the block
  blurb: string; // supporting line (aligned right of the title)
  mockupLabel: string; // placeholder art label
  gradient: string; // placeholder art background
  points: { title: string; desc: string }[]; // 2–3 sub-capabilities
};

export type CatalogItem = {
  name: string;
  desc: string;
  mockupLabel: string;
  gradient: string;
};

export type ProductPageData = {
  slug: string;
  name: string;

  // §1 Hero
  hero: {
    headline: string;
    pitch: string;
  };

  // §2 Hero image
  heroImage: {
    label: string;
    gradient: string;
  };

  // §4 Deep-dive capability cards
  capabilities: {
    sectionTitle: string;
    sectionIntro: string;
    cards: CapabilityCard[];
  };

  // §4.5 Feature spotlight (optional) — the "Introducing Memory" style panel
  spotlight?: {
    kicker: string; // small label above, e.g. "Under the hood"
    title: string; // big serif feature name
    tagline: string;
    mockupLabel: string;
    gradient: string;
  };

  // §5 Impact + proof (optional)
  impact?: {
    heading: string;
    stats: Stat[];
    testimonials: Testimonial[];
  };

  // §6 "In action" catalog (optional)
  catalog?: {
    items: CatalogItem[];
  };
};
