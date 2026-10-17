# Project C implementation

## Install

Use Python 3.12 or newer. From the repository root, create an isolated environment
and install the package:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

For automated tests, install the optional development dependencies:

```bash
.venv/bin/python -m pip install -e '.[dev]'
```

Stages 1–6 use jsonschema with date-time format checking, plus standard-library
JSON, SHA-256 hashing, UUIDs, and timezone-aware timestamps. Stage 1 has an argparse
CLI. Stage 2 exposes Python functions, including HTTPX capture utilities; Jinja2,
icalendar, and tzdata support the planned later workflow. Final event artifact
generation is not implemented. Stage 3 uses read-only ZIP/XML extraction of XLSX
cells and preserved text lines; it does not recalculate formulas or require an
additional spreadsheet dependency.

## Display CLI help

```bash
.venv/bin/event-coordination --help
```

Running `event-coordination` without arguments also displays help. Use
`event-coordination stage1 --help` for Stage 1 options.
The CLI currently exposes only `stage1`; its help description still says only
Stage 1 is implemented. Stage 2 is available through the Python commands below,
not an `event-coordination stage2` subcommand.
Stage 3 likewise uses a Python API, not a `stage3` CLI subcommand.
Stage 4 uses a Python API, not a `stage4` CLI subcommand.
Stage 5 also uses a Python API, not a `stage5` CLI subcommand.
Stage 6 uses a Python API, not a `stage6` CLI subcommand.

To display help from the source tree using the installed dependencies:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m event_coordination.cli --help
```

## Generate Stage 1

Run only when a new Stage 1 snapshot is authorized and its output path is absent:

```bash
.venv/bin/event-coordination stage1 --project-root /path/to/event-coordination
```

`--project-root` defaults to the current directory. The command reads the root
`snapshot.schema.json` and selected lines from these preserved local inputs:

- `evidence/originals/event-brief-manually-completed.txt`
- `interviews/project-c-event-coordination-20261016-1954.md`
- `interviews/project-c-event-coordination-20261016-2056.md`

Evidence selections are reviewed Project C mappings in `stages/scope.py`, not a
general-purpose extraction system. Missing files or changed selected text cause
failure. Source bytes are hashed without modification. The manually completed
brief is explicitly distinguished from the separate incomplete PDF.

The command generates a UUID run ID unless `--run-id YOUR_RUN_ID` is supplied.
Retain that ID for future stages. It writes
`deliverables/snapshots/01-scope-and-approval-gates.json`, prints the output path
and SHA-256 hash, and refuses to overwrite an existing snapshot. A supplied run ID
does not bypass overwrite protection. Do not rerun generation to validate an
existing snapshot.

The snapshot captures the objective, role-based owners, approval gates, and the
stakeholder-confirmed Operations deadline `2026-09-04T17:00:00+08:00` (second
interview, line 790). It preserves source paths, hashes, line references, excerpts,
and provenance. Approvals remain pending and learner decisions remain empty.
Its `partial` status records unresolved individual category-owner identities.

Validation uses Draft 2020-12 with `FormatChecker` against the unchanged schema,
then checks source hashes/excerpts, evidence references, supported scope values,
pending approvals, and Stage 1 record lineage. It runs before writing and again
after reading the saved JSON. These checks establish structural and local evidence
consistency, not independent authentication of the manually completed source.

## Test and validate an existing snapshot

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
```

Tests generate snapshots only in temporary test directories. To validate the
existing project snapshot without regenerating or overwriting it, run from the
repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import json
from pathlib import Path
from event_coordination.validation import validate_snapshot

