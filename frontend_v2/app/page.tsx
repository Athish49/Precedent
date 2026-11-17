import { Nav } from '@/components/nav';
import { Hero } from '@/components/landing/hero';
import { LogoWall } from '@/components/landing/logo-wall';
import { Problem } from '@/components/landing/problem';
import { HowItWorks } from '@/components/landing/how-it-works';
import { Capabilities } from '@/components/landing/capabilities';
import { Services } from '@/components/landing/services';
import { Deterministic } from '@/components/landing/deterministic';
import { Impact } from '@/components/landing/impact';
import { Autonomous } from '@/components/landing/autonomous';
import { Testimonials } from '@/components/landing/testimonials';
import { Security } from '@/components/landing/security';
import { FAQ } from '@/components/landing/faq';
import { CtaFooter } from '@/components/landing/cta-footer';

export default function LandingPage() {
  return (
    <div style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)' }}>
      <Nav />
      <Hero />
      <LogoWall />
      <Problem />
      <HowItWorks />
      <Capabilities />
      <Services />
      <Deterministic />
      <Impact />
      <Autonomous />
      <Testimonials />
      <Security />
      <FAQ />
      <CtaFooter />
    </div>
  );
}
