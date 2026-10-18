---
name: event-planning-coordination-brief
description: Compare evidence-backed event options, maintain planning dependencies, and prepare consistent event planning drafts for human review using the Project C nine-stage snapshot contract.
---

# Event planning and coordination brief

Produce a review-ready draft package with traceable evidence, explicit uncertainty,
and genuine human decisions. Support initial planning, option comparison, review,
and replanning after source changes. Follow the user's authorized scope; a request
to document or inspect the workflow does not authorize running it.

## Establish context

Locate the project root from the user's workspace; do not assume the working
directory is the Skill directory. Read the root `README.md`,
`snapshot.schema.json`, and original stakeholder export under `interviews/`.
Preserve these files unchanged. For Project C the export is
`interviews/project-c-event-coordination-20261016-1954.md`.
Use the schema as the structural contract and the interview as business context;
use actual disclosed sources to establish current figures and venue observations.
Surface conflicts instead of silently choosing a convenient authority.

Before implementation, verify course session capture as required by the README.
Never run, script, or automate the stakeholder interview. Keep credentials out of
the repository. If a material question requires the stakeholder, give it to the
learner to resolve rather than contacting the interview service.

Project C evaluates business conditions at **2026-08-26 12:00 Asia/Taipei**
(`2026-08-26T12:00:00+08:00`). Retrieval and execution use their actual timestamps.
Do not generalize this exercise clock into a default for other events: obtain
their explicit clock and rules before applying this workflow to a new project.

## Choose the operation

- For a new run, stage execution, snapshot validation, or replanning, read
  [workflow.md](references/workflow.md).
- Before source capture, interpretation, or feasibility judgments, read
  [evidence-and-uncertainty.md](references/evidence-and-uncertainty.md).
- Before recording decisions, evaluating exceptions, or preparing review outputs,
  read [approval-boundaries.md](references/approval-boundaries.md).

Stages 1–7 and Stage 8 in-memory rendering/controlled writing are implemented. Inspect `event-coordination stage1 --help` before
running it. When generation is authorized, use the installed environment's CLI:

```bash
.venv/bin/event-coordination stage1 --project-root /path/to/event-coordination
```

The project root defaults to the current directory. Optional `--run-id` supplies
the ID to retain for later stages; otherwise the command generates one. It reads
the preserved manually completed brief and both stakeholder interviews, verifies
selected evidence, and creates
`deliverables/snapshots/01-scope-and-approval-gates.json`. It validates the schema
with date-time checking and checks provenance/lineage before and after writing.
Existing snapshots cannot be overwritten; use the read-only validation procedure
in the root `IMPLEMENTATION.md` to review one already generated.

Stage 1 records the Operations approval deadline `2026-09-04T17:00:00+08:00` from
the second interview, line 790. It preserves local source hashes, line references,
and the manually completed brief's provenance limitations. Approvals remain pending;
status is partial because individual category-owner assignments remain unresolved.
Stage 1 performs no external source retrieval or event plan, calendar, comparison
CSV, or communication generation.

## Run Stage 2 from preserved evidence

The CLI exposes `stage1` and the bounded `run-stages` coordinator. Individual
Stage 2 execution uses its Python API. Do not invent an `event-coordination stage2` command. Read the
root `IMPLEMENTATION.md`, Stage 2 sections, for capture preparation and validation
limits. Stage 2 reads all registered capture JSON files and verifies their source
identities, interview locators, original-file hashes, and preserved observations.
It performs no online retrieval while assembling or validating.

When generation is authorized and the Stage 2 output is absent, run from the
repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from pathlib import Path
from event_coordination.stages.capture import write_snapshot

path, digest = write_snapshot(Path.cwd())
print(path)
print(digest)
PY
```

The output is `deliverables/snapshots/02-source-capture.json`. It retains Stage 1's
run ID and references the exact approved predecessor bytes by SHA-256. It preserves
separate attempts/representations under seven source identities, without upgrading
retrieval states or resolving conditions. An existing snapshot cannot be overwritten.

For a saved snapshot, use this read-only command instead:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import json
from pathlib import Path
from event_coordination.validation import validate_snapshot

root = Path.cwd()
path = root / "deliverables/snapshots/02-source-capture.json"
validate_snapshot(json.loads(path.read_bytes()), root)
print("Stage 2 schema, evidence hashes, and lineage checks passed")
PY
```

