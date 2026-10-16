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

Use Python for repeatable processing, SHA-256 hashing, validation, and draft
generation once implemented. Inspect available CLI help before invoking commands;
the current foundation provides help only. Do not invent stage commands, claim a
planned check ran, or replace an absent implementation with fabricated outputs.

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
