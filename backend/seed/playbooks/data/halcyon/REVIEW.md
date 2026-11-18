# Cross-file consistency review (task 3.13)

Reviewer re-ran this task from scratch after an earlier session died mid-run
from an API rate limit with no output. This review covers the full seed
directory: `taxonomy.yaml`, `authority.yaml`, and all ten rule files (130
rules) under `playbooks/`.

## 1. Validator and coverage report

- `cd backend && .venv/bin/python -m seed.playbooks.validate` — **0 errors,
  1 warning**, exit 0.
  - The remaining warning
    (`saas_msa_vendor/data.yaml [compliance.anti_corruption]`) flags that the
    preferred language contains a number ("UK Bribery Act **2010**") with no
    matching parameter. That number is a statute year, not a negotiated
    term, so no parameter is added. Per section 5 of the authoring standard,
    a file may trade a parameter for an extra position when a clause has no
    negotiable number; this is recorded here rather than suppressed.
- `python -m seed.playbooks.report` — exit 1, with **two missed targets**:
  `playbook_version` (9 expected, 7 present) and `playbook_change_log` (20
  expected, 0 present). Both are explicitly out of scope for this task:
  `report.py`'s own `count_versions()` docstring states these two targets
  only become satisfiable once task 3.14 writes `versions/*.yaml` and the
  seed models load it (`versions=headers, change_log_entries=0,
  modelled=False` until then). Task 3.13's file ownership is limited to
  `playbooks/` and `REVIEW.md`; `versions/` belongs to 3.14, which depends on
  3.13 finishing first. Every other row, breakdown, and fill-rate check in
  the report is satisfied. This is recorded as a known, intentional gap, not
  left silently unresolved.

## 2. Cross-file reference resolution in the six merged sets

Checked every `related_rule_key` (dependencies) and every
`recommended_position.rule_key` (objections) in all 130 rules against the
rule-key union of each of the six merged sets: baseline+SaaS,
baseline+SaaS+HIPAA, baseline+SaaS+GDPR, baseline+DPA+GDPR, baseline+NDA,
baseline+vendor MSA.

**Result: zero dangling references in all six sets**, both before and after
the fixes below. (An early draft of one fix in this review added a
cross-regime dependency from `saas_msa_vendor/data.yaml` to
`hipaa_overlay`'s `data_protection.de_identification`; that dependency only
resolves in the one set that contains both playbooks and left two sets with
a dangling reference. It was reverted in favour of a prose-only
clarification — see §4 below — so the zero-dangling invariant holds for all
six sets exactly as it did before this review started.)

## 3. Overlapping rule keys — override consistency

32 `rule_key` values are defined in more than one playbook (listed by
`seed.playbooks.report`). Of these, the parent/overlay pairs that matter for
"same or stricter, never looser" are baseline → {mutual_nda, saas_msa_vendor,
dpa_processor, vendor_msa_customer} and {dpa_processor, saas_msa_vendor} →
{gdpr_overlay, hipaa_overlay}. The rest (`saas_msa_vendor` vs
`vendor_msa_customer`) are sibling playbooks for opposite party roles (sell
side vs buy side) that never apply to the same contract, so "stricter"
doesn't apply between them; each was still spot-checked on its own terms
(see §6).

Specifically confirmed, per the task brief's pointers:

