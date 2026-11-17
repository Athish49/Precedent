import { Nav } from '@/components/nav';
import { SolutionsOverview } from '@/components/solutions/solutions-overview';
import { CtaFooter } from '@/components/landing/cta-footer';

export const metadata = {
  title: 'Solutions — Precedent',
  description:
    'Precedent, framed around the way your team works — legal operations, procurement, and sales / deal desk — and across every kind of paper you sign.',
};

export default function SolutionsPage() {
  return (
    <div style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)' }}>
      <Nav />
      <SolutionsOverview />
      <CtaFooter />
    </div>
  );
}
