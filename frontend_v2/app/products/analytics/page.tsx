import { ProductPage } from '@/components/products/detail/product-page';
import { analyticsReporting } from '@/content/products/analytics';

export const metadata = {
  title: 'Analytics & Reporting — Precedent',
  description: 'Fast, deterministic dashboards and reports over your live contract portfolio.',
};

export default function AnalyticsPage() {
  return <ProductPage data={analyticsReporting} />;
}
