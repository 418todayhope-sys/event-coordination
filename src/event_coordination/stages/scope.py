"""Evidence-backed Stage 1; no external retrieval or approval automation."""

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from event_coordination.sources import hash_bytes, read_evidence

DEADLINE = "2026-09-04T17:00:00+08:00"
BUSINESS_CLOCK = "2026-08-26T12:00:00+08:00"
BRIEF = "evidence/originals/event-brief-manually-completed.txt"
ORIGINAL = "interviews/project-c-event-coordination-20261016-1954.md"
FOLLOWUP = "interviews/project-c-event-coordination-20261016-2056.md"
OUTPUT = "deliverables/snapshots/01-scope-and-approval-gates.json"
OWNERS = ["Operations", "Category budget owners", "Programme"]
GATES = [
    "Operations approval of the overall event plan, date, and venue.",
    "Category budget owner authorization of spending and category exceptions; the overall ceiling cannot be exceeded.",
    "Programme authorization of roster or duration changes when proposed.",
    "Human authorization before invitations, booking, vendor commitments, payment, or production-calendar writes.",
]

# Reviewed source selections, not a general-purpose business-data extractor.
SELECTIONS = [
    ("ev-objective", BRIEF, 16,
     "The event should let fellows present work, give partners a useful programme overview, and support accessible participation.",
     "Manually completed Notion copy; not an untouched export."),
    ("ev-gates", BRIEF, 19,
     "Operations approves the plan. Budget owners approve spending.",
     "Manually completed Notion copy; not an untouched export."),
    ("ev-review", BRIEF, 34, "No booking or spend has been approved.",
     "Manually completed Notion copy; not an untouched export."),
    ("ev-programme", BRIEF, 47, "Programme owns roster or duration changes.",
     "Manually completed Notion copy; programme section missing from preserved PDF."),
    ("ev-owners", ORIGINAL, 636,
     "Operations owns the overall event plan, date, and venue approval.",
     "Original stakeholder interview export."),
    ("ev-exceptions", ORIGINAL, 644,
     "However, this cannot exceed the overall budget ceiling.",
     "Original stakeholder interview export."),
    ("ev-deadline", FOLLOWUP, 790,
     "The exact deadline for Operations to approve the event plan is September 4, 2026, at 17:00, Asia/Taipei time (+08:00).",
     "Second preserved stakeholder interview export; explicit deadline clarification."),
]


def build_snapshot(root: Path, run_id: str | None = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    evidence = [read_evidence(root, *selection) for selection in SELECTIONS]
    owners = list(OWNERS)
    gates = list(GATES)
    def record(record_id, field, value, evidence_ids):
        return {"id": record_id, "summary": str(value), "evidence_ids": evidence_ids,
                "field": field, "value": value}
    objective = SELECTIONS[0][3]
    scope = [
        record("scope-objective", "objective", objective, ["ev-objective"]),
        record("scope-deadline", "decision_deadline", DEADLINE, ["ev-deadline"]),
        record("scope-owners", "owners", owners, ["ev-owners", "ev-programme"]),
        record("scope-gates", "approval_gates", gates,
               ["ev-gates", "ev-owners", "ev-exceptions", "ev-programme"]),
    ]
    approvals = [
        {"id": f"approval-{index}", "summary": gate, "evidence_ids": scope[3]["evidence_ids"],
         "status": "pending"}
        for index, gate in enumerate(gates, 1)
    ]
    unresolved = [{
        "id": "unknown-category-owner-identities",
        "summary": "Individual category budget owner identities and assignments have not been established from the selected evidence; confirm during source capture.",
        "evidence_ids": ["ev-owners"], "owner": None,
    }]
    state = {
        "objective": objective, "decision_deadline": DEADLINE,
        "owners": owners, "approval_gates": gates,
        "decision_deadline_scope": "Operations approval of the event plan",
        "decision_deadline_timezone": "Asia/Taipei",
        "business_clock": BUSINESS_CLOCK, "business_timezone": "Asia/Taipei",
        "local_evidence_inspected_at": now,
        "evidence_records": evidence, "scope_records": scope,
        "approval_requirements": approvals, "output_status": "draft",
        "provenance_limitations": [
            "Local inspection timestamps are not original online retrieval times.",
            "The manually completed brief is distinct from the preserved incomplete PDF; no online equivalence is asserted.",
        ],
    }
    records = evidence + scope + approvals + unresolved
    return {
        "schema_version": "event-coordination-stage-snapshot/2",
        "snapshot_id": str(uuid4()), "run_id": run_id if run_id is not None else str(uuid4()),
        "stage": "scope-and-approval-gates", "sequence": 1, "created_at": now,
        "status": "partial", "predecessor": None, "consumed_record_ids": [],
        "produced_record_ids": [r["id"] for r in records],
        "state": state, "unresolved": unresolved, "decisions": [],
    }


def write_snapshot(root: Path, run_id: str | None = None) -> tuple[Path, str]:
    from event_coordination.validation import validate_snapshot

    snapshot = build_snapshot(root, run_id)
    validate_snapshot(snapshot, root)
    target = root / OUTPUT
    target.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    # Exclusive creation refuses overwrites, including concurrent writers.
    with target.open("xb") as stream:
        stream.write(content)
    saved = target.read_bytes()
    validate_snapshot(json.loads(saved), root)
    return target, hash_bytes(saved)