Hash verification establishes byte integrity, not verified remote origin. Source
states `retrieved`, `unavailable`, `invalid`, `unverified`, and `stale` must retain
their evidence-supported meanings. Accepted remote bytes can be `retrieved` while
content identity/completeness still requires inspection. Local registrations remain
`unverified` against the online source; original download times are unknown unless
supported separately. Keep actual attempt/registration times distinct from the
business clock, and manual copies distinct from provider exports and real venue
publications. The current captures include an unsuccessful remote attempt, which
must remain visible with no invented bytes or observations.

Stage 2 can legitimately be `partial`: unknown retrieval times, incomplete exports,
online equivalence, privacy limits, and operational conditions remain unresolved.
Keep the spatial PDF copy in `deliverables/snapshots/evidence/` byte-identical to
the referenced original; packaging that copy does not change existing lineage.
Treat the snapshot as internal evidence and do not copy sensitive attendee needs
into general communications. Preserve all Entire checkpoint history.

## Run Stage 3 constraint modeling

Stage 3 is available through `event_coordination.stages.constraints`, not a CLI
`stage3` subcommand. The CLI also exposes the Stage 01–09 `run-stages` coordinator. Read the root
`IMPLEMENTATION.md`, Stage 3 sections, for input requirements and validation limits.

The builder validates the exact saved Stage 2 predecessor and underlying Stage 1
chain, reads preserved source records, workbook cells and checked brief/interview
lines, and creates evidence-linked constraints without retrieving or changing sources.
Keep `hard_constraints`, `preferences`, `assumptions`, `unknowns` and `conflicts`
distinct. Preserve observations and original values/units in `source_facts`; planned
allocations are not approval limits, and attendance forecasts are not guaranteed
check-ins. The current assumption collection is empty; do not invent defaults.

When generation is authorized and its output is absent, run from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from pathlib import Path
from event_coordination.stages.constraints import write_snapshot

path, digest = write_snapshot(Path.cwd())
print(path)
print(digest)
PY
```

The output is `deliverables/snapshots/03-constraint-model.json`. The writer validates
before and after exclusive creation and refuses overwrites. To review an existing
snapshot, use this read-only command instead:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import json
from pathlib import Path
from event_coordination.validation import validate_snapshot

root = Path.cwd()
path = root / "deliverables/snapshots/03-constraint-model.json"
validate_snapshot(json.loads(path.read_bytes()), root)
print("Stage 3 schema, evidence, dependencies, and lineage checks passed")
PY
```

Stage 3 retains the run ID and references Stage 2's exact snapshot ID/path and
SHA-256. New semantic IDs link to consumed Stage 2 evidence IDs, original locators,
hashes and checked source values. Dependencies must resolve without cycles; timing
prerequisites and five pending approval gates remain explicit. Quote conditions
apply only when proposed; no vendor selection or granted approval is inferred.

The current `partial` status retains 73 unknowns and 6 conflicts, represented by 79
unresolved records. All Stage 2 issues are carried forward. Hash integrity and a
schema-valid requirement do not establish remote verification, fulfillment or
authorization. Preserve manual-copy provenance, incomplete exports, unknown original
retrieval times, privacy limits and operational conditions. Keep this internal model
out of general communications and preserve all Entire checkpoint history.

## Run Stage 4 planning baseline

Use `event_coordination.stages.baseline`, not a `stage4` CLI subcommand. Read the
root `IMPLEMENTATION.md`, Stage 4 sections, for generation inputs and validation
limits. The builder verifies the exact Stage 3 predecessor and recursively checks
the earlier chain and original evidence. It performs no source retrieval.

Preserve the four required arrays:

- `headcount_basis`: 180 registered + 30 required onsite + 35 forecast walk-ins
  reconcile to the declared 245-person planning quantity. Keep forecasts uncertain,
  confidence qualitative and overlapping needs nonadditive. Neither demo slots nor
  the 80% check-in target change the capacity basis.
- `schedule_dependencies`: retain all eight calendar records, source priorities,
  date alternatives, Asia/Taipei offsets, access windows and prerequisites. Keep
  Operations' `2026-09-04T17:00:00+08:00` deadline distinct from the business clock.
  Twelve ten-minute demos plus twelve three-minute changeovers total 156 minutes;
  this does not finalize the run of show. Preserve venue confirmation before the
  walkthrough and date/bundle-specific readiness before opening. Do not invent
  vendor durations or extra mandatory buffers.
