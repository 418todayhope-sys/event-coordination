"""Shared schema validation with stage-specific evidence and lineage checks."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from event_coordination.sources import read_evidence
from event_coordination.stages.scope import BUSINESS_CLOCK, DEADLINE, GATES, OWNERS, SELECTIONS


def validate_snapshot(snapshot: dict, root: Path) -> None:
    from event_coordination.run_contract import current_run, validate_run_metadata
    session = current_run(root)
    if session is not None:
        if type(snapshot) is not dict or snapshot.get("run_id") != session.run_id:
            raise ValueError("Snapshot is outside the active run")
        if snapshot.get("sequence") == 1:
            metadata = snapshot.get("state", {}).get("run_metadata")
            validate_run_metadata(metadata)
            if metadata != session.metadata:
                raise ValueError("Stage 1 run metadata differs from the active run")
    if isinstance(snapshot, dict) and snapshot.get("stage") == "publication-validation":
        from event_coordination.stages.publication import validate_stage9
        validate_stage9(snapshot, root)
        return
    if isinstance(snapshot, dict) and snapshot.get("stage") == "draft-propagation":
        from event_coordination.stages.drafts import validate_stage8
        validate_stage8(snapshot, root)
        return
    # Stage 7 must pin its schema before the first schema read, not only after
    # the shared validator has already inspected potentially changing bytes.
    if isinstance(snapshot, dict) and snapshot.get("stage") == "decision-and-approval":
        from event_coordination.stages.decisions import validate_stage7
        validate_stage7(snapshot, root)
        return
    schema = json.loads((root / "snapshot.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(snapshot)
    if snapshot["stage"] == "source-capture":
        from event_coordination.stages.capture import validate_stage2
        validate_stage2(snapshot, root)
        return
    if snapshot["stage"] == "constraint-model":
        from event_coordination.stages.constraints import validate_stage3
        validate_stage3(snapshot, root)
        return
    if snapshot["stage"] == "planning-baseline":
        from event_coordination.stages.baseline import validate_stage4
        validate_stage4(snapshot, root)
        return
    if snapshot["stage"] == "option-generation":
        from event_coordination.stages.options import validate_stage5
        validate_stage5(snapshot, root)
        return
    if snapshot["stage"] == "feasibility-testing":
        from event_coordination.stages.feasibility import validate_stage6
        validate_stage6(snapshot, root)
        return
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    require(snapshot["stage"] == "scope-and-approval-gates" and snapshot["sequence"] == 1,
            "Only Stages 1 through 9 validation are implemented")
    require(snapshot["predecessor"] is None and snapshot["consumed_record_ids"] == [],
            "Invalid Stage 1 lineage")
    state = snapshot["state"]
    require(state["decision_deadline"] == DEADLINE, "Unsupported Operations deadline")
    require(state["business_clock"] == BUSINESS_CLOCK, "Incorrect business clock")
    require(state["decision_deadline_scope"] == "Operations approval of the event plan"
            and state["decision_deadline_timezone"] == "Asia/Taipei", "Incorrect deadline scope/timezone")
    expected = [read_evidence(root, *s) for s in SELECTIONS]
    require(state["evidence_records"] == expected, "Evidence hash, location, excerpt, or provenance mismatch")
    records = (state["evidence_records"] + state["scope_records"]
               + state["approval_requirements"] + snapshot["unresolved"])
    if session is not None:
        from event_coordination.input_changes import request_records, DECISION_PATH
        from event_coordination.sources import hash_bytes
        requests = request_records(root)
        if requests:
            expected_requests = [dict(r, evidence_ids=["scope-gates"], path=DECISION_PATH,
                sha256=hash_bytes((root / DECISION_PATH).read_bytes())) for r in requests]
            if state.get("decision_requests") != expected_requests:
                raise ValueError("Decision requests differ from preserved advisory inputs")
            records += [dict(r, evidence_ids=["scope-gates"]) for r in requests]
    ids = [r["id"] for r in records]
    require(len(ids) == len(set(ids)), "Duplicate record IDs")
    require(set(snapshot["produced_record_ids"]) == set(ids), "Produced record lineage mismatch")
    for record in records:
        Draft202012Validator({"$ref": "#/$defs/record", "$defs": schema["$defs"]}).validate(record)
        require(all(e in ids for e in record["evidence_ids"]), "Unresolved evidence reference")
    expected_links = {
        "objective": ["ev-objective"], "decision_deadline": ["ev-deadline"],
        "owners": ["ev-owners", "ev-programme"],
        "approval_gates": ["ev-gates", "ev-owners", "ev-exceptions", "ev-programme"],
    }
    require(len(state["scope_records"]) == 4, "Missing scope provenance")
    require({r["field"] for r in state["scope_records"]} == set(expected_links), "Invalid scope fields")
    for record in state["scope_records"]:
        require(record["value"] == state[record["field"]] and
                record["evidence_ids"] == expected_links[record["field"]], "Scope provenance mismatch")
    require(state["objective"] == SELECTIONS[0][3], "Unsupported objective")
    require(state["owners"] == OWNERS and state["approval_gates"] == GATES,
            "Unsupported owners or approval gates")
    require(len(state["approval_requirements"]) == len(state["approval_gates"]), "Missing approval requirement")
    for approval, gate in zip(state["approval_requirements"], state["approval_gates"]):
        Draft202012Validator({"$ref": "#/$defs/approvalRecord", "$defs": schema["$defs"]}).validate(approval)
        require(approval["status"] == "pending" and approval["summary"] == gate,
                "No granted approvals are supported by this Stage 1 evidence")
    require(snapshot["decisions"] == [] and state["output_status"] == "draft",
            "Unsupported decision or final output")
