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

Stages 1–3 use jsonschema with date-time format checking, plus standard-library
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
unchanged. Stages 1–3 are implemented; Stages 4–9 and event
plan/CSV/ICS/communication generation remain unimplemented. Stage 2's offline
assembler and Stage 3 builder do not call the separately available retrieval utilities. No booking,
spending, invitation, or publishing action is performed. Generated editable-install
`*.egg-info/` metadata is ignored by Git and can remain locally.

Stage 2 is an internal evidence inventory containing aggregate accessibility and
dietary signals. Do not expose private individual medical/contact details or copy
the inventory wholesale into general artifacts. Public repository inclusion needs
explicit publication review. Preserve all Entire checkpoint history; do not delete
or rewrite checkpoints as a documentation or packaging step.
