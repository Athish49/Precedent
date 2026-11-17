import type { ProductPageData } from '@/components/products/detail/types';

// Playbooks & Standards — maps to backend Service 6 (Playbook & Rules).
export const playbooksStandards: ProductPageData = {
  slug: 'playbooks',
  name: 'Playbooks & Standards',

  hero: {
    headline: 'Your standards, enforced on every deal.',
    pitch: 'Precedent turns your playbook into live rules and applies them to every contract automatically.',
  },

  heroImage: {
    label: 'Playbooks & Standards — rule store mockup',
    gradient: 'linear-gradient(135deg, #0ea5e9, #6366f1, #8b5cf6)',
  },

  capabilities: {
    sectionTitle: 'One source of truth for what "good" looks like',
    sectionIntro:
      'Every clause type gets a single, owned rule-set — so the standards your team agrees on are the standards enforced on every deal, without anyone re-checking by hand.',
    cards: [
      {
        title: 'One store per clause type',
        blurb:
          'For each clause, define what you want, what you’ll accept, what you’ll never sign, and where you land when you have to give ground.',
        mockupLabel: 'Clause rule store — preferred, acceptable, prohibited, fallback',
        gradient: 'linear-gradient(135deg, #0ea5e9, #3b82f6)',
        points: [
          {
            title: 'Preferred and acceptable, side by side',
            desc: 'Hold your ideal language plus the acceptable variations you already tolerate — so review knows the difference between perfect and fine.',
          },
          {
            title: 'Prohibited terms, drawn hard',
            desc: 'Mark the language you will never accept once, and it’s flagged everywhere it appears.',
          },
          {
            title: 'Fallback for the give-and-take',
            desc: 'Capture where you land when you have to concede, so negotiators always have a pre-approved next position.',
          },
        ],
      },
      {
        title: 'One-time AI bootstrap from your own paper',
        blurb:
          'Start from your executed contracts, not a blank template — Precedent reads what you’ve already signed and proposes a playbook to approve.',
        mockupLabel: 'Bootstrap — executed corpus to seeded playbook',
        gradient: 'linear-gradient(135deg, #3b82f6, #6366f1)',
        points: [
          {
            title: 'Seeded from what you’ve signed',
            desc: 'A single AI pass over your already-executed contracts suggests preferred language and acceptable variations per clause type.',
          },
          {
            title: 'Sensible defaults out of the box',
            desc: 'Prohibited terms come pre-populated from template defaults, so you’re never starting from zero.',
          },
        ],
      },
      {
        title: 'Practice-area routing, merged by precedence',
        blurb:
          'The right rules for the right deal — Precedent picks every applicable rule-set and combines them in a fixed, predictable order.',
        mockupLabel: 'Routing — HIPAA / GDPR / MSA / NDA / DPA merge',
        gradient: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
        points: [
          {
            title: 'All applicable rule-sets selected',
            desc: 'HIPAA, GDPR, SaaS MSA, NDA, DPA — every rule-set that applies to the deal is pulled in automatically.',
          },
          {
            title: 'Merged by fixed precedence',
            desc: 'Overlapping rules resolve in a consistent, defined order, so the outcome is the same every time.',
          },
        ],
      },
      {
        title: 'Self-service CRUD — legal owns every rule',
        blurb:
          'Change a standard the moment you decide to — your legal team edits rules directly, and the change lands on every deal without waiting on engineering.',
        mockupLabel: 'Self-service rule editor — no engineers',
        gradient: 'linear-gradient(135deg, #8b5cf6, #0ea5e9)',
        points: [
          {
            title: 'No engineers in the loop',
            desc: 'Create, update, and retire rules through a self-service interface — legal owns the playbook end to end.',
          },
          {
            title: 'Applied everywhere, instantly',
            desc: 'Playbooks feed Contract Analysis and Redlining downstream, so a rule change is enforced on the next contract you touch.',
          },
        ],
      },
    ],
  },

  spotlight: {
    kicker: 'Set up in a day',
    title: 'One-Time Bootstrap',
    tagline:
      'Point Precedent at the contracts you’ve already signed and it drafts your playbook for you — preferred language and acceptable variations, ready for your team to review and own.',
    mockupLabel: 'Bootstrap — corpus to approved playbook',
    gradient: 'linear-gradient(135deg, #0284c7, #4f46e5, #7c3aed)',
  },

  impact: {
    heading: 'Standards that actually stick',
    stats: [
      { value: 100, suffix: '%', label: 'of deals checked against your playbook' },
      { value: 1, suffix: '-day', label: 'to a playbook seeded from your own contracts' },
      { value: 0, label: 'engineering tickets to change a rule' },
    ],
    testimonials: [
      {
        quote:
          'The bootstrap did in an afternoon what would have taken us a quarter. It read our signed contracts and handed us a playbook that already looked like our positions — we just approved it.',
        name: 'Priya Nandakumar',
        role: 'Associate General Counsel',
        firm: 'Meridian Health',
      },
      {
        quote:
          'When we change a standard, it’s live on the next deal — no ticket, no waiting. Our positions are finally enforced consistently instead of living in someone’s head.',
        name: 'Tom Rasmussen',
        role: 'Director, Contract Standards',
        firm: 'Cobalt Systems',
      },
    ],
  },

  catalog: {
    items: [
      {
        name: 'Preferred language',
        desc: 'Your ideal clause for each type — the language you reach for first on every deal.',
        mockupLabel: 'Preferred language',
        gradient: 'linear-gradient(135deg, #0ea5e9, #3b82f6)',
      },
      {
        name: 'Acceptable variations',
        desc: 'The alternate wordings you already tolerate, so fine isn’t mistaken for a problem.',
        mockupLabel: 'Acceptable variations',
        gradient: 'linear-gradient(135deg, #3b82f6, #6366f1)',
      },
      {
        name: 'Prohibited terms',
        desc: 'The language you’ll never sign — defined once, flagged everywhere it appears.',
        mockupLabel: 'Prohibited terms',
        gradient: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
      },
      {
        name: 'Fallback language',
        desc: 'Where you land when you concede — a pre-approved next position for negotiation.',
        mockupLabel: 'Fallback language',
        gradient: 'linear-gradient(135deg, #8b5cf6, #a855f7)',
      },
      {
        name: 'Practice-area routing',
        desc: 'HIPAA, GDPR, MSA, NDA, DPA rule-sets selected and merged by fixed precedence.',
        mockupLabel: 'Practice-area routing',
        gradient: 'linear-gradient(135deg, #a855f7, #0ea5e9)',
      },
    ],
  },
};