- `budget_baseline`: keep the TWD 520,000 ceiling, TWD 510,000 allocations, category
  approval limits and zero recorded commitments distinct. TWD 10,000 is unallocated;
  contingency is already included. Uncommitted amounts do not authorize spending.
  Category-owner authorization remains pending and reallocation policy unresolved.
- `accessibility_baseline`: retain mandatory access, dietary and safety responses,
  overlapping signals, separate space limits and conditional service prerequisites.
  `fulfillment: not-evaluated` establishes neither provision nor absence of services.
  Public floor-plan/index observations and fictional exercise confirmations do not
  certify current operational accessibility.

When generation is authorized and the output is absent, run from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from pathlib import Path
from event_coordination.stages.baseline import write_snapshot

path, digest = write_snapshot(Path.cwd())
print(path)
print(digest)
PY
```

The output is `deliverables/snapshots/04-planning-baseline.json`. The writer uses
exclusive creation and validates before and after writing. For an existing snapshot,
run this read-only command instead:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import json
from pathlib import Path
from event_coordination.validation import validate_snapshot

root = Path.cwd()
path = root / "deliverables/snapshots/04-planning-baseline.json"
validate_snapshot(json.loads(path.read_bytes()), root)
print("Stage 4 schema, arithmetic, evidence, dependencies, and lineage checks passed")
PY
```

New semantic IDs cite Stage 3 produced IDs and embed supporting `source_records`
with original values, units, locators, hashes and verification limitations. Keep
source statements, stakeholder rules and derived formulas distinct. Current
assumptions and planning choices are empty. Preserve all 79 unresolved records and
five pending gates with their original IDs and historical evidence links; the
baseline remains `partial`. Local hash/schema validation does not establish remote
verification, requirement fulfillment or approval.

Stage 4 retains the run ID and chains to Stage 3 ID
`c8b2438d-157e-4a55-9065-ae4b32156c2c`, SHA-256
`0b346b83d170f871b4ad22d13c951baabb9a437ecd1beaf3c9e75bee14f3ea37`.
Actual execution time stays separate from the fixed business clock. Keep the baseline
internal, omit individual medical/contact details from general artifacts, and do not
select vendors, finalize a date or authorize spending. Verify generation in a
temporary input copy when the real output exists; preserve Entire checkpoint history.

## Run Stage 5 option generation

Use the Python API `event_coordination.stages.options`; no `stage5` CLI subcommand
exists. Read root `IMPLEMENTATION.md`, Stage 5 sections, for exact input-copy and
reproduction instructions. Preserve the required `options` and `rejected_early`
arrays and the supporting quote evidence, ancestor references and comparison basis.

The two October 17 proposals share Q-001/Q-005/Q-006/Q-009/Q-010 and differ between
Green Table Q-003 and City Pantry Q-004. Quoted subtotals are TWD 429,000 and 447,000.
The explicit allowance policy retains communications 25,000 and contingency 40,000,
giving planning totals 494,000 and 512,000. Do not add baseline allocations again.
Catering capacities 260/300 give nominal margins 15/55 over the uncertain 245-person
planning basis. Preserve category variances and separate approval limits. These
are proposals, not selected vendors, final feasibility results or authorized spend.

Keep all four screening records: the incomplete October 24 package/keynote conflict,
Q-007's unsupported hearing-loop coverage, and both conditional Q-008 livestream
additions. Livestream totals are 549,000/567,000 under this allowance policy, and
network test/venue confirmation remain open. Keep reasons and reconsideration needs;
do not invent replacement offers or treat early screening as full feasibility testing.

When authorized and the output is absent, run from the project root:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from pathlib import Path
from event_coordination.stages.options import write_snapshot

path, digest = write_snapshot(Path.cwd())
print(path)
print(digest)
PY
```

The real `deliverables/snapshots/05-option-generation.json` already exists. Verify
reproduction in a temporary input copy using the operator documentation; do not
regenerate the real output. The writer exclusively creates files and refuses
overwrites. For the saved snapshot, run this read-only command instead:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import json
from pathlib import Path
from event_coordination.validation import validate_snapshot

root = Path.cwd()
path = root / "deliverables/snapshots/05-option-generation.json"
validate_snapshot(json.loads(path.read_bytes()), root)
print("Stage 5 schema, arithmetic, ancestor evidence, and lineage checks passed")
PY
```

