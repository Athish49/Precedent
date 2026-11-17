import { Nav } from '@/components/nav';
import { ProductsOverview } from '@/components/products/products-overview';
import { CtaFooter } from '@/components/landing/cta-footer';

export default function ProductsPage() {
  return (
    <div style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)' }}>
      <Nav />
      <ProductsOverview />
      <CtaFooter />
    </div>
  );
}