root = Path.cwd()
path = root / "deliverables/snapshots/01-scope-and-approval-gates.json"
validate_snapshot(json.loads(path.read_bytes()), root)
print("Stage 1 schema and provenance checks passed")
PY
```

## Stage 2 source-capture workflow

Stage 2 assembles preserved evidence offline. Its inputs are the unchanged schema,
the saved Stage 1 snapshot, interview disclosure references, all JSON records under
`evidence/captures/`, and their referenced originals under `evidence/originals/`.
Keep the complete input package available to reproduce validation and integration
tests. The current inventory has seven source identities, nine capture attempts,
eight original files, and 55 observations. The two brief representations and failed
floor-plan attempt remain separate records, grouped under their source identities.

The capture foundation in `capture.py` provides explicit `retrieve_source()` and
`import_local()` functions. Retrieval requests only a catalog URL without supplied
authentication, follows no redirects, and records failures honestly. Local import
requires explicit method, content type, and publication classification; it does
not claim online equivalence. Accepted new captures use hash-based exclusive byte
storage. These functions return metadata; they do not automatically save a capture
JSON record or perform the reviewed document observations. The current registrations
preserve user-supplied browser/provider exports with separately saved metadata.

Source retrieval states are:

- `retrieved`: a successful remote capture of accepted bytes, not proof of document
  identity, completeness, operational conditions, or historical applicability.
- `unavailable`: an unsuccessful access attempt; no successful retrieval is inferred.
- `invalid`: unexpected or rejected content.
- `unverified`: provenance or online equivalence remains unverified, including local
  copies; can also represent a redirect requiring review.
- `stale`: an evidenced freshness limitation. The assembler preserves this status;
  it does not invent an age threshold or automatically assign it.

The present package has eight `unverified` local registrations and one `unavailable`
automated attempt. Hash verification confirms byte integrity, not remote retrieval.
Manual text, browser-produced PDF/HTML, official publications, and fictional exercise
records retain their different provenance. Actual registration/attempt times remain
separate from unknown original download times and the simulated business clock.

`source_inventory.load_inventory()` checks capture schemas, catalog identities,
disclosure references, duplicate IDs, paths, sizes, and original-file hashes. It
also hashes capture JSON bytes into the snapshot's manifest. Editing even the
whitespace of a capture JSON changes that manifest hash. Original observation IDs
are preserved in the produced-record lineage. Scope and unresolved owner questions
are consumed from Stage 1; conditions and limitations remain explicit unresolved
records rather than approvals or resolutions.

The assembler is pinned to the approved Stage 1 SHA-256:
`6579a81d06ac405d3e612dbe7ad4d354b9373ff5840168af0981d961186fde7d`.
It retains run ID `988f5ccf-4aeb-44d7-984d-777b1a2412e1` from that predecessor and
records its snapshot ID, path, and exact byte hash. A changed predecessor is rejected.

The required spatial evidence copy is
`deliverables/snapshots/evidence/f1710485827023.pdf`, identical to its preserved
original. Existing capture references still point to `evidence/originals/`; the
assembler does not create or separately validate the submission copy. Keep both
copies unchanged and verify their hashes when packaging.

## Generate Stage 2

From the repository root, use this only for an authorized run where
`deliverables/snapshots/02-source-capture.json` does not already exist:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from pathlib import Path
from event_coordination.stages.capture import write_snapshot

path, digest = write_snapshot(Path.cwd())
print(path)
print(digest)
PY
```

This runs the actual Python API, verifies the input evidence and predecessor,
validates before writing, creates the snapshot exclusively, then rereads and
validates the saved bytes. It refuses an existing snapshot. It does not retrieve
sources, select vendors, or generate general planning artifacts. The existing real
Stage 2 snapshot must be validated rather than regenerated.

## Validate saved Stage 2 without rewriting it

Run from the repository root:

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

Validation uses the unchanged schema with date-time checking, rechecks Stage 1 and
capture inputs, and compares the saved Stage 2 state, manifest, grouping, lineage,
and unresolved records with those inputs. It performs no network requests and no
writes. Changed/missing inputs cause failure rather than silent source substitution.

Stage 2 legitimately remains `partial` when evidence is available but verification,
completeness, conditions, or inherited questions remain unresolved. The current
snapshot contains 73 unresolved records; these include per-capture limitations and
historical failures, not 73 independent planning blockers. Schema validity does not
turn local imports into verified remote evidence. Future stages must retain the
unresolved conditions relevant to their decisions.

The complete test command above covers Stages 1–3. Capture tests use synthetic
fixtures/mocked responses, and Stage 2 integration tests copy preserved project
inputs into temporary directories. They prohibit live network access. Generation
and validation commands can be verified in a temporary input copy without replacing
the real snapshots; test success alone does not establish live-source authenticity.

## Stage 3 constraint-model workflow

