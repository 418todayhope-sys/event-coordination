# Scenario and task — Event Planning & Coordination Brief

You have joined Quillhaven Academy as an automation specialist. The Event and Operations Manager repeatedly turns changing event goals, attendee signals, budgets, vendor records, official venue information, a floor plan, and calendar constraints into a plan for human review. The current manual process is slow, difficult to trace, and easy to make inconsistent when an input changes.

Interview the stakeholder to understand the real workflow, pain points, constraints, uncertainties, source ownership, and approval boundaries. Then build and execute an Agent Skills-compliant skill named `event-planning-coordination-brief` that fetches the current disclosed sources, compares feasible options, and prepares a consistent event-planning package.

**Interview rule.** You conduct the stakeholder interview yourself, and the questions are yours. Do not connect a coding agent or any other AI to the interview to run, script, or automate it. The interview transcript is assessed together with the code; a project whose interview was run by an agent is not scored.

Your skill must document one end-to-end command, keep the provided snapshot contract unchanged, and write a snapshot at every required workflow boundary before producing the final planning drafts:

```text
snapshot.schema.json  # provided contract
event-planning-coordination-brief/
├── SKILL.md
├── scripts/
└── references/
deliverables/
├── snapshots/
│   ├── 01-scope-and-approval-gates.json
│   ├── 02-source-capture.json
│   ├── 03-constraint-model.json
│   ├── 04-planning-baseline.json
│   ├── 05-option-generation.json
│   ├── 06-feasibility-testing.json
│   ├── 07-decision-and-approval.json
│   ├── 08-draft-propagation.json
│   ├── 09-publication-validation.json
│   └── evidence/
│       └── <retrieved floor plan or image evidence>
├── vendor-comparison.csv
├── event-plan.md
├── event-calendar.ics
└── draft-communications.md
```

## Required snapshot chain

Every stage file must conform to [`snapshot.schema.json`](snapshot.schema.json). All nine use the same `run_id`. From stage 2 onward, `predecessor` identifies and hashes the immediately preceding snapshot. Each transition names the records it consumed and produced.

| Stage | State that must be preserved |
|---|---|
| 01 Scope and approval gates | objective, decision deadline, owners, approval gates |
| 02 Source capture | every attempted structured, web, image, video, and calendar source with retrieval state |
| 03 Constraint model | hard constraints, preferences, assumptions, unknowns, and conflicts |
| 04 Planning baseline | dated headcount basis, schedule dependencies, budget, and accessibility baseline |
| 05 Option generation | materially different options and any early rejection with reason |
| 06 Feasibility testing | capacity, cost, timing, accessibility, availability, quote-validity, and approval results |
| 07 Decision and approval | trade-offs, recommendation or deferral, learner decisions, and human approvals |
| 08 Draft propagation | draft artifacts, affected dependencies, propagated changes, and unresolved items |
| 09 Publication validation | final artifact paths and hashes, validation checks, and publication state |

Run status is `complete`, `partial`, `blocked`, or `failed`. Retrieval status is `retrieved`, `unavailable`, `invalid`, `unverified`, or `stale`. Option feasibility is `feasible`, `infeasible`, `conditional`, or `unverified`. Approval status is `pending`, `approved`, `rejected`, or `not-required`. Record only actual states. A missing, conflicting, stale, or unresolved item must remain traceable through later stages until a recorded evidence-backed resolution or human decision changes it.

On successful image retrieval, `snapshots/evidence/` preserves the official floor-plan or image bytes used for spatial or accessibility claims as part of the assessed run snapshot. Stage 02 records the file and locator; later stages consume its evidence ID.

## Final artifacts

- `vendor-comparison.csv` compares materially different options, including availability or verification state, cost and currency where known, feasibility, material constraints, evidence references, trade-offs, and unresolved conditions.
- `event-plan.md` states the objective, planning basis, options, recommendation or deferral, feasibility, schedule, budget, accessibility and safety considerations, risks, unknowns, change impacts, and approval requests.
- `event-calendar.ics` is a valid draft calendar consistent with the selected or proposed plan. `draft-communications.md` contains clearly unsent drafts that preserve uncertainty and approval dependencies.

The snapshot chain is formal evidence from the assessed run. It does not need to reproduce an earlier version of an external website; it must preserve the evidence and locators actually used during this run and show how those records flowed into decisions and drafts.

Use at least one required official floor-plan or image source disclosed by the stakeholder. Optional video evidence may be used when it improves the plan. If one vendor quote or record is missing or cannot be verified, continue with supported comparisons and mark that vendor record unavailable or unverified. If the required image evidence is unavailable, do not claim spatial or accessibility facts that depend on it.

The plan must compare multiple options, explain feasibility and trade-offs, and keep every affected artifact consistent when an input changes. Treat the calendar and communications as drafts. Do not book, pay, invite, commit to a vendor, write to a production calendar, expose secrets, or bypass operations or budget approval.

