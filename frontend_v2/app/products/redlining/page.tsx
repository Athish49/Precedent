import { ProductPage } from '@/components/products/detail/product-page';
import { redliningNegotiation } from '@/content/products/redlining';

export const metadata = {
  title: 'Redlining & Negotiation — Precedent',
  description: 'Turn flagged clauses into surgical, counterparty-ready redlines shaped by how each counterparty negotiates.',
};

export default function RedliningPage() {
  return <ProductPage data={redliningNegotiation} />;
}
