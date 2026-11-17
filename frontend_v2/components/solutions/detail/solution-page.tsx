import { Nav } from '@/components/nav';
import { CtaFooter } from '@/components/landing/cta-footer';
import {
  SolutionHero,
  SolutionHeroImage,
  ProofBand,
  PillarsSection,
  UseCasesSection,
  FeaturedTestimonial,
  ImpactStats,
} from './sections';
import type { SolutionPageData } from './types';

// One shell for every "by team" Solutions page, driven entirely by content.
// Section order follows the Harvey law-firms narrative arc — each section is a
// different lens on the persona (position → proof → value → the story → trust →
// outcome), never a re-list of the same capabilities.
export function SolutionPage({ data }: { data: SolutionPageData }) {
  return (
    <div style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)' }}>
      <Nav />
      <SolutionHero hero={data.hero} />
      <SolutionHeroImage heroImage={data.heroImage} />
      <ProofBand proof={data.proof} />
      <PillarsSection pillars={data.pillars} />
      <UseCasesSection useCases={data.useCases} />
      <FeaturedTestimonial featured={data.featured} />
      <ImpactStats impact={data.impact} />
      <CtaFooter />
    </div>
  );
}
