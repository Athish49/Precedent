import { SolutionPage } from '@/components/solutions/detail/solution-page';
import { sales } from '@/content/solutions/sales';

export const metadata = {
  title: 'Sales / Deal Desk — Precedent',
  description:
    'Close deals without the legal bottleneck: routine paper clears automatically against pre-approved positions, reps get a redline in minutes, and only genuine risk escalates to a lawyer.',
};

export default function SalesPage() {
  return <SolutionPage data={sales} />;
}