Stage 5 verifies the exact Stage 4 predecessor and recursively checks earlier
snapshots/evidence. Its 32 ancestor references identify Stage 3 quote facts/rules,
Stage 2 observations/capture and the alternatives rule by owning snapshot, hash and
record ID. Never attribute those ancestor IDs to Stage 4. All ten quotes retain
original cells, locators, hashes, service-specific capacities, dates and exclusions.
Local integrity does not establish live-source verification or real supplier offers.

Preserve the run ID and Stage 4 predecessor ID/hash, all 79 unresolved records and
five pending approval gates. Keep status `partial`, decisions empty and options
unselected, not yet tested and unapproved. Keep actual execution timestamps separate
from the business clock, retain privacy limitations and preserve Entire checkpoints.
Stage 6 must test scope/capacity, accessibility/dietary/safety, date/quote validity,
category/total costs, programme/windows and applicable operational conditions before
classifying feasibility. Stage 7 records recommendations and genuine decisions or
approvals; neither approval nor fulfilled conditions may be inferred from arithmetic.

## Run Stage 6 feasibility testing and prepare the handoff

Use `event_coordination.stages.feasibility`; no `stage6` CLI subcommand exists.
Read root `IMPLEMENTATION.md`, Stage 6 sections, for prerequisites, reproduction,
checks and the proposed witness. Stage 6 requires the exact saved Stage 5 predecessor
ID `78805525-4ec3-44dd-b837-7fdb6a3347b4`, path
`deliverables/snapshots/05-option-generation.json`, SHA-256
`e0454834f384615926edbf2cc8130ea4c0f0a3ae1e8c942a8010f9fad92dc65d`.
It recursively validates earlier snapshots/evidence and retains the existing run ID.

When generation is authorized and the output is absent, run from the project root:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from pathlib import Path
from event_coordination.stages.feasibility import write_snapshot

path, digest = write_snapshot(Path.cwd())
print(path)
print(digest)
PY
```

The real output already exists. Verify reproduction only in a temporary input copy
as described in `IMPLEMENTATION.md`; the writer exclusively creates files and
refuses overwrites. Use this command from the real root for read-only validation:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import json
from pathlib import Path
from event_coordination.validation import validate_snapshot

root = Path.cwd()
path = root / "deliverables/snapshots/06-feasibility-testing.json"
validate_snapshot(json.loads(path.read_bytes()), root)
print("Stage 6 schema, types, evidence, checks, schedules, and lineage validation passed")
PY
```

Preserve `option_results` and `unresolved_conditions`, 109 candidate checks, two
witnesses, four retained screening records with separate audits, and five pending
gates. Independently reconstruct costs with Decimal from quote facts: quoted
429,000/447,000 plus retained allowances give planning totals 494,000/512,000 TWD.
Do not double-count allocations. Evaluate availability, scope/exclusions and
operational readiness separately; source integrity is not live verification.

Applicable technical hard outcomes aggregate `fail > unknown > conditional > pass`
into `infeasible`, `unverified`, `conditional` or `feasible`. Keep preferences,
ordinary authorization and out-of-scope live verification separate. Both current
results are conditional because venue confirmation before the walkthrough remains
open; neither is selected or approved. Do not generalize that result to revised inputs.

Witnesses preserve 09:30 opening, 10:00–11:00 keynote, twelve ten-minute demos and
twelve three-minute changeovers, and the source setup/teardown envelopes. Demo
order, breaks, lunch and flexible allowance are proposed choices. Validate full
Asia/Taipei timestamps, connected opening/readiness boundaries, durations, resource
lanes and half-open intervals. Never infer individual vendor durations or an
approved run of show. Fictional case confirmations and floor-plan observations do
not prove current elevator/route operation, service provision or bookings.

Keep all 79 inherited issues and nine new conditions (88 total) traceable. Conditions
identify resolution evidence, related issues and only supported roles/deadlines.
Preserve the fallback conflict, Q-007 coverage gap and conditional livestream
alternatives; no replacement offer or successful test is invented.

