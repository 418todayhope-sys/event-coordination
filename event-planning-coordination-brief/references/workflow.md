# Workflow and snapshot operations

## Run contract

Read the unchanged root `snapshot.schema.json` rather than maintaining a competing
schema here. The required schema version is
`event-coordination-stage-snapshot/2`. A run has nine numbered snapshots in
`deliverables/snapshots/`, named `01-<stage>.json` through `09-<stage>.json` using
the stage identifiers below. All share one run ID and have distinct snapshot IDs.

Record actual execution time in `created_at`. Record the fixed business clock
separately in run context/state: `2026-08-26T12:00:00+08:00`, `Asia/Taipei`.
It is neither the event date nor a substitute for retrieval time.

Stage 1 has a null predecessor and empty consumed IDs. Every later snapshot
references the immediately preceding snapshot's ID, path, and SHA-256 hash of its
exact saved bytes, and consumes at least one real upstream record. Save a
predecessor before hashing it; do not reformat it afterward. Use
`sha256:` plus 64 lowercase hexadecimal digits wherever the schema requires it.
Keep consumed, produced, evidence, and dependency references resolvable. Decisions
require genuine rationale and at least one actual tradeoff; leave the decision
array empty when no decision has been made.

## Stage procedures

| Sequence and stage | Operation and required state |
|---|---|
| 01 `scope-and-approval-gates` | Establish `objective`, `decision_deadline`, `owners`, and `approval_gates` from evidence. Identify Operations and category review roles. Distinguish a known role from a verified named owner. |
| 02 `source-capture` | Populate `sources` with retrieval outcomes, original evidence references, versions, hashes, and located observations. An inaccessible source is a recorded gap. |
| 03 `constraint-model` | Populate `hard_constraints`, `preferences`, `assumptions`, `unknowns`, and `conflicts`. Record interpretation and evidence rather than silently resolving ambiguity. |
| 04 `planning-baseline` | Populate `headcount_basis`, `schedule_dependencies`, `budget_baseline`, and `accessibility_baseline`. Show inputs, units, formulas, overlap handling, and unresolved dependencies. |
| 05 `option-generation` | Populate `options` and `rejected_early`. Compare evidence-backed alternatives before narrowing around familiar suppliers. Explain early exclusions; do not invent vendors to enlarge the comparison. |
| 06 `feasibility-testing` | Populate `option_results` and `unresolved_conditions`. Evaluate capacity, service scope, quote validity, category and total budgets, calendar windows, accessibility, and applicable operational tests. Use the schema's feasible/infeasible/conditional/unverified classifications. |
| 07 `decision-and-approval` | Populate `recommendation`, `tradeoffs`, `learner_decisions`, and `approval_requirements`. A recommendation may be null. Record only decisions actually supplied by the learner and evidence-supported approvals. |
| 08 `draft-propagation` | Populate `artifact_drafts`, `affected_dependencies`, and `unresolved_items`. Generate consistent drafts from the shared planning basis and disclose outstanding conditions and reviews. |
| 09 `publication-validation` | Populate `artifacts`, `validation_checks`, and `publication_status`. Verify the local draft package and its hashes. Validation does not publish or grant approval. |

Use `complete` for a stage whose required work is supported and finished,
`partial` for useful work with outstanding work, `blocked` where missing evidence
or a decision prevents progress, and `failed` for an execution or validation
failure. Explain the status in unresolved records. Do not force downstream
success when upstream conditions remain unresolved.

The schema requires some concrete fields even for blocked snapshots, notably a
date-time decision deadline in stage 1. If a required value is unavailable, report
the contract/data gap and stop that snapshot's validation claim. Never insert a
fake date or business value to manufacture nine passing snapshots. Resolve the
gap with the learner before completing the chain.

## Draft package

Produce these paths only when generation is authorized and implemented:

- `deliverables/vendor-comparison.csv`: source-linked scope, capacity, validity,
  costs, constraints, feasibility, and reasons for comparison outcomes.
- `deliverables/event-plan.md`: objectives, headcount basis, options and rationale,
  budget allocations, accessibility responses, run of show, risks, and reviews.
- `deliverables/event-calendar.ics`: timezone-aware schedule drafts consistent
  with access windows and the run of show; no invitation transmission.
- `deliverables/draft-communications.md`: audience-specific draft messages,
  unresolved details, and required review before release.

Preserve retrieved original evidence and hashes alongside the package. Artifact
hashes describe actual bytes. For a missing artifact, do not invent a hash to fill
an artifact record; record the omission as unresolved and flag the schema's
required-hash representation issue for resolution.

## Dependency propagation and revisions

Maintain explicit edges from source observations to constraints/calculations,
options, decisions, approval scope, and artifact sections or calendar entries.
For each changed source:

1. Compare versions and hashes, retaining the old evidence and retrieval history.
2. Identify the earliest affected basis and traverse its downstream dependencies.
3. Mark impacted results and approvals as requiring reevaluation; retain the
   historical approval evidence without treating it as approval of changed scope.
4. Recompute affected costs, capacities, timing, and feasibility. Update all
   affected drafts, including allocations, run of show, calendar, and messages.
5. Cross-check against current evidence and route revisions to the affected owners.

Preserve completed chains. Create a new run ID for revised runs and retain prior
packages under `runs/<run-id>/`; never overwrite a predecessor in a preserved
chain. Reused records must still resolve to retained evidence and be rechecked for
applicability. Archiving mechanics remain to be implemented.

## Validation and handoff

Use Draft 2020-12 schema validation with date-time format checking. Separately
check all nine stage/sequence pairs, shared run ID, predecessor hashes, reference
integrity, evidence and artifact hashes, arithmetic, constraints, and consistency
across drafts. Parse the ICS and ensure it matches the event plan's dates, timezone,
and access windows. Distinguish structural validity, business feasibility, approval
status, and publication readiness. A package can have valid files while release
remains blocked. Report those outcomes separately and never report an unexecuted
check as passed.
