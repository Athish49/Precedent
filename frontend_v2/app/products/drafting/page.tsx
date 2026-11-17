import { ProductPage } from '@/components/products/detail/product-page';
import { draftingStudio } from '@/content/products/drafting';

export const metadata = {
  title: 'Drafting Studio — Precedent',
  description:
    'Generate polished first drafts, clauses, and memos in minutes — built from your own templates and playbook.',
};

export default function DraftingStudioPage() {
  return <ProductPage data={draftingStudio} />;
}