Stage 3 reads `deliverables/snapshots/02-source-capture.json`, validates its saved
hash and Stage 2 semantics (including the Stage 1 chain), and uses its capture
records and original observation IDs as upstream evidence. It reads preserved
workbook cells and checked brief/interview lines without changing sources or
retrieving anything online. The workbook reader preserves original cell values,
units and date serials alongside interpreted fields; unsupported formulas or
formats fail rather than being recalculated or guessed.

The model separates:

| Collection | Meaning |
|---|---|
| `hard_constraints` | Requirements that an applicable proposal must satisfy; conditional quote requirements apply only when that quote is proposed. |
| `preferences` | Source-supported flexible choices, including fallback/rehearsal preferences and familiar suppliers. |
| `assumptions` | Explicit planning assumptions. Currently empty; missing facts are not converted into assumptions. |
| `unknowns` | Unverified provenance, missing policies/identities/approvals, incomplete sources, and other unresolved evidence. |
| `conflicts` | Unresolved tensions and potential conditional conflicts. An allocation variance alone is not an approval-limit breach or vendor rejection. |
| `source_facts` | Preserved observations and structured source values, separate from enforceable rules. Includes overlapping representations, not independent additional sources. |

Stable semantic record IDs link rules to Stage 2 evidence IDs, source locators,
hashes and original values. Supplementary checked interview/brief lines retain
their path, hash and excerpt without modifying Stage 2 observations. Budget ceiling,
planned allocations, approval limits and committed amounts remain distinct.
Attendee signals retain their source types, units and qualitative confidence;
overlapping needs add no people and forecasts are not guaranteed attendance.

`depends_on_record_ids` represents dependencies among Stage 3 records. Missing
references and cycles are rejected. For example, the walkthrough requires venue
confirmation first. Five separate approval-gate records remain `pending`; a
conditional Programme or quote requirement does not establish that a change or
vendor was selected. No actual approval or final feasibility decision is generated.

The predecessor is Stage 2 snapshot ID `7e223901-57c7-4a24-8ba8-597241feb2ec`,
with SHA-256
`abe8ff40d45da1e8ba8c45f35b715db99b17bd40fe66d5e5adc331334d00fe70`.
Stage 3 retains run ID `988f5ccf-4aeb-44d7-984d-777b1a2412e1`. Consumed IDs must
resolve to Stage 2 produced records. Stage 3 produces distinct IDs; its top-level
`unresolved` repeats the unknown/conflict collections as identical views of the same
logical records, not new produced IDs. Actual execution time is separate from the
unchanged business clock.

## Generate Stage 3

Run from the repository root only when generation is authorized and
`deliverables/snapshots/03-constraint-model.json` is absent:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from pathlib import Path
from event_coordination.stages.constraints import write_snapshot

