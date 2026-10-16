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

Stage 1 uses jsonschema with date-time format checking, plus standard-library CLI
parsing, JSON, SHA-256 hashing, UUIDs, and timezone-aware timestamps. HTTPX, Jinja2,
icalendar, and tzdata are declared for the planned later workflow; external source
retrieval and event artifact generation are not implemented.

## Display CLI help

```bash
.venv/bin/event-coordination --help
```

Running `event-coordination` without arguments also displays help. Use
`event-coordination stage1 --help` for Stage 1 options.

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
unchanged. Only Stage 1 is implemented. Stages 2–9, external retrieval, and event
plan/CSV/ICS/communication generation remain unimplemented. No booking, spending,
invitation, or publishing action is performed. Generated editable-install
`*.egg-info/` metadata is ignored by Git and can remain locally.