For Stage 7, hand off check-level findings, blockers, costs, witnesses and evidence
limitations. A recommendation is separate from a learner decision and human
approval. Operations, spending, applicable Programme changes, venue confirmation
and external actions retain their distinct boundaries. Approvals stay pending
until genuine evidence covers the plan revision and scope.

Changed quotes, attendance, venue conditions or evidence require upstream
reevaluation and propagation to dependent results/drafts. Preserve historical
snapshots and Entire checkpoints; do not edit saved JSON or silently repin hashes.
The current implementation rejects changed pinned inputs and does not automatically
migrate revised runs. Run the focused Stage 6 tests documented in `IMPLEMENTATION.md`
when verifying assessment changes; preserve privacy in all general artifacts.

## Stage 7 provisional review model

Use `event_coordination.stages.decisions.build_snapshot(root)` to build only in
memory from the pinned Stage 6 predecessor. `validate_snapshot` checks Stage 7
schema, reconstructed recommendation policy, source integrity, strict types and lineage. See
`IMPLEMENTATION.md` for the executable inspection and focused-test commands;
there is no Stage 7 CLI subcommand. Input manifests pin evidence, captures,
interviews, schema, media copies and earlier snapshots through builder/validation
return. The writer requires no-follow canonical parents and supported Linux
`openat2` exclusive creation; directory swaps, collisions and unsupported kernels
stop generation. It reads back the original descriptor and rechecks inputs and
output identity. A failed write may leave an incomplete file: stop for review,
without deleting or overwriting it automatically. See `IMPLEMENTATION.md` for
platform and concurrency limits. The exclusive writer remains reserved for a
separately authorized generation step; the real Snapshot 07 has not been generated.

Use the versioned planner policy `adequacy-then-headroom/1`; it is a planning
choice, not a stakeholder ranking rule. Require adequate catering capacity, costs
within the ceiling, feasible/conditional hard-check outcomes, comparable demand and
hard dependencies, and no additional unresolved requirement types before using
lower total and greater headroom to recommend a candidate. Otherwise retain null
with the policy's evidence-linked deferral rationale. Do not invent capacity buffers
or treat lowest price alone as sufficient. Current evidence provisionally prefers
Green Table, with 15 catering places of margin and TWD 26,000 headroom; City Pantry
retains 55 places and TWD 8,000 headroom. Preserve that trade-off for human review.
See `IMPLEMENTATION.md` for the criteria, caveats and executable inspection command.

Keep learner decisions empty, both candidates conditional and unselected, all 88
unresolved records, five pending gates and four early screenings. A provisional
recommendation is not selection, approval, booking or spending authority. Preserve
historical IDs and explicit ancestor ownership; source-copy/exercise limitations
remain unchanged. Reevaluate upstream for changed demand, quotes or conditions.
Stop for review before snapshot generation, selection, genuine approval ingestion,
policy changes or business action. A deferral does not establish final assignment
completion.

Ordinary temporary-fixture development tests suffice; do not enable the isolated
runner or treat a batch configuration as human authority. Stage 8 includes the in-memory foundation and separately authorized controlled writer below; Stage 9 technical validation is available through the coordinator below. Do not claim unexecuted commands or tests passed, or replace missing
implementation with fabricated planning artifacts.

## Stage 8 Part 1 — in-memory draft propagation

Use `event_coordination.stages.drafts.build_bundle(root)` to construct a proposed
Stage 8 snapshot and four byte payloads only in memory; `validate_bundle` validates
both. See `IMPLEMENTATION.md` for executable inspection/test commands and exact
predecessor identity. There is no Stage 8 CLI. In-memory inspection does not authorize
saving the returned objects; use the controlled writer only after generation approval.

Carry the provisional Green Table basis and City Pantry alternative into CSV,
event plan, tentative ICS and unsent audience-role communications. Retain both
conditional classifications, all 88 unresolved records, five pending gates and
four screenings. Programme approval applies only to roster/duration changes.
Reuse Stage 6's schedule witness; do not relabel it as a Stage 7 output or invent
vendor setup durations. Quote rows and package totals remain separate; allocations
are not extra costs or spending authority. Keep forecast uncertainty and needs
overlap explicit. Restrict public drafts to business fields and generic coordination
responses; do not copy raw private attendee needs/contact data into them.

