import { SolutionPage } from '@/components/solutions/detail/solution-page';
import { legalOps } from '@/content/solutions/legal-ops';

export const metadata = {
  title: 'Legal Operations — Precedent',
  description:
    'Run the whole contract lifecycle from one system: set the standards, enforce them on every deal, and see the entire portfolio — from first draft to renewal.',
};

export default function LegalOpsPage() {
  return <SolutionPage data={legalOps} />;
}
