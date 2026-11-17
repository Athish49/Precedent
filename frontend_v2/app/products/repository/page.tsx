import { ProductPage } from '@/components/products/detail/product-page';
import { repositorySearch } from '@/content/products/repository';

export const metadata = {
  title: 'Repository & Search — Precedent',
  description: 'Every contract in one searchable home — keyword, faceted, and Smart Search to the clause.',
};

export default function RepositoryPage() {
  return <ProductPage data={repositorySearch} />;
}
