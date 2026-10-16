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

Only Stage 1 is implemented. Inspect `event-coordination stage1 --help` before
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
Do not invent commands for Stages 2–9, claim unexecuted checks passed, or replace
absent implementation with fabricated outputs. Stage 1 performs no external source
retrieval or event plan, calendar, comparison CSV, or communication generation.

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
