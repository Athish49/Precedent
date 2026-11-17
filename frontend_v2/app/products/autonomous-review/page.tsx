import { ProductPage } from '@/components/products/detail/product-page';
import { autonomousReview } from '@/content/products/autonomous-review';

export const metadata = {
  title: 'Autonomous Review — Precedent',
  description: 'Event-triggered contract review that redlines clean deals automatically and escalates the risky ones.',
};

export default function AutonomousReviewPage() {
  return <ProductPage data={autonomousReview} />;
}