path, digest = write_snapshot(Path.cwd())
print(path)
print(digest)
PY
```

This invokes the implemented writer, which builds and validates the model in
memory, exclusively creates the output, verifies saved bytes, and validates again.
It refuses to overwrite an existing snapshot. `build_snapshot(root)` is the
read-only in-memory API; it validates but does not write. The existing real Stage 3
snapshot must be validated rather than regenerated.

## Validate saved Stage 3 without rewriting it

Run from the repository root:

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

Validation uses the unchanged schema with date-time checking and reconstructs the
expected model from preserved inputs. It checks the exact predecessor, shared run
ID, supported source values, evidence references, dependency graph, pending gates,
lineage, and retained uncertainty. A changed source or unsupported model edit fails
validation; passing checks does not independently authenticate a remote source.

The current snapshot is `partial`: it has 56 hard constraints, 3 preferences,
0 assumptions, 73 unknowns, 6 conflicts, 105 source-fact records and 5 pending gates.
Its 79 unresolved records preserve every Stage 2 issue plus additional model gaps
and conditional conflicts. They include incomplete exports, unknown original
retrieval times, unverified online equivalence, allocation-policy ambiguity and
operational prerequisites. Requirements being explicit is not proof they are
fulfilled. Do not promote these items to verified facts, approvals, selected vendors
or a finalized attendance/schedule basis.

The test command above includes Stage 3 correctness, provenance, source-value/unit
preservation, dependency/cycle checks, conditional applicability, uncertainty,
tamper rejection and overwrite refusal. Integration tests copy inputs into temporary
project roots and block live network access. Verify generation in a temporary input
copy when the real output already exists. Keep the model internal; it contains
aggregate attendee-needs evidence and must not be copied wholesale into general
communications.

## Stage 4 planning baseline

Stage 4 uses `event_coordination.stages.baseline`; there is no `stage4` CLI
subcommand. It reads the saved Stage 3 snapshot and recursively validates the
Stage 1–3 chain and preserved evidence hashes before building a baseline. It does
not retrieve sources. The current output contains 54 stable semantic records:

| Required array | Records | Meaning |
| --- | ---: | --- |
| `headcount_basis` | 7 | Registered people, required onsite personnel, forecast, reconciled planning demand, overlap and success-target rules. |
| `schedule_dependencies` | 14 | All eight calendar records, access windows, approval deadline, scoped readiness, programme authority, roster and duration calculations. |
| `budget_baseline` | 13 | Ceiling, seven category records, allocation/commitment totals, differences from the ceiling and spending authorization requirements. |
| `accessibility_baseline` | 20 | Mandatory access requirements, eight overlapping needs signals, separate space limits, verification limits, safety, privacy and conditional service prerequisites. |

Each new record cites actual Stage 3 produced IDs in `evidence_ids` and preserves
supporting records, original values, units, locators, hashes and verification limits
in `source_records`. `basis` separates source statements, stakeholder rules and
derived calculations. Derivations retain their inputs and operations. The current
`assumptions` and `planning_choices` arrays are empty; neither vendor selection nor
a final event date is established.

Attendance reconciles 180 registered people (148 fellows + 32 partners), 30 required
onsite personnel (18 staff + 12 speakers), and 35 forecast walk-ins to the declared
245-person working planning demand. Forecast confidence remains qualitative, and
245 is not confirmed attendance or a finalized quantity for every service. Mobility,
captioning, quiet-space, dietary and allergy signals overlap the existing population;
they add no people. Demo slots add no people either. The 80% registered check-in
success target is not a capacity discount.

The budget keeps the TWD 520,000 ceiling separate from TWD 510,000 planned
allocations, category approval limits, and TWD 0 recorded commitments. The TWD
10,000 unallocated difference is derived; TWD 40,000 contingency is already within
the allocations. Ceiling less commitments is TWD 520,000, not permission to spend.
Category limits remain separate thresholds, and reallocation policy is unresolved.
All spending authority remains pending, including explicit owner authorization for
exceptions; no category exception can override the overall ceiling.

All calendar values retain their priorities and UTC+08:00 offsets, with
`Asia/Taipei` named explicitly. The preferred 17 October and fallback 24 October
remain alternatives; the fallback/keynote conflict is unresolved. Operations'
approval deadline is `2026-09-04T17:00:00+08:00`, supported by the second interview,
line 790. Venue confirmation precedes the walkthrough; specified base-bundle
readiness precedes opening on 17 October. Setup is 07:30–09:30 and teardown is
17:00–18:30. Missing individual vendor durations and extra mandatory buffers stay
unknown. Twelve demos each require ten presentation minutes plus a separate
three-minute changeover: 120 + 36 = 156 minutes. This is an allowance, not a finalized
run of show; keynote and other calendar requirements remain separate.

Step-free programme/restroom access, wheelchair seating, live captions and a staffed
quiet room remain mandatory but `fulfillment` is `not-evaluated`. Dietary and safety
responses remain required. Exercise venue confirmations are not current operational
certification; registered public floor-plan/index observations do not prove routes
are unobstructed or services are available. Conditional service requirements remain
conditional and do not select vendors. Keep individual medical/contact details out
of general artifacts; this baseline is for internal evidence review.

The predecessor is Stage 3 ID `c8b2438d-157e-4a55-9065-ae4b32156c2c`, SHA-256
`0b346b83d170f871b4ad22d13c951baabb9a437ecd1beaf3c9e75bee14f3ea37`.
Stage 4 retains run ID `988f5ccf-4aeb-44d7-984d-777b1a2412e1`.
Consumed IDs reference Stage 3 records. All 79 unresolved records and five pending
approval gates retain their identities and historical evidence links unchanged;
`inherited_record_ids` identifies these carried records. New dependency edges are
checked with the inherited Stage 3 graph for missing references and cycles.

The saved snapshot remains `partial`, with empty decisions: incomplete exports,
unverified online equivalence, unknown original retrieval times, operational
conditions, conflicts and genuine approvals remain unresolved. Validation cannot
upgrade these to verified facts or authorization. Actual UTC creation time remains
separate from the fixed business clock `2026-08-26T12:00:00+08:00`.

## Generate Stage 4

Run from the repository root only when generation is authorized and
`deliverables/snapshots/04-planning-baseline.json` is absent:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from pathlib import Path
from event_coordination.stages.baseline import write_snapshot

path, digest = write_snapshot(Path.cwd())
print(path)
print(digest)
PY
```

