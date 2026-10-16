# Decisions and human approval boundaries

## Authority and evidence

Operations approves the overall plan, date, venue, and hard-constraint alignment.
Named category budget owners authorize spending within their categories. Category
amounts above approval limits require explicit owner authorization for the amount
and plan; no category exception permits exceeding the overall budget ceiling.
Identify actual owners and limits from the disclosed sources rather than guessing.

Approval must have genuine supporting evidence identifying the authorized person
or role, the decision, the applicable amount/category or plan scope, and the
version or conditions covered. Preserve the source and precise locator and any
available timestamp. If authority, scope, or authenticity cannot be established,
record the uncertainty and keep approval pending. The interview's description of
approval policy is not an approval of a particular plan.

Use schema statuses honestly:

- `pending`: no sufficient evidence of a decision, including missing approval.
- `approved`: explicit evidence from the responsible authority covers this scope.
- `rejected`: genuine rejection evidence; preserve reasons and affected scope.
- `not-required`: supported policy establishes that this approval does not apply;
  never use it to bypass missing evidence.

Record learner decisions only when actually supplied by the learner, with
rationale and tradeoffs. Distinguish an agent recommendation from a learner
decision, a learner decision from owner approval, and owner approval from
authorization for an external action. Approval to implement software is not
permission to spend or publish. No validation process may invent an approval to
obtain a passing result.

## Review handoff

Prepare a draft review package showing objective, proposed headcount, evidence for
hard constraints, costs by category and total, options/tradeoffs, risks, unresolved
conditions, and exact decisions requested. Route overall plan/date/venue matters
to Operations and spending matters to the relevant category owner. Preparing this
handoff does not authorize sending messages or contacting reviewers.

All generated planning outputs and communications remain drafts, including those
whose source evidence contains approvals. While approval is pending, no final
bookings, communication releases, or external commitments may be finalized.
Humans finalize bookings and commitments. Spending, invitations, and publishing
also require explicit human authorization; creating local Markdown, CSV, or ICS
does not grant it. Keep ICS drafts tentative and avoid invitation-sending behavior.

Stage 9's `publication_status` describes validation/readiness of the local draft
package, not proof that an external publication occurred. Report pending release
authorization separately. A syntactically valid draft can remain blocked for
business use, and an approved amount can still belong to an infeasible option.

## Changed scope and stopping conditions

When attendance, quotes, venue access, accessibility needs, or allocations change,
map impacts to the relevant decisions and approvals. Preserve the historical
evidence, mark affected scope as requiring renewed review, and keep authorization
pending unless genuine evidence explicitly covers the revision. Reevaluate from
the earliest affected basis and propagate all dependent drafts before review.

Stop the affected action when evidence, authority, required decisions, or hard
constraints cannot be established. Continue independent authorized analysis and
prepare an honest partial or blocked handoff. State the missing evidence and
responsible role when known; do not fabricate approval, send an interview prompt,
or make an external commitment to unblock the run.
