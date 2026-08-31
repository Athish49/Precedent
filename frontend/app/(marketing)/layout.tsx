import { MarketingNav } from '@/components/shell/marketing-nav';

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <MarketingNav />
      <main>{children}</main>
    </>
  );
}
