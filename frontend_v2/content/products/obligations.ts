import type { ProductPageData } from '@/components/products/detail/types';

// Obligations & Monitoring — maps to backend Service 8 (Obligations & Monitoring).
export const obligationsMonitoring: ProductPageData = {
  slug: 'obligations',
  name: 'Obligations & Monitoring',

  hero: {
    headline: 'Never miss a deadline or renewal again.',
    pitch: 'Precedent tracks every commitment and returns alerts before anything ever slips.',
  },

  heroImage: {
    label: 'Obligations & Monitoring — tracker mockup',
    gradient: 'linear-gradient(135deg, #f43f5e, #fb7185, #f59e0b)',
  },

  capabilities: {
    sectionTitle: 'Every commitment, tracked the moment it lands',
    sectionIntro:
      'The obligations hide in the fine print. Precedent pulls each one out at ingest and watches them for you — so your team stops chasing calendars and starts trusting the system.',
    cards: [
      {
        title: 'Obligations, extracted at ingest',
        blurb:
          'The instant a contract lands, Precedent lifts out every commitment, deadline, and deliverable — each with an owner attached.',
        mockupLabel: 'Obligation extraction — owner, deadline, deliverable',
        gradient: 'linear-gradient(135deg, #e11d48, #f43f5e)',
        points: [
          {
            title: 'Owner, deadline, deliverable',
            desc: 'Each obligation is captured as a clean record — who owns it, when it is due, and exactly what has to happen.',
          },
          {
            title: 'Grounded in the contract',
            desc: 'Extraction is anchored to the contract’s own metadata, so nothing is invented and nothing is missed.',
          },
          {
            title: 'No manual entry',
            desc: 'The tracker fills itself at ingest — your team never has to key obligations into a spreadsheet again.',
          },
        ],
      },
      {
        title: 'A daily monitor that never sleeps',
        blurb:
          'One deterministic pass a day checks every obligation on file — firing deadline alerts and flagging renewal windows before they close.',
        mockupLabel: 'Daily monitor — deadline & renewal sweep',
        gradient: 'linear-gradient(135deg, #f43f5e, #f97316)',
        points: [
          {
            title: 'Deadline alerts on time',
            desc: 'When a due date falls inside your threshold, the monitor raises an alert — early enough to actually act on it.',
          },
          {
            title: 'Renewal windows caught early',
            desc: 'Any contract 30–90 days from expiry surfaces automatically, so renewals are a decision, not a surprise.',
          },
          {
            title: 'Deterministic, every day',
            desc: 'The same rules run once a day across your whole portfolio — predictable coverage, no gaps, no guesswork.',
          },
        ],
      },
      {
        title: 'Renewal recommendations, decided',
        blurb:
          'For every contract nearing expiry, Precedent bundles a clear recommendation — extend, renegotiate, or close — with a compliance check attached.',
        mockupLabel: 'Renewal recommendation — extend / renegotiate / close',
        gradient: 'linear-gradient(135deg, #fb7185, #f59e0b)',
        points: [
          {
            title: 'A recommendation, not a reminder',
            desc: 'Each renewal arrives with a suggested path — extend, renegotiate, or close — so the next step is obvious.',
          },
          {
            title: 'Compliance in the same view',
            desc: 'A check against your current playbook rides alongside the recommendation, flagging drift before you re-sign.',
          },
        ],
      },
      {
        title: 'Compliance, on demand',
        blurb:
          'Verify any contract against your current playbook whenever you need it — on upload, on renewal, or the moment a question comes up.',
        mockupLabel: 'Compliance check — contract vs current playbook',
        gradient: 'linear-gradient(135deg, #ef4444, #fb7185)',
        points: [
          {
            title: 'Check on upload or on demand',
            desc: 'Run compliance automatically as contracts arrive, or trigger it any time against the standards you enforce today.',
          },
          {
            title: 'Measured against your playbook',
            desc: 'Every check compares the live contract to your current playbook, so results reflect your rules right now — not last year’s.',
          },
        ],
      },
    ],
  },

  spotlight: {
    kicker: 'Runs while you sleep',
    title: 'The Daily Monitor',
    tagline:
      'One deterministic pass a day sweeps every obligation on file — checking deadlines and renewal windows so nothing ever slips through overnight.',
    mockupLabel: 'Daily monitor — one pass, whole portfolio',
    gradient: 'linear-gradient(135deg, #be123c, #f43f5e, #f59e0b)',
  },

  impact: {
    heading: 'Monitoring, by the numbers',
    stats: [
      { value: 100, suffix: '%', label: 'of obligations tracked from ingest' },
      { value: 0, label: 'missed renewal windows' },
      { value: 90, suffix: '%', label: 'less time spent watching calendars' },
    ],
    testimonials: [
      {
        quote:
          'We used to find out about a renewal when it had already auto-extended. Now Precedent flags it 90 days out with a recommendation and a compliance check — we just decide.',
        name: 'Priya Raman',
        role: 'Director, Contract Operations',
        firm: 'Meridian',
      },
      {
        quote:
          'The daily monitor is the part I trust. Every obligation gets checked once a day, every day. Nothing sits in someone’s inbox waiting to be missed.',
        name: 'Elliot Grant',
        role: 'Associate General Counsel',
        firm: 'Halcyon',
      },
    ],
  },

  catalog: {
    items: [
      {
        name: 'Obligation extraction',
        desc: 'Pull every commitment, deadline, and deliverable out of a contract at ingest — each with an owner attached.',
        mockupLabel: 'Obligation extraction',
        gradient: 'linear-gradient(135deg, #e11d48, #f43f5e)',
      },
      {
        name: 'Deadline alerts',
        desc: 'Fire an alert whenever a due date falls inside your threshold, early enough to act.',
        mockupLabel: 'Deadline alerts',
        gradient: 'linear-gradient(135deg, #f43f5e, #f97316)',
      },
      {
        name: 'Renewal recommendations',
        desc: 'Bundle an extend / renegotiate / close recommendation for any contract 30–90 days from expiry.',
        mockupLabel: 'Renewal recommendations',
        gradient: 'linear-gradient(135deg, #fb7185, #f59e0b)',
      },
      {
        name: 'Compliance checks',
        desc: 'Verify a contract against your current playbook on upload, on renewal, or on demand.',
        mockupLabel: 'Compliance checks',
        gradient: 'linear-gradient(135deg, #ef4444, #fb7185)',
      },
      {
        name: 'Acknowledgements',
        desc: 'Route alerts to the UI or your notification system, where they can be acknowledged and cleared.',
        mockupLabel: 'Acknowledgements',
        gradient: 'linear-gradient(135deg, #f59e0b, #f43f5e)',
      },
    ],
  },
};
