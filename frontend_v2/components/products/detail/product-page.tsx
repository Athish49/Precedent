import { Nav } from '@/components/nav';
import { CtaFooter } from '@/components/landing/cta-footer';
import {
  ProductHero,
  ProductHeroImage,
  CapabilityCards,
  Spotlight,
  ImpactMetrics,
  InActionCatalog,
} from './sections';
import type { ProductPageData } from './types';

// One shell, driven entirely by content. Optional sections (impact, catalog)
// render only when the product has meaningful data for them.
export function ProductPage({ data }: { data: ProductPageData }) {
  return (
    <div style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)' }}>
      <Nav />
      <ProductHero name={data.name} hero={data.hero} />
      <ProductHeroImage heroImage={data.heroImage} />
      <CapabilityCards capabilities={data.capabilities} />
      {data.spotlight && <Spotlight spotlight={data.spotlight} />}
      {data.impact && <ImpactMetrics impact={data.impact} />}
      {data.catalog && <InActionCatalog catalog={data.catalog} />}
      <CtaFooter />
    </div>
  );
}
