import { ProductPage } from '@/components/products/detail/product-page';
import { documentIntelligence } from '@/content/products/document-intelligence';

export const metadata = {
  title: 'Document Intelligence — Precedent',
  description: 'Ask any contract anything and get a cited answer drawn straight from the clause text.',
};

export default function DocumentIntelligencePage() {
  return <ProductPage data={documentIntelligence} />;
}