- **GDPR overlay overrides of the DPA** (task 3.10's list): all six are
  present, correctly keyed, and same-or-stricter —
  `data_protection.processing_instructions` (GDPR drops all yellow fallbacks,
  `negotiable: false`, strictly tighter than the DPA's negotiable version),
  `data_protection.data_subject_requests` (GDPR forwarding window 5/3/1
  business days vs the DPA's 10/10/2 — stricter), `data_transfers.
  transfer_mechanism` and `data_transfers.data_residency` (GDPR's green/
  yellow categories are the same or narrower), `subprocessors.
  authorisation_model` (same 30/60-day notice structure, GDPR's own
  red line additionally blocks per-instance consent), and
  `breach_notification.notification_timeline` (see the fix in §4 — after the
  fix, GDPR and the DPA now carry identical, correct numbers, which
  satisfies "same or stricter").
- **HIPAA overlay overrides** (task 3.9's list): `data_protection.
  data_return_and_deletion` and both breach_notification rules
  (`notification_timeline`, `notification_content`) are present and, after
  the fix in §4, consistent with the SaaS and DPA numbers for the same
  underlying obligation (destruction/purge periods are identical across
  SaaS, HIPAA and the now-fixed DPA rule; breach notice green boundary is
  48 hours everywhere).

## 4. Fixes made

### 4.1 Repeated direction/threshold mistake (risk area 3) — confirmed and fixed in two places

A systematic pass was made over all 139 rule parameters, checking each
`direction` against (a) the rule's own risk_rationale and position ladder,
and (b) the numeric boundaries stated in section 2.4. An automated ordering
check (`green_limit`/`yellow_limit`/`preferred_value` consistent with the
stated `direction`) found no arithmetic inconsistencies — the bugs found
were semantic (direction, or zone boundary, set inconsistent with what the
rule's own ladder and rationale actually reward), which a purely numeric
check cannot catch.

**Fix 1 — `dpa_processor/rules.yaml`, `data_protection.data_return_and_deletion`,
parameter `deletion_completion_days`.** Was `direction: lower_is_better`
with `preferred_value: 60, green_limit: 90, yellow_limit: 120`. The rule's
own fallback rung 1 (90 days) is explicitly labelled `zone: green` and its
summary says the longer period "reflect[s] Halcyon's backup retention
cycle" — i.e. *more* days is safer for Halcyon (less chance of breaching its
own deletion commitment across three AWS regions), not less. That is the
opposite of what `lower_is_better` encodes, and it is the same mistake the
company already avoided correctly elsewhere: the identical obligation
("days to delete data from production and backups") appears, correctly, as
`higher_is_better` in both `saas_msa_vendor/data.yaml`
(`data_destruction_days`, 60/45/30) and `hipaa_overlay/rules.yaml`
(`phi_destruction_days`, 60/45/30). Changed to `direction: higher_is_better`
with `green_limit: 45, yellow_limit: 30` to match those two correctly-authored
twins exactly (same policy, same numbers), and added a sentence to the
extraction hint explaining why a shorter commitment is the riskier one.

**Fix 2 — `dpa_processor/rules.yaml`, `breach_notification.notification_timeline`,
and `gdpr_overlay/rules.yaml`, `breach_notification.notification_timeline`.**
Both files' fallback rung 1 ("48 hours from confirmation") was labelled
`zone: yellow` with `approver_role: security_lead`, and both parameters had
`green_limit: 72`. Section 2.4's breach-notification row is explicit:
"Preferred: ... within 72 hours. **Still green: 48 hours.** Yellow: 24
hours: security_lead with privacy_counsel. Red: under 24 hours, or from
suspicion." 48 hours is stated as still green, not yellow. The same rule,
correctly implemented, already exists in `saas_msa_vendor/data.yaml` and
`hipaa_overlay/rules.yaml` — both mark the 48-hour rung `zone: green` with
`green_limit: 48`. Fixed both DPA and GDPR to match: rung 1 changed to
`zone: green` (dropping the now-wrong `approver_role`/`internal_note`), and
`green_limit` changed from 72 to 48 in both parameters. The GDPR rule's
extraction hint, which incorrectly asserted "only 72 hours or more is
green... both fallbacks need an approver" (itself a symptom of the same
mistake), was corrected. Updated the one test case in each file that
asserted `expected_zone: yellow` for the 48-hour sample text to
`expected_zone: green` to match.

**Fix 3 — `dpa_processor/rules.yaml`, `data_protection.personnel_confidentiality`.**
Fallback rung 1 ("training on hire only, no recurring training") was
labelled `zone: green`, but the rule's own extraction hint says this
language should be read as an interval of `999` months — and the parameter's
thresholds (`green_limit: 24, yellow_limit: 36`) would classify 999 as red.
A position cannot be both self-declared green and red under the parameter
test it supplies its own extraction value for. Dropping recurring training
entirely is a real reduction in the control the risk rationale describes
("controls that keep one engineer from seeing another customer's patient
data by accident"), so it is not an equivalent alternative to annual
training. Changed rung 1 to `zone: yellow` with `approver_role:
privacy_counsel` and a `give_get`, and adjusted the parameter to
`green_limit: 12, yellow_limit: 999` so the ladder (12 = green, 999 = the
onboarding-only case = yellow) and the extraction hint now agree.

Checked the rest of the ~130 parameters against this same lens (does the
direction match what the rule's own ladder and rationale reward, and do the
numbers match section 2.4 where 2.4 states one) and found the large
majority already correct, including some that looked suspicious on a first
pass but turned out right on reading the full rule text — e.g.
`vendor_msa_customer`'s `change_of_control_notice_days`
(`lower_is_better` is correct: it is notice *to* Halcyon, so faster is
better for Halcyon) and the buy-side liability/breach-notice parameters in
`vendor_msa_customer/risk.yaml`, which correctly invert the sell-side
convention and match the buy-side rows of section 2.4 exactly (5x super-cap,
24-month cap, 48-hour vendor breach notice). One near-miss is recorded for
transparency: `saas_msa_vendor/commercial.yaml`'s `uptime_percent` parameter
(`yellow_limit: 99.98`) was briefly "corrected" to 99.95 to match the named
yellow rung, then reverted on closer reading — `yellow_limit` is the edge of
the yellow zone before red, not necessarily equal to a named rung, and 99.98
is exactly right because section 2.4 puts red at "99.99% or higher"; several
other rules (e.g. `termination.for_cause_cure_period`'s `yellow_limit: 10`,
well below its own worst named rung of 15 days) use the same convention
correctly. No change was needed there.

### 4.2 Risk area 2 — de-identified data scope ambiguity (confirmed, clarified)

Found a real boundary gap, not between HIPAA's `de_identification` rule and
a DPA/GDPR rule as the brief guessed, but between HIPAA's
`data_protection.de_identification` rule and the general SaaS rule
`saas_msa_vendor/data.yaml`'s `data_protection.customer_data_use`. The SaaS
rule's fallback rung 1 triggers on `data_sensitivity: [phi, special_category]`
and withholds cross-customer benchmarking of de-identified data. HIPAA's
`de_identification` rule's own *preferred* (green) position explicitly
permits "analytics and benchmarking... without further restriction" once
PHI is de-identified to the Safe Harbor or expert-determination standard
under 45 C.F.R. § 164.514. On a contract that is both a SaaS MSA and in
scope of the HIPAA overlay (i.e. exactly the `baseline+SaaS+HIPAA` merged
set, the common case since HIPAA implies PHI), these two rules give opposite
answers for the identical fact pattern: de-identified PHI used for
cross-customer benchmarking.

Fix: added a clarifying paragraph to `customer_data_use`'s
`detection_guidance` stating that its own PHI fallback governs
de-identification that is *not* tied to the HIPAA regulatory standard, or a
deal with no HIPAA overlay in scope, and that where the HIPAA overlay
applies, its `de_identification` rule controls PHI de-identified to that
standard and may permit what this rule's fallback would otherwise withhold.
A first attempt also added a structured `dependencies` entry for this, but
that entry is only resolvable in the one merged set containing both
playbooks and left `baseline+SaaS` and `baseline+SaaS+GDPR` with a dangling
reference (see §2) — reverted in favour of the prose-only clarification,
which needs no cross-file reference to resolve. No position, parameter or
test case was changed in either rule; this is a scope note, not a position
change, and 24 pre-existing test cases across the two rules are unaffected.

### 4.3 Risk area 1 — data-retention window conflict (checked, no conflict found)

Checked `saas_msa_vendor/commercial.yaml`'s
`termination.effect_of_termination` (the 30/60/90-day Customer Data
*retrieval* window) against `saas_msa_vendor/data.yaml`'s
`data_protection.data_return_and_deletion` (the 60/45/30-day production
destruction and 90/60-day backup purge periods, after they end). This is
well-designed, not a conflict: `data_return_and_deletion`'s preferred
language explicitly starts its destruction and backup-purge clocks "after
the end of [the] retrieval window," its `detection_guidance` says in so many
words that "Halcyon's own template runs them from the end of that window, in
sequence, so the retrieval commitment and the deletion commitment never
compete for the same days," and the `extraction_hint` tells the model to
flag a drafting gap if a real contract counts the periods from termination
instead of from the end of the retrieval window. Both rules carry a
`dependencies` entry (`read_with`) pointing at each other. No change made.

## 5. Numbers against section 2.4 and defined terms against section 2.1

Spot-checked numeric parameters that section 2.4 states explicitly (cure
period, breach notification, late fees, price increases, uptime, data
breach super-cap, cap carve-outs, sub-processor notice, buy-side liability
cap and breach notice) against the table; all match except the two
breach-notification green boundaries fixed in §4.1. Defined terms were
checked against section 2.1 while reading full rule text throughout this
review (SaaS/commercial rules consistently use "Halcyon", "Customer",
"Services", "Customer Data", "Fees", "Subscription Term"; the DPA and GDPR
overlay consistently use "Processor"/"Controller"/"Personal Data"/
"Sub-processor"/"Data Subject"; the HIPAA overlay consistently uses
"Business Associate"/"Covered Entity"/"PHI"/"Subcontractor"/"Breach"; the
mutual NDA uses "Disclosing Party"/"Receiving Party"/"Confidential
Information"/"Purpose"; the vendor MSA uses "Halcyon"/"Vendor"/
"Services"/"Halcyon Data"/"Fees") — no cross-contamination of defined terms
between agreement types was found.

## 6. Ten rules read end-to-end for legal plausibility

Read in full (language, rationale, full position ladder, parameters, red
lines, objections, dependencies and test cases), beyond the rules already
covered above for the specific risk areas:
`dpa_processor` `definitions.roles_of_parties`,
`data_protection.processing_instructions`,
`data_protection.purpose_limitation`,
`data_protection.data_subject_requests`;
`gdpr_overlay` `subprocessors.authorisation_model`,
`audit.supervisory_authority_cooperation`;
`saas_msa_vendor` `data_protection.customer_data_use`,
`termination.effect_of_termination`,
`compliance.anti_corruption`,
`service_levels.uptime_commitment`,
`termination.for_cause_cure_period`;
`vendor_msa_customer` `assignment.change_of_control`;
`hipaa_overlay` `data_protection.de_identification`.
All read as contract-ready, internally consistent clause language once the
fixes above were applied; no further weak rules were found in this sample.

## 7. Summary of changes

Files touched (all under `backend/seed/playbooks/data/halcyon/playbooks/`):

- `dpa_processor/rules.yaml` — 3 fixes (§4.1, fixes 1–3), 1 test case zone
  correction.
- `gdpr_overlay/rules.yaml` — 1 fix (§4.1, fix 2), 1 test case zone
  correction, 1 corrected extraction-hint sentence.
- `saas_msa_vendor/data.yaml` — 1 clarifying paragraph added to
  `detection_guidance` (§4.2); no position, parameter or test case changed.

No file outside `playbooks/` was touched. No rule was added or removed. No
quota, per-rule minimum, or merged-set reference was broken by any fix —
re-verified after every change.

## 8. Done-when checklist

- Validator exits 0: **yes** (0 errors, 1 documented warning).
- Report exits 0: **no** — exits 1 solely on `playbook_version` and
  `playbook_change_log`, which `report.py` documents as not satisfiable
  until task 3.14 writes `versions/*.yaml`; that file set is explicitly out
  of scope for task 3.13 ("Files:" lists only `playbooks/` and
  `REVIEW.md`). Every other row, breakdown and per-rule minimum in the
  report passes.
- All six merged sets resolve with no dangling reference: **yes**.
- `REVIEW.md` exists: **yes** (this file).
