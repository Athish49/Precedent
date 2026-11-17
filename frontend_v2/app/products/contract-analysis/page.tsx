import { ProductPage } from '@/components/products/detail/product-page';
import { contractAnalysis } from '@/content/products/contract-analysis';

export const metadata = {
  title: 'Contract Analysis — Precedent',
  description: 'Precedent reads any contract and surfaces every risk, cited to the exact line.',
};

export default function ContractAnalysisPage() {
  return <ProductPage data={contractAnalysis} />;
}
