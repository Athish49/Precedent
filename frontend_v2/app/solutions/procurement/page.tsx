import { SolutionPage } from '@/components/solutions/detail/solution-page';
import { procurement } from '@/content/solutions/procurement';

export const metadata = {
  title: 'Procurement & Sourcing — Precedent',
  description:
    'Review vendor paper at the speed you sign it: Precedent reads every inbound agreement against your standards on intake, surfaces risk, redlines the gaps, and clears the routine so procurement stops waiting on legal.',
};

export default function ProcurementPage() {
  return <SolutionPage data={procurement} />;
}
