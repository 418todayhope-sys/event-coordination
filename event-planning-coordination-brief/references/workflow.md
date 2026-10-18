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
packages under `deliverables/history/<run_id>/`; never overwrite a predecessor in a preserved
chain. Reused records must still resolve to retained evidence and be rechecked for
applicability. Managed `execute` now implements bounded archive/recovery mechanics; see the operator instructions.

### Read-only run-contract foundation

`event_coordination.run_contract` implements inspection, planning and scoped
new-run bindings. The separate `pipeline` coordinator executes Stages 01–09 in a
new external workspace; it does not archive evidence or write `failure.json`; Stage 09 performs technical validation only. See the root `IMPLEMENTATION.md` for the executable command.

The coordinator creates a new run UUID and new snapshot UUIDs. Keep original
observation IDs and scope semantic record IDs by run. The proposed Stage 01
`state.run_metadata` contains version 1, run ID, fixed business clock,
`supersedes_run_id`, sorted unique `changed_source_ids` and `changed_decision_ids`,
and evidence-linked `change_reasons`. Stage 01 still has a null predecessor and
empty consumed IDs. Existing snapshots are not retrofitted with this metadata.

Strict metadata validation is structural. Supply both previous and current pinned
manifests to verify changed IDs against actual local byte/path differences.
Several evidence files can share a catalog `source_id`; do not count the event
brief's representations as different disclosed sources. File identity changes
invalidate an active pin even when bytes are identical; comparing two separate
manifests treats unchanged bytes at the same path as the same source version.
Reason evidence IDs must be resolved by the later stage integration: this helper
checks their syntax and presence, not the truth or authority of their assertions.

Hash and parse a predecessor from the same immutable bytes. Check schema with
format validation, run/stage/sequence identity, fixed clock, and the supplied
verified parent, then revalidate pins before returning. This is envelope and
lineage inspection; new-run stage-specific semantic integration remains pending.
`inspect_legacy_run` explicitly pins the historical eight snapshots and schema
and invokes their existing semantic validators. It does not declare Stage 09
complete or grant approval.

Archive planning mirrors selected repository-relative paths beneath
`deliverables/history/<run_id>/`, preserving existing relative evidence links.
It rejects existing destinations, symlinked parents, unsafe paths, recursive
history inclusion, and unrelated files. The plan is non-binding: any future
archive writer must repeat collision, input-integrity, and confinement checks.
Explicit input enumeration is required; the helper does not discover a complete
archive or certify that a caller supplied every required evidence file.

Failure descriptions use controlled codes, actual timezone-aware execution time,
last validated stage, affected paths, and optional expected/observed hashes. A
missing file has no observed hash. Preserve partial outputs for review; do not
overwrite, delete, retry writers, or claim successful recovery. Failure-file
storage and interruption detection are implemented by managed `execute`; incomplete history repair still requires review. Bounded local Stage 01–09 orchestration is implemented separately. Configuration and metadata never authorize business actions.

## Validation and handoff

Use Draft 2020-12 schema validation with date-time format checking. Separately
check all nine stage/sequence pairs, shared run ID, predecessor hashes, reference
integrity, evidence and artifact hashes, arithmetic, constraints, and consistency
across drafts. Parse the ICS and ensure it matches the event plan's dates, timezone,
and access windows. Distinguish structural validity, business feasibility, approval
status, and publication readiness. A package can have valid files while release
remains blocked. Report those outcomes separately and never report an unexecuted
check as passed.

### Managed execution boundary

The Skill `scripts/run.py` delegates to CLI `execute`. It runs all nine stages in
a private candidate, archives prior active evidence/output before promotion and
records semantic source/decision differences in Stage 01. Layout-only changes do
not supersede a run. New paths, actual saved hashes and explicit lineage remain
mandatory. A source revision must already have truthful local registration.

For technical recovery use the documented `--recover` option after examining
`deliverables/failure.json`. The previous run, damaged views and receipts are
preserved; no approvals are copied as granted. Unknown business requirements,
unsupported recommendation deferrals and incomplete/conflicting archive contents
stop for human review rather than being silently resolved.