The writer builds and validates in memory, exclusively creates the output, checks
saved bytes, and validates the saved JSON again. It refuses overwrites.
`build_snapshot(root)` provides validated in-memory generation without writing.
The real Stage 4 snapshot already exists; validate it rather than regenerating it.
To verify generation, use a temporary project copy containing the unchanged schema,
Stage 1–3 snapshots, interviews, original evidence and capture records. Use the
installed project environment and leave the temporary Stage 4 output absent.

## Validate saved Stage 4 without rewriting it

Run from the repository root:

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

Validation applies the unchanged schema with date-time checking and reconstructs
the expected baseline from the exact predecessor and recursively verified inputs.
It rejects unsupported calculations, evidence references, dependencies, approvals,
selections, fulfillment claims or lost uncertainty. The full test command above
includes Stage 4 arithmetic, original-value/provenance preservation, all calendar
records, programme timing, conditional applicability, stable IDs, tamper rejection,
required arrays and overwrite refusal. Tests use temporary roots and block network
access. These checks establish local consistency, not independent remote authenticity.

## Stage 5 option generation

Stage 5 uses `event_coordination.stages.options`, not a `stage5` CLI subcommand.
It assembles proposed alternatives for later testing, without choosing a winner or
assigning final feasibility. Inputs are the unchanged schema, saved Stage 1–4 chain,
registered captures, preserved evidence and interviews. Assembly is offline and
recursively validates the earlier chain and evidence hashes.

The output is `deliverables/snapshots/05-option-generation.json`. Required arrays
`options` and `rejected_early` contain two candidate packages and four screening
records. Supporting arrays retain ten `quote_evidence` records, 32
`ancestor_references`, and three `comparison_basis` records. Every quote preserves
its source fields, original cell values, worksheet locator, dates, exclusions,
conditions, capture classification and hash. Date-only expiration cutoffs remain
unknown. Service capacities retain distinct interpretations; livestream capacity
is not physical seating and quiet-room capacity is not total event demand.

| Candidate ID | Proposed quotes | Quoted subtotal (TWD) | Planning total (TWD) |
| --- | --- | ---: | ---: |
| `option-oct17-green-table` | Q-001, Q-003, Q-005, Q-006, Q-009, Q-010 | 429,000 | 494,000 |
| `option-oct17-city-pantry` | Q-001, Q-004, Q-005, Q-006, Q-009, Q-010 | 447,000 | 512,000 |

Both propose 17 October 2026 in Asia/Taipei. `option-policy-retained-allowances`
explicitly records the planning choice to retain TWD 25,000 communications and
TWD 40,000 contingency allowances. Each total is its quoted subtotal plus those
allowances. They are not vendor offers, and the TWD 510,000 baseline allocation
total is not added again. Original amounts, calculated results and planning choices
remain distinct, with Decimal calculations and recorded formulas/inputs.

Catering capacities of 260 and 300 give nominal margins of 15 and 55 over the
245-person planning demand. That demand still includes uncertain forecast walk-ins;
overlapping needs and demo slots add no attendees. The TWD 18,000 price difference
buys a different recorded catering capacity, not permission to weaken dietary or
allergy coverage. Catering allocation differences are minus TWD 7,000 and plus
TWD 11,000; both candidates' security cost is TWD 3,000 above its planned allocation.
Category approval limits, recorded zero commitments and pending spending authority
remain separate. Arithmetic below the TWD 520,000 ceiling is not feasibility or
approval. Both records are `selected: false`, `assessment_status: not-yet-tested`,
and `authorization_status: pending`; no final feasibility field is assigned.

Early-screening records preserve considered alternatives, reasons and evidence
needed for reconsideration; they are not universal vendor rejections:

- `screen-oct24-incomplete-package`: Q-002 has a keynote conflict and no complete
  date-compatible service/programme/readiness basis. Its `missing_service_quotes`
  list describes absent October 24 coverage; those quotes do exist for October 17.
- `screen-oct17-q007-no-loop`: Q-007 alone excludes hearing-loop provision; no
  replacement service or price is invented.
- `screen-oct17-green-table-stream`: adding conditional Q-008 gives TWD 549,000
  under the retained-allowance policy, with network test and venue confirmation open.
- `screen-oct17-city-pantry-stream`: the same addition gives TWD 567,000, retaining
  both conditions. No reduced reserve, successful test or other remedy is assumed.

Stage 4 does not produce standalone quote-fact IDs. Each ancestor reference records
its actual owning snapshot's path, ID, SHA-256, run ID, stage and produced record ID.
The 32 references comprise ten Stage 3 quote facts, ten Stage 3 quote rules, ten
Stage 2 observations, the Stage 2 vendor capture and the Stage 3 alternatives rule.
The builder verifies ancestor hashes against the predecessor chain, shared run IDs,
record ownership, and quote observation/capture hashes and locators. Original-byte
integrity does not authenticate online origin: local copies remain unverified and
fictional exercise offers remain distinct from real venue publications.

Stage 5 retains run ID `988f5ccf-4aeb-44d7-984d-777b1a2412e1` and chains to Stage 4
ID `99fb512f-88e0-4bcd-ab2a-c42eed0b4671`, SHA-256
`321e45c0ce912ca95223f0ed72f627e19d539c40bf71c4f97a12bc691db25098`.
Consumed IDs cover actual Stage 4 and explicitly owned ancestor records; newly
produced records and inherited identities are enumerated separately from nested
source copies. All 79 unresolved records and five pending gates are preserved
unchanged. Status remains `partial`, decisions are empty, and actual UTC creation
time is separate from `2026-08-26T12:00:00+08:00`. Keep this evidence-rich snapshot
internal; do not copy individual medical/contact details into general artifacts.

## Reproduce Stage 5 without overwriting the saved snapshot

Run the following from a project root only when generation is authorized and
`deliverables/snapshots/05-option-generation.json` is absent. The real output already
exists: use a temporary copy for reproduction. Copy `snapshot.schema.json`,
`interviews/`, `evidence/originals/`, `evidence/captures/`, and snapshots 01–04 into
that temporary root. Use the installed project environment (or a `.venv` symlink
to it) there. Do not copy Snapshot 05 into the temporary root.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from pathlib import Path
from event_coordination.stages.options import write_snapshot

