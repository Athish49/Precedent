import { ProductPage } from '@/components/products/detail/product-page';
import { obligationsMonitoring } from '@/content/products/obligations';

export const metadata = {
  title: 'Obligations & Monitoring — Precedent',
  description: 'Track every commitment and get alerted before any deadline or renewal slips.',
};

export default function ObligationsPage() {
  return <ProductPage data={obligationsMonitoring} />;
}
