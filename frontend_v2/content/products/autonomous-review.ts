import type { ProductPageData } from '@/components/products/detail/types';

// Autonomous Review — maps to backend "Review Pipeline & Autonomous Trigger".
export const autonomousReview: ProductPageData = {
  slug: 'autonomous-review',
  name: 'Autonomous Review',

  hero: {
    headline: 'Routine review, handled end to end.',
    pitch: 'Precedent reviews every incoming contract and returns clean redlines the moment it lands.',
  },

  heroImage: {
    label: 'Autonomous Review — pipeline mockup',
    gradient: 'linear-gradient(135deg, #8b5cf6, #a855f7, #ec4899)',
  },

  capabilities: {
    sectionTitle: 'Review that runs itself',
    sectionIntro:
      'The moment a contract arrives, Precedent parses it, checks it against your playbook, analyzes the risk, and redlines it — so your team only ever looks at the deals that actually need judgment.',
    cards: [
      {
        title: 'Triggered the moment it lands',
        blurb:
          'No queue to watch, no button to press — an upload fires the pipeline automatically, so review starts before anyone opens the file.',
        mockupLabel: 'Event trigger — webhook / queue',
        gradient: 'linear-gradient(135deg, #7c3aed, #a855f7)',
        points: [
          {
            title: 'Event-driven start',
            desc: 'A webhook or queue message kicks off review the instant a document is uploaded — nothing waits on a human to notice.',
          },
          {
            title: 'Code-owned flow',
            desc: 'The pipeline is orchestrated in code, not by a model deciding what to do next — so every contract follows the same reliable path.',
          },
        ],
      },
      {
        title: 'Parse, playbook, analyze, redline',
        blurb:
          'A full review pipeline runs end to end — from raw document to marked-up redlines — without a hand-off in between.',
        mockupLabel: 'Pipeline — parse → playbook → analyze → redline',
        gradient: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
        points: [
          {
            title: 'Parse and fetch in parallel',
            desc: 'Document parsing and playbook retrieval run concurrently, so the pipeline is ready to analyze the moment the text is extracted.',
          },
          {
            title: 'Analyze, then redline',
            desc: 'Contract analysis feeds straight into redlining — issues are found and corrected in one continuous pass.',
          },
          {
            title: 'One uninterrupted run',
            desc: 'From upload to finished redlines, the whole review completes without a manual step in the middle.',
          },
        ],
      },
      {
        title: 'A gate you can trust',
        blurb:
          'A deterministic threshold gate decides what ships automatically and what a human must see — and it never skips the things that matter.',
        mockupLabel: 'Threshold gate — hard-stop rules',
        gradient: 'linear-gradient(135deg, #a855f7, #d946ef)',
        points: [
          {
            title: 'Hard-stops, not just a score',
            desc: 'Any prohibited or missing clause, any quality failure, or a single high-risk clause always escalates to a person — no aggregate can override that.',
          },
          {
            title: 'Auto-apply the routine',
            desc: 'When a contract is clean, the gate applies the redlines on its own and moves the deal forward — no waiting on a reviewer.',
          },
          {
            title: 'Escalate the exceptions',
            desc: 'Only contracts that trip a rule reach a human, so your team spends its time exactly where judgment is needed.',
          },
        ],
      },
      {
        title: 'Every change, explained and logged',
        blurb:
          'Autonomous does not mean opaque — each redline carries its reasoning, and every human decision is remembered.',
        mockupLabel: 'Rationale + audit trail',
        gradient: 'linear-gradient(135deg, #c026d3, #8b5cf6)',
        points: [
          {
            title: 'Rationale on every change',
            desc: 'Each redline is attached to the reason it was made, so a reviewer can see the "why" at a glance.',
          },
          {
            title: 'Full audit trail',
            desc: 'Every step of the pipeline and every accept or reject is recorded end to end for compliance and review.',
          },
          {
            title: 'Decisions become memory',
            desc: 'Each human accept or reject is logged to Negotiation Memory, so the system gets smarter with every deal.',
          },
        ],
      },
    ],
  },

  spotlight: {
    kicker: 'You stay in control',
    title: 'The Threshold Gate',
    tagline:
      'Clean contracts ship on their own; anything prohibited, missing, or high-risk stops and waits for you — so nothing important is ever decided without a human.',
    mockupLabel: 'Threshold gate — auto-apply vs. escalate',
    gradient: 'linear-gradient(135deg, #7c3aed, #a855f7, #ec4899)',
  },

  impact: {
    heading: 'Autonomous review, by the numbers',
    stats: [
      { value: 80, suffix: '%', label: 'of routine contracts cleared without a reviewer' },
      { value: 15, suffix: 'x', label: 'faster turnaround on standard agreements' },
      { value: 100, suffix: '%', label: 'of high-risk contracts routed to a human' },
    ],
    testimonials: [
      {
        quote:
          'Standard NDAs and order forms now redline themselves the second they hit our inbox. My team only sees the deals that trip a hard-stop — which is exactly where we want to be.',
        name: 'Priya Raman',
        role: 'Director of Legal Operations',
        firm: 'Halcyon',
      },
      {
        quote:
          'The gate is what sold us. We know a prohibited or missing clause will always come to a person — no score can wave it through. That let us turn autonomy on without losing a wink of sleep.',
        name: 'Thomas Beck',
        role: 'Deputy General Counsel',
        firm: 'Ridgeline',
      },
    ],
  },

  catalog: {
    items: [
      {
        name: 'Auto-apply clean redlines',
        desc: 'When a contract clears every rule, Precedent applies its redlines automatically and advances the deal — no reviewer required.',
        mockupLabel: 'Auto-apply',
        gradient: 'linear-gradient(135deg, #7c3aed, #a855f7)',
      },
      {
        name: 'Escalate to a human',
        desc: 'Any contract that trips the gate is routed to a person with its redlines and reasoning ready to review.',
        mockupLabel: 'Escalate',
        gradient: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
      },
      {
        name: 'Hard-stop rules',
        desc: 'Prohibited, missing, or high-risk clauses and quality failures always force a human review — never an aggregate score.',
        mockupLabel: 'Hard-stop rules',
        gradient: 'linear-gradient(135deg, #a855f7, #d946ef)',
      },
      {
        name: 'Rationale on every change',
        desc: 'Each redline arrives with the reasoning behind it, so reviewers understand the "why" instantly.',
        mockupLabel: 'Rationale',
        gradient: 'linear-gradient(135deg, #c026d3, #8b5cf6)',
      },
      {
        name: 'Audit trail',
        desc: 'Every pipeline step and every accept or reject is logged end to end, and decisions flow into Negotiation Memory.',
        mockupLabel: 'Audit trail',
        gradient: 'linear-gradient(135deg, #9333ea, #ec4899)',
      },
    ],
  },
};
