import { ProductPage } from '@/components/products/detail/product-page';
import { playbooksStandards } from '@/content/products/playbooks';

export const metadata = {
  title: 'Playbooks & Standards — Precedent',
  description: 'Turn your executed contracts into live rules and enforce your standards automatically on every deal.',
};

export default function PlaybooksPage() {
  return <ProductPage data={playbooksStandards} />;
}