Use any implementation language or maintained libraries appropriate to the task. The assessment evaluates the observable workflow, evidence, judgment, outputs, and safety boundary rather than one prescribed technical design or final recommendation.

## Start, sources and evidence access

The business clock for this exercise is **26 August 2026, 12:00, Asia/Taipei**. Evaluate supplied quote validity and planning deadlines at that clock, while recording the actual time at which you retrieve each source. The operating sources are authored exercise data; the official venue pages and floor plan remain real, mutable sources. A fictional quote or coordination note does not prove a real reservation or supplier permission.

Interview entry: [Event and Operations Manager](https://work-sim-alpha.catalyte.ai/s/project-c-event-coordination). This starter contains the assignment, complete source inventory and public snapshot schema. Your facilitator supplies an Agent Skills-capable coding environment and must verify learner identity, interview recording/export, coding-session capture, current remote source access and the assigned submission destination before a graded run. The human-conducted interview and attributed development record are collected through that verified route; do not manufacture an interview/session transcript as a deliverable. Report a missing binding to the facilitator; it is an environment defect, not a reason to invent business evidence.

The source inventory is complete and no exact interview phrase is needed to obtain it:

| Source | Read-only destination |
|---|---|
| Event brief and venue coordination note | https://app.notion.com/p/3ba0b700541e81d0af55dc1a8f49f5af |
| Attendee signals | https://docs.google.com/spreadsheets/d/1IXAEAFsZM6Q9IZZ_9pGqbFQ7l2ikr-oThqrEKudHwIU |
| Budget | https://docs.google.com/spreadsheets/d/1Cxo7CvcgImz9HbT8PThZyvaTuyd44ug7w5rBA1z5qlM |
| Calendar constraints | https://docs.google.com/spreadsheets/d/1f_i6tUCHbJV-Ug_j6U3T4LEZ3yAr2ucdBnID-4C_-8s |
| Vendor register | https://docs.google.com/spreadsheets/d/1cULbGrOQS-vuj862nV2EWND4oe0H5kf-smJ85VZegko |
| Official Plenary Hall page | https://www.ticc.com.tw/wSite/sp?BaseDSD=7&CtUnit=99&ctNode=322&mp=2&roomId=PH&xdUrl=%2FwSite%2Fap%2Fcp_VenueSearch.jsp |
| Official accessibility index | https://www.ticc.com.tw/wSite/lp?ctNode=398&mp=2&xq_xCat=6 |
| Required official 4F floor plan | https://www.ticc.com.tw/wSite/public/Attachment/f1710485827023.pdf |
| Optional venue video | https://www.youtube.com/watch?v=gNFKu6GThVc |

The sources supply business criteria and service conditions; ask the stakeholder about their interpretation and uncertainty. Preserve captured source content or permitted excerpts sufficient to inspect every claim, with ID, URL, version, retrieval time, locator and hash. Do not copy private attendee medical/contact details into general artifacts. Author-only normalized fixtures are not a substitute for the selected sources.

The starter provides this assignment and the unchanged public snapshot schema. You author the Skill and implementation. From the starter root, this small environment smoke verifies only Python 3 and the supplied JSON contract:

```bash
python3 -c "import json,pathlib,sys; s=json.loads(pathlib.Path('snapshot.schema.json').read_text()); assert s['type']=='object'; print(sys.version); print('Public schema readable; business workflow not implemented')"
```

Python is used only for the supplied smoke; use any supported language for your Skill. Your own documented end-to-end command must actually retrieve, plan and write the submitted artifacts. Include its dependencies/setup and distinguish a usable draft, bounded partial result and failed run. Submit the source repository and `deliverables/` through the facilitator's assigned assessment entry; that destination must be verified before the run. Do not assume a public repository or send any communications.

## Record meaning and completion states

Read structured sources by their disclosed field meanings and stable record identities. Accept reordered headers, reordered records and extra unrelated columns when the required fields, identities and business values remain intact, including combinations of those changes. These are representation changes, not new prices, capacities, approvals or event facts. Preserve the captured representation and its actual observation metadata; an unchanged interpretation does not make different source bytes or a later observation identical to the earlier capture. Missing required fields, ambiguous/duplicate identities, incompatible meanings or invalid required values must be reported or held before dependent interpretation; do not guess a renamed field, coerce an unknown value or silently choose a conflicting record.

Use integer TWD amounts and explicit timezone-bearing timestamps. Vendor prices cover quoted packages, not an invented per-person rate. Keep quote identity, category, capacity, date, conditions and evidence. Category allocations, category approval limits, commitments and the overall ceiling are different quantities. A proposed category excess needs the category owner’s explicit amount/plan-bound exception; without it the option remains conditional. Ordinary plan approval does not grant a spending exception, and no category exception overrides the overall ceiling. Preserve source owner and unresolved term rather than filling a blank with zero. Headcount groups and overlapping attendee needs must be distinguished from their source definitions. The quiet-room capacity concerns concurrent quiet-room use, while catering and plenary capacities concern their relevant participant populations.

For every option in `vendor-comparison.csv`, include at least `option_id`, `quote_ids`, `planning_people`, `cost_twd`, `currency`, `feasibility`, `availability_status`, `evidence_ids`, `tradeoffs`, `unresolved`, and `approval_status`. A blank unknown cost remains blank with its reason; CSV lists can be JSON arrays or a documented unambiguous delimiter. Prices and totals must agree with the plan and decision snapshot. A conditional option is not silently called feasible.

The calendar baseline retains all supplied records and their meaning: a decision deadline is not an event duration; the accessibility walkthrough keeps its venue-confirmation dependency; a soft rehearsal window permits the supplied remote backup. Keep future actions tentative and distinguish them from observed confirmation or completed work. Programme slots must fit around fixed events, with every supplied demo and its changeover represented once; total minutes alone do not establish a non-overlapping schedule. Equally valid sequences are allowed.

`event-plan.md` must show the source/run basis, proposed headcount and uncertainty policy, timing and dependencies, category/total amounts, option comparison, accessibility evidence with limits, recommendation or deferral, remaining owners and draft review requests. `event-calendar.ics` uses `VERSION:2.0`, draft `METHOD:PUBLISH`, stable event `UID`, `DTSTAMP`, supported `DTSTART`/`DTEND`, and `STATUS:TENTATIVE` for proposed events. Do not include attendees or delivery actions. If no proposed event time is supportable, submit an empty valid VCALENDAR and explain the deferral in the plan. `draft-communications.md` labels every message UNSENT DRAFT and its intended audience, purpose, conditions and approval owner; it never asserts a booking, payment or invitation was sent.

| Run state | Required result |
|---|---|
| complete | Nine valid linked snapshots and all four internally consistent review drafts, supported option comparisons and a justified recommendation; spend/plan approval can remain pending because the result is a draft |
| partial | Nine linked snapshots and four drafts with supported work preserved, unavailable source/conditional claims and resolution owner visible; no unsupported spatial or availability claim |
| blocked | Nine snapshots when the run can retain valid evidence, comparison and plan explaining why no supported recommendation exists, empty draft calendar and unsent clarification drafts. This is valid for genuine source/fact blockage, not missing author-supplied business rules |
| failed | `deliverables/failure.json` with run_id, observed_at, error, affected_stage, available_evidence, affected_artifacts, next_owner and recovery action; no claim of completed snapshots or reuse of old successful outputs. Write only evidence actually obtained before failure |

If a required source fails during a run, record its real attempt and the affected claim; supported independent work may continue. If a hard condition is false, reject the option. If it is unknown, preserve it as conditional/unverified. More than one recommendation may satisfy the same facts. Explain your choices with source-grounded consequences; do not assume an expected winner.

## Re-entry and learner decisions

Before processing a material change, retain the previous current run under `deliverables/history/<run_id>/`. Write a coherent new set of the same nine current filenames with a new run_id and unique snapshot_ids. Stage01 state records `supersedes_run_id`, changed source/decision IDs and the reason; predecessor links thereafter bind the new run. Inspect historical identity and hashes before using them. Missing or malformed prior history must not be reconstructed as though it had been observed. Retained media can be referenced by hash without copying identical bytes again.

Reconsider every affected headcount, cost, capacity, schedule, availability, accessibility, option, approval request and draft; justify which evidence remains unchanged. Source changes need not trigger unrelated retrieval or a forced choice of technology. If inputs are unchanged but a required output is missing or damaged, repair and validate it or return an explicit incomplete/failure result; a previous success is not evidence the current bundle is intact.

This retry check includes a file that still exists but has corrupt or stale content, not only a deleted file: inspect actual output content and its run bindings before reporting success. After a failed source or output validation, retain the failed attempt and earlier evidence as history, with no prior or partial package represented as successful current work. When the source or output becomes usable again, revalidate the affected work and record the actual new attempt before reporting a recovered result. The same business facts and decision bindings must retain their meaning, including any conditional or unresolved claims, pending approvals, tentative calendar entries and unsent communications. Recovery does not establish that a prerequisite was completed, an approval granted or a message sent. A truthful bounded partial/blocked result or the disclosed failure receipt remains valid when recovery cannot establish a supported normal bundle.

During your own interview/development/review, make attributable project-specific decisions about evidence, headcount uncertainty, inherited assumptions, option trade-offs and change effects where those choices arise. Ground a choice in the relevant source and explain its consequence; concise decisions are sufficient. A perfect AI-generated artifact or retrospective generic assent cannot by itself establish your ownership. Approvals remain the named humans' responsibility. The platform's actual capture route must work; a learner-authored JSON field cannot replace it.