path, digest = write_snapshot(Path.cwd())
print(path)
print(digest)
PY
```

The existing exclusive writer validates before and after writing, verifies saved
bytes, and refuses an existing output. `build_snapshot(root)` builds and validates
in memory without writing. Reproduction creates a new snapshot UUID and execution
timestamp, so its file hash differs; stable records and calculations reproduce.
Never delete or replace the real snapshot to reproduce the procedure.

## Validate saved Stage 5 read-only

Run from the repository root:

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

Validation uses the unchanged schema with date-time checking and reconstructs the
expected candidate records, arithmetic, ancestor references and inherited issues
from verified inputs. Unsupported source edits, calculations, selections, approvals,
feasibility claims or lost conditions fail validation. The full automated test
command above includes Stage 5 and Stage 1–4 regressions; tests block network access
and use temporary project copies for generated outputs and overwrite checks.

## Stage 6 feasibility testing

Stage 6 uses the implemented Python API `event_coordination.stages.feasibility`;
there is no `stage6` CLI subcommand. It independently assesses both October 17
candidates within the fictional exercise scope. It does not retrieve sources,
recommend a winner, record a learner decision or authorize an external action.

Inputs are the unchanged schema, saved Stage 1–5 snapshots, registered captures,
preserved original evidence and interviews. The required immediate predecessor is
Stage 5 ID `78805525-4ec3-44dd-b837-7fdb6a3347b4`, path
`deliverables/snapshots/05-option-generation.json`, SHA-256
`e0454834f384615926edbf2cc8130ea4c0f0a3ae1e8c942a8010f9fad92dc65d`.
The builder checks those exact bytes, recursively validates the earlier chain and
source hashes, and retains run ID `988f5ccf-4aeb-44d7-984d-777b1a2412e1`.
Actual UTC execution time stays separate from the fixed business clock.

The required `option_results` and `unresolved_conditions` arrays are supported by
109 auditable candidate `checks`, two `schedule_witnesses`, an `assessment_policy`,
four `retained_early_screening` records, four separate `screening_checks` and five
pending `approval_requirements`. Stage 6 evidence IDs cite actual Stage 5 produced
records; nested baseline references retain their parent record and source identity.
Original source values, locators, hashes and verification limitations remain
traceable through the saved chain and Stage 5 ancestor references.

Each candidate has its own checks for costs, category limits/variances, attendance,
service-specific capacities, dates/expiry, service scope, programme/access windows,
accessibility, dietary/allergy responses, safety and operational prerequisites.
Quote amounts are reconstructed with Decimal from preserved source facts, not
accepted from Stage 5 calculated totals. Quoted subtotals are TWD 429,000 and
447,000; retained communications 25,000 plus contingency 40,000 give planning totals
494,000 and 512,000. Allocation variances, approval limits, zero recorded commitments
and pending authority remain distinct. The allocation-transfer policy is unresolved.

Checks use `pass`, `fail`, `conditional`, `unknown`, or `not-applicable`. Applicable
technical hard checks aggregate in this order:

| First applicable outcome present | Result |
| --- | --- |
| `fail` | `infeasible` |
| Otherwise `unknown` | `unverified` |
| Otherwise `conditional` | `conditional` |
| Otherwise all applicable hard checks pass | `feasible` |

Preferences, ordinary approval requirements and explicitly out-of-scope live
verification do not automatically decide technical feasibility. Record every blocker
and keep the assessment scope explicit. The saved results for both candidates are
`conditional` because venue confirmation before the accessibility walkthrough remains
an operational prerequisite. That is distinct from pending plan/spending approval.

Availability, scope coverage and operational readiness are separate checks. Scope
assessment evaluates source inclusions, explicit exclusions and evidenced
prerequisites, rather than treating an available quote as sufficient coverage.
Mandatory step-free access, wheelchair spaces, captions, hearing loop, quiet-room
availability/staffing, dietary and safety responses are assessed separately.
Exercise coordination/readiness confirmations support only their specified case
bundles. They are not live inspections, real supplier offers or bookings. The floor
plan does not establish current elevator operation, clear routes or service staffing.
Date-only quote expiry cutoffs remain unknown when their exact time matters.

### Proposed schedule witnesses

Both witnesses use full timestamps with UTC+08:00 and `Asia/Taipei`:

| Window | Witness element |
| --- | --- |
| 07:30–09:30 | Setup/readiness envelope |
| 09:30–10:00 | Proposed opening/orientation |
| 10:00–11:00 | Source keynote |
| 11:00–11:15 | Proposed break |
| 11:15–12:33 | DEMO-01–06, each ten minutes plus three-minute changeover |
| 12:33–13:33 | Proposed lunch |
| 13:33–14:51 | DEMO-07–12, each ten minutes plus three-minute changeover |
| 14:51–15:06 | Proposed second break |
| 15:06–17:00 | Flexible programme/closing allowance |
| 17:00–18:30 | Teardown/clearance envelope |

Ordering, break/lunch durations and flexible content are planning choices, not
source observations or an approved run of show. Setup/teardown are envelopes;
individual vendor durations and additional mandatory buffers are not invented.
Validation requires opening at the source 09:30 time and connects setup completion,
readiness, opening, keynote and programme/teardown boundaries. All twelve demos and
twelve separate changeovers are checked for duration and ordering, with half-open
intervals and distinct programme/access resource lanes. Adjacent intervals may meet
at the same timestamp without overlap.

### Uncertainty and Stage 7 handoff

The saved snapshot remains `partial` and `draft`, with empty decisions and neither
candidate selected. All 79 inherited unresolved records remain unchanged. Nine new
assessment conditions produce 88 unresolved records total, also represented in
`state.unresolved_conditions` as the same logical records. New conditions specify
resolution evidence, related inherited issue IDs, and owner roles/deadlines only
where supported. Venue confirmation is required before the September 25 walkthrough
at 14:00 Asia/Taipei; an unknown confirming owner is not invented. Five approval
gates remain pending. The four original early-screening records are unchanged;
separate audits retain the fallback conflict, Q-007 hearing-loop gap and both
livestream ceiling violations with unresolved network/venue prerequisites.

Stage 7 is not implemented. Its future recommendation must consume each result's
check IDs, blocking conditions, cost breakdown, witness and source limitations,
not merely compare prices or copy the feasibility label. Conditional does not mean
approved, selected, booked or ready for external action. Keep Operations, category
spending, applicable Programme changes, venue confirmation and external-action
authority separate. Only genuine evidence can change approval statuses; software
implementation permission is not spending authority.

When attendance, quotes, venue conditions or evidence change, identify the earliest
affected source/basis and reevaluate downstream constraints, baselines, options and
checks before updating recommendations or drafts. Preserve historical snapshots
and evidence. The current builders pin approved predecessors and reject changed
inputs; they do not automatically migrate a revised run. A separately reviewed
revision must establish its evidence, lineage and approval applicability. Do not
edit saved JSON, silently replace hashes or reuse stale approval scope to force
validation to pass. Preserve all Entire checkpoints throughout replanning.

## Reproduce Stage 6 safely

The real `deliverables/snapshots/06-feasibility-testing.json` already exists. For
reproduction, use a temporary root containing `snapshot.schema.json`, `interviews/`,
`evidence/originals/`, `evidence/captures/`, and unchanged snapshots 01–05 at their
original relative paths. Use the installed project environment (or a `.venv` symlink
to it). Leave Snapshot 06 absent from the temporary copy. Run from that root:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from pathlib import Path
from event_coordination.stages.feasibility import write_snapshot

path, digest = write_snapshot(Path.cwd())
print(path)
print(digest)
PY
```

