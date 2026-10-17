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

Stages 1–6 are implemented. Inspect `event-coordination stage1 --help` before
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

The CLI exposes only `stage1`; its description has not yet been updated for the
Stage 2 Python API. Do not invent an `event-coordination stage2` command. Read the
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
`stage3` subcommand. The CLI still exposes only `stage1`. Read the root
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

Stages 7–9 remain unimplemented. Do not claim unexecuted commands or tests passed,
or replace missing implementation with fabricated planning artifacts.

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