Artifact hashes cover actual rendered UTF-8 bytes embedded in `rendered_text`.
They are planned in-memory hashes: `saved_file_verified=false` and
`validation_status=not-produced`, regardless of successful in-memory validation.
Never describe them as verified saved artifacts. All real output paths must be
absent for in-memory generation; collisions or changed protected inputs stop the
foundation. The controlled writer performs saved-file verification as described below.

Preserve real ancestor IDs, source locators/hashes and artifact section/row/calendar
UID dependencies. `affected_targets` reports transitive impacts without editing
history; unknown scope stops. Changed evidence requires upstream reevaluation and
human review. Business evaluation uses the fixed Taipei clock; actual UTC execution
time supplies DTSTAMP. ICS remains tentative/transparent, without invitations,
organizer/attendee addresses, fabricated deadline durations or confirmed fallback.
Review privacy, cross-artifact consistency and all unresolved conditions before
any authorized generation or Git milestone. Keep operational automation disabled.


## Stage 8 controlled writing and recovery

New in-memory rendering/builds and separately authorized writing use
`draft_contract_version: assignment-drafts/1`. Apply the published draft contract
from starter README `c724104`, lines 104–110, before accepting generated bytes:

- CSV includes `option_id`, `quote_ids`, `planning_people`, `cost_twd`, `currency`,
  `feasibility`, `availability_status`, `evidence_ids`, `tradeoffs`, `unresolved`,
  `approval_status`. Costs are whole-number TWD. Candidate cost includes retained
  allowances; individual quote cost is only that service. Blank unknown package
  costs require reasons. Tradeoffs/unresolved use JSON arrays; quote IDs use `;`.
  Keep captured notes unchanged, fictional availability separate from unverified
  real-world availability, candidates conditional and all approvals pending.
- Calendar `METHOD:PUBLISH` is required draft metadata. It sends nothing. Keep
  tentative events, source-supported timing, and no attendees or organizer.
- Each communication has an `UNSENT DRAFT` heading, audience, purpose, conditions
  and approval owner. Use supported gate roles; explicitly mark the unknown
  external-release owner unresolved rather than assigning one. No recipients or
  release authority are invented.

The exact saved historical Snapshot 08 and artifact bytes retain their old format
for integrity validation only. This is not assignment acceptance. New builds must
use the current contract; an absent version, a copied run ID or a legacy flag
cannot exempt new snapshots. Never edit audited outputs to update their format.
Use `tests/test_draft_contract.py` with `tests/test_stage8.py` in temporary copies
for published-field assertions and historical compatibility. Root
`IMPLEMENTATION.md` documents the exact test commands and exception pins.
Fresh runs require the separate-workspace coordinator below. Managed recovery uses `execute` below; Stage 9 validates saved drafts locally; never replace the audited artifacts to demonstrate the new format.

Use `event_coordination.stages.drafts.write_snapshot(root)` only for a separately
authorized generation scope. See `IMPLEMENTATION.md` for the exact executable
Python commands and temporary-copy prerequisites. Keep all five destinations
absent and their parents canonical. The writer creates the four drafts exclusively,
reopens and hashes them, then writes Snapshot 08 last and validates its saved bytes.
Linux x86_64 `openat2` confinement is mandatory; unsupported isolation fails without
an unsafe fallback. Input/parent/output identities are rechecked throughout.

The saved model uses `generation_mode=saved-files-verified` and marks local artifact
hashes verified only after reopening actual bytes. Shared `validate_snapshot`
validates either the in-memory proposal (outputs absent) or saved mode (artifacts
present and exact). Valid saved bytes confer no booking, spending, invitation or
publishing authority. Keep the provisional recommendation, all pending gates and
unresolved conditions, and fictional-versus-live source limitations intact.

On any write, readback, integrity or validation failure, stop. Leave partial files
untouched and report paths, error and available hashes. Never automatically delete,
replace, retry, or describe an existing snapshot as a completed batch. Human review
must authorize recovery; use a fresh temporary copy for tests/reproduction.
This is not a transactional multi-file operation or protection against arbitrary
concurrent host changes after observation. Do not enable the supervised runner,
perform external actions or generate real outputs under implementation-only approval.

## Maintain the planning boundary