For a real generation, run only when authorized and the output is absent. The
exclusive writer checks existence, builds and validates in memory, creates with
`xb`, verifies saved bytes and revalidates the saved JSON. It refuses overwrites.
`build_snapshot(root)` provides validated in-memory assessment without writing.
Reproduction assigns a new UUID and actual creation time, so its file hash differs;
the stable assessment contents must reproduce. Do not remove or replace the real
snapshot to test generation.

## Validate saved Stage 6 read-only

Run from the repository root:

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

Shared validation uses the unchanged schema with date-time checking, then
reconstructs the Stage 6 assessment and checks its exact inputs and lineage.
Supplemental recursive type/structure validation rejects numeric 0/1 in Boolean
fields. Local integrity does not authenticate a remote source or grant approval.

Run the focused Stage 6 validation tests with:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_stage6.py -q -p no:cacheprovider
```

The existing full-suite command also covers Stage 1–5 regressions. Tests include
aggregation precedence, independent monetary inputs, capacity boundaries, quote
expiry ambiguity, scope loss despite unchanged availability, Boolean mutations,
the delayed-opening counterexample, schedule/resource conflicts, actionable
conditions, inherited-record preservation, tampered inputs and exclusive writes
in temporary roots. No tests retrieve live sources.

## Implementation boundaries

Before further implementation, verify course-required session capture is active.
Its status is not verified by the CLI.

The implementation keeps the fixed business clock
`2026-08-26T12:00:00+08:00` (`Asia/Taipei`) separate from actual retrieval and
execution timestamps. All planning outputs and communications remain drafts.
Human decisions and approvals require genuine supporting evidence; missing
approvals remain pending. Booking, spending, invitations, and publishing require
human authorization.

Preserve `README.md`, `snapshot.schema.json`, all interviews, and original evidence
unchanged. Stages 1–6 are implemented; Stages 7–9 and event
plan/CSV/ICS/communication generation remain unimplemented. Stage 2's offline
assembler and Stage 3–6 builders do not call the separately available retrieval utilities. No booking,
spending, invitation, or publishing action is performed. Generated editable-install
`*.egg-info/` metadata is ignored by Git and can remain locally.

Stage 2 is an internal evidence inventory containing aggregate accessibility and
dietary signals. Do not expose private individual medical/contact details or copy
the inventory wholesale into general artifacts. Public repository inclusion needs
explicit publication review. Preserve all Entire checkpoint history; do not delete
or rewrite checkpoints as a documentation or packaging step.
