# Project C implementation

## Install

Use Python 3.12 or newer. From the repository root, create an isolated environment
and install the package:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

For future test development, install the optional development dependencies:

```bash
.venv/bin/python -m pip install -e '.[dev]'
```

The declared dependencies support the planned implementation: HTTPX for source
retrieval, jsonschema with format checking for snapshot validation, Jinja2 for
draft templates, icalendar for calendar drafts, and tzdata for timezone data.
Python's standard library will provide CLI parsing, JSON, SHA-256 hashing, and
timezone-aware clock handling. These workflow capabilities are not implemented yet.

## Display CLI help

```bash
.venv/bin/event-coordination --help
```

Running `event-coordination` without arguments also displays help. The CLI has no
planning commands and does not retrieve sources or generate deliverables.

To check the help-only entry point directly from the source tree without installing
dependencies:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m event_coordination.cli --help
```

## Implementation boundaries

Before further implementation, verify course-required session capture is active.
Its status has not been verified by this foundation CLI.

The future workflow must keep the fixed business clock
`2026-08-26T12:00:00+08:00` (`Asia/Taipei`) separate from actual retrieval and
execution timestamps. All planning outputs and communications remain drafts.
Human decisions and approvals require genuine supporting evidence; missing
approvals remain pending. Booking, spending, invitations, and publishing require
human authorization.

Preserve `README.md`, `snapshot.schema.json`, and the original interview export
unchanged. No nine-stage workflow, external retrieval, or deliverable generation
is included in this foundation.