Keep facts, calculations, assumptions, unresolved conditions, recommendations,
learner decisions, and approvals distinct. Evidence must support business claims
and approvals; passing schema validation is never evidence of authorization.
Preserve missing approvals as pending. All generated outputs remain drafts.
Humans authorize booking, spending, invitations, and publishing and finalize
bookings and commitments.

At handoff, report the run or reviewed scope, affected artifacts, validation
results, unresolved conditions, required reviewers, and decisions still needed.
Never describe a conditional plan as fully feasible or a local validated artifact
as published.

## Execute a separately authorized local Stage 01–09 run

Use the installed environment and exact `run-stages` command in the root
`IMPLEMENTATION.md`. For example, from the repository:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m event_coordination.cli run-stages --source-root /home/maxg/event-coordination --workspace /tmp/project-c-new-run
```

Require an absent destination outside the repository, safe canonical parents,
unchanged schema and all registered captures, evidence and interviews. This
replays registered local sources, not remote retrieval. It executes the real
nine writers, verifies saved predecessor bytes, and creates new run/snapshot
IDs and `assignment-drafts/1` outputs. Review the returned JSON hashes and paths.
Historical snapshots, artifacts and source evidence stay unchanged.

Preserve all 88 unresolved records, five pending gates, four screening records,
and fictional/local-copy provenance. The recommendation is a draft, not a human
decision. Never send or publish the generated files automatically. The workspace
contains source evidence and must stay restricted. Filesystem separation is not
an OS sandbox; operational supervised execution stays disabled.

If any stage fails, stop and retain partial outputs for review. Do not retry into
the same workspace, overwrite artifacts, silently change evidence pins, or claim external publication is authorized. Use managed `execute --recover` for reviewed recovery. Material source changes require further reviewed
implementation rather than bypassing existing evidence-bound checks.

## Stage 09 local publication validation

`run-stages` defaults to Stages 01–09; `--through-stage 8` preserves the shorter
review checkpoint. Stage 09 verifies actual saved artifact bytes, assignment
content, source lineage and Stage 08 predecessor hashes before exclusively writing
`09-publication-validation.json`. See root `IMPLEMENTATION.md` for the command.

Treat passed validation checks as technical checks on drafts only. Publication
remains blocked, external publication is not performed and the run remains
partial while approvals and evidence are unresolved. Retain every pending gate,
unresolved record and screened alternative. Never turn `METHOD:PUBLISH` calendar
metadata or a technical pass into permission to send, book, spend or publish.
Missing/tampered files stop the command; preserve partial work for review. Managed `execute` adds bounded recovery and material-change archiving below.

## Managed end-to-end execution and source changes

Use `scripts/run.py` with the installed project environment for a dedicated
external workspace. It invokes `execute` for Stages 01–09, semantic input
comparison, immutable history and failure receipts. Exact command, prerequisites,
input registration rules and recovery limitations are in the root
`IMPLEMENTATION.md`, “Managed execution, semantic changes and bounded recovery”.

Compare spreadsheet records by source identity, headers and stable primary keys;
never infer identity from row order. Keep original bytes and actual locators.
Equivalent layout changes preserve the existing validated run. Meaningful changes
require new IDs and Stage 01 supersession metadata, a complete candidate rerun and
a verified archive at `deliverables/history/RUN_ID/` before active replacement.

Treat `evidence/decision-requests.json` as advisory input only. No configuration,
request, technical validation or recovery operation grants business authority.
Preserve pending gates and honest retrieval states; do not create missing offers
or modify the protected repository run to demonstrate a source revision.

On failure inspect `deliverables/failure.json`, the attempt journal and preserved
files. After review use the same command with `--recover` for missing/corrupt or
interrupted managed outputs. Do not overwrite partial/conflicting history; its
repair requires human review. A deferred recommendation or unsupported event-scope
change may stop planning and require an explicit learner decision. No sending,
publication, bookings, payments, Git mutation or Entire configuration change is
part of this script.

For the current eight-source catalog, include the official Plenary Hall webpage
as a distinct source. Its exact URL is evidenced by the preserved published
assignment, not an invented interview line. Preserve both failed and successful
retrieval attempts. Treat public full-hall capacity/tariffs separately from the
fictional allocation/package, and retain supplier-permission and technical/safety
briefing conditions before real use. See the operator section “Official Plenary
Hall source addition”. Earlier seven-source runs remain immutable history.
