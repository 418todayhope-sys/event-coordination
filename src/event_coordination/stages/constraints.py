"""Stage 3: evidence-linked requirements, facts, dependencies and uncertainty.

No option selection, attendance finalization, scheduling, approval or retrieval.
"""

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import re
from uuid import uuid4

from event_coordination.constraint_sources import source_line, validate_dependencies, workbook_rows
from event_coordination.sources import hash_bytes
from event_coordination.stages.capture import OUTPUT as PREDECESSOR_PATH
from event_coordination.stages.scope import BRIEF, ORIGINAL, FOLLOWUP

PREDECESSOR_HASH = "sha256:abe8ff40d45da1e8ba8c45f35b715db99b17bd40fe66d5e5adc331334d00fe70"
OUTPUT = "deliverables/snapshots/03-constraint-model.json"
CATEGORIES = ("hard_constraints", "preferences", "assumptions", "unknowns", "conflicts")


def _inputs(root: Path) -> dict:
    from event_coordination.validation import validate_snapshot

    content = (root / PREDECESSOR_PATH).read_bytes()
    if hash_bytes(content) != PREDECESSOR_HASH:
        raise ValueError("Stage 2 predecessor hash differs from approved snapshot")
    upstream = json.loads(content)
    validate_snapshot(upstream, root)
    captures = upstream["state"]["sources"]
    capture_index = {c["id"]: c for c in captures}
    manual_brief = next(c for c in captures if c["local_reference"] == BRIEF)
    observations = {o["id"]: (c, o) for c in captures for o in c["observations"]}
    upstream_ids = set(upstream["produced_record_ids"])
    state = {category: [] for category in CATEGORIES}
    state.update(source_facts=[], approval_requirements=[])
    coverage = {}

    def add(category, identifier, summary, evidence, *, basis="stakeholder-rule",
            rule=None, dependencies=(), owner=None, source_values=None, **extra):
        evidence = list(dict.fromkeys(evidence))
        provenance = []
        for eid in evidence:
            if eid in observations:
                capture, observation = observations[eid]
                provenance.append({"evidence_id": eid, "capture_id": capture["id"],
                                   "path": capture["local_reference"], "sha256": capture["content_hash"],
                                   "locator": observation["locator"],
                                   "retrieval_status": capture["retrieval_status"]})
            elif eid in capture_index:
                capture = capture_index[eid]
                provenance.append({"evidence_id": eid, "capture_id": eid,
                                   "path": capture["local_reference"], "sha256": capture["content_hash"],
                                   "locator": capture["locator"], "retrieval_status": capture["retrieval_status"]})
        record = {"id": identifier, "summary": summary, "evidence_ids": evidence,
                  "basis": basis, "owner": owner, "provenance": provenance,
                  "verification": "inherits-upstream-limitations",
                  "fulfillment": "not-evaluated", "depends_on_record_ids": list(dependencies), **extra}
        if rule is not None:
            record["rule"] = rule
        if source_values is not None:
            record["source_values"] = source_values
        state[category].append(record)
        return record

    def interview(identifier, line, expected, summary, evidence, category="hard_constraints", **kwargs):
        return add(category, identifier, summary, evidence,
                   source_values=[source_line(root, ORIGINAL, line, expected)], **kwargs)

    def brief_fact(identifier, line, expected, evidence, **values):
        original = source_line(root, BRIEF, line, expected)
        # Some brief details were not individually observed in Stage 2. Cite the
        # captured file plus this checked line, not an unrelated observation.
        anchors = [manual_brief["id"]]
        ranges = {"obs-brief-text-objective": (16, 18), "obs-brief-text-fictional": (29, 33),
                  "obs-brief-text-programme": (43, 47)}
        if evidence in ranges and ranges[evidence][0] <= line <= ranges[evidence][1]:
            anchors.append(evidence)
        return add("source_facts", identifier, expected, anchors, basis="source-fact",
                   source_values=[original], values=values, scope="fictional-exercise")

    # Retain every upstream observation, including source-identity and index facts.
    for eid, (capture, observation) in observations.items():
        add("source_facts", "fact-evidence-" + eid, observation["summary"], [eid],
            basis="source-fact", source_values=[deepcopy(observation)],
            publication_kind=capture["version_metadata"]["publication_kind"])

    tables = {}
    specs = [
        ("budget-allocations", "Budget", "obs-budget-row-", "fact-budget-", "category",
         ["category", "planned_amount_twd", "approval_limit_twd", "committed_amount_twd", "owner", "record_version"]),
        ("attendee-signals", "Attendee Signals", "obs-attendee-", "fact-signal-", "signal_id",
         ["signal_id", "source", "segment", "signal", "value", "unit", "observed_at", "confidence"]),
        ("vendor-register", "Vendor Quotes", "obs-quote-", "fact-quote-", "quote_id",
         ["quote_id", "vendor", "category", "option", "quote_amount_twd", "capacity", "available_date", "valid_until", "status", "notes"]),
        ("calendar-constraints", "Calendar Constraints", "obs-calendar-", "fact-calendar-", "constraint_id",
         ["constraint_id", "owner", "constraint_type", "start_at", "end_at", "priority", "notes", "record_version"]),
    ]
    for identity, sheet, obs_prefix, fact_prefix, key, headers in specs:
        capture = next(c for c in captures if c["source_identity"] == identity and c["local_reference"])
        rows = workbook_rows(root, capture, sheet)
        if list(rows[0]["values"].values()) != headers:
            raise ValueError("Unexpected source headers")
        tables[identity] = []
        for number, row in enumerate(rows[1:], 2):
            values = dict(zip(headers, row["values"].values(), strict=True))
            if any(v is None for v in values.values()):
                raise ValueError("Required source cell missing; do not invent a value")
            semantic = values[key]
            eid = obs_prefix + (str(number) if identity == "budget-allocations" else semantic.lower())
            if eid not in observations:
                raise ValueError("Worksheet row lacks an upstream observation")
            units = {field: "TWD" for field in values if field.endswith("_twd")}
            if identity == "attendee-signals":
                units["value"] = values["unit"]
            if identity == "vendor-register":
                units["capacity"] = "service-specific capacity; exact unit not independently specified"
            classification = "source-statement"
            if identity == "attendee-signals":
                classification = "forecast-estimate" if values["source"] == "forecast" else "source-reported-signal"
            fact = add("source_facts", fact_prefix + semantic, f"Source fields for {semantic}.", [eid],
                       basis="source-fact", values=values, units=units, interpretation=classification,
                       source_values=[{"evidence_id": eid, "original_cell_values": row["raw"],
                                       "locator": f"'{sheet}'!A{number}:{chr(64 + len(headers))}{number}"}])
            tables[identity].append(fact)

    brief_fact("fact-brief-objective", 16, "The event should let fellows present work",
               "obs-brief-text-objective")
    ceiling = brief_fact("fact-budget-total", 17, "The total approved planning ceiling is TWD",
                         "obs-brief-pdf-objective")
    # The text supplies the lexical value; the PDF observation is corroborating.
    ceiling["evidence_ids"].append("obs-brief-text-objective")
    amount = re.search(r"ceiling is TWD (\d+)", ceiling["source_values"][0]["excerpt"])
    if not amount:
        raise ValueError("Budget ceiling missing")
    ceiling["values"] = {"value": amount[1], "unit": "TWD"}
    add("hard_constraints", "hc-budget-total", "Total proposed cost must not exceed the overall ceiling.",
        ceiling["evidence_ids"], basis="explicit-exercise-requirement", dependencies=[ceiling["id"]],
        rule={"subject": "total_proposed_cost", "operator": "<=", **ceiling["values"]})
    for fact in tables["budget-allocations"]:
        v = fact["values"]
        add("hard_constraints", "hc-budget-authorization-" + v["category"],
            "Spending requires category-owner authorization; above-limit exceptions require explicit amount/plan approval and cannot exceed the overall ceiling.",
            fact["evidence_ids"] + ["obs-brief-text-approvals"], dependencies=[fact["id"], "hc-budget-total"],
            owner=v["owner"], rule={"subject": v["category"], "planned_allocation": v["planned_amount_twd"],
                                   "approval_limit": v["approval_limit_twd"], "committed": v["committed_amount_twd"],
                                   "unit": "TWD", "authorization": "required-for-all-spending",
                                   "planned_amount_role": "baseline-allocation; reallocation-policy-unresolved",
                                   "approval_limit_role": "explicit-owner-exception-threshold",
                                   "exception": "explicit-owner-approval-required"},
            source_values=[source_line(root, ORIGINAL, 636, "Category budget owners must approve all spending"),
                           source_line(root, ORIGINAL, 644, "this cannot exceed the overall budget ceiling")])
    declared = brief_fact("fact-declared-headcount", 15, "Plan for 245 people", "obs-brief-text-objective")
    declared["values"] = {"value": "245", "unit": "people", "meaning": "declared planning quantity, not check-ins"}
    interview("hc-nonadditive-needs", 53, "don't add them as additional people",
              "Accessibility and dietary needs overlap existing cohorts and add no people to the headcount.",
              ["source-group-attendee-signals"])
    interview("hc-qualitative-confidence", 121, "not a numerical probability",
              "Confidence labels are qualitative; do not convert them to attendance probabilities.",
              ["source-group-attendee-signals"])
    interview("hc-capacity-coverage", 300, "comparing the total planning headcount",
              "Each selected service and seating allocation must cover its applicable planning demand and accessibility needs.",
              ["source-group-attendee-signals", "source-group-vendor-register"],
              rule={"operator": "capacity>=applicable-demand", "demand_basis": "not-finalized"})
    for fact in tables["attendee-signals"]:
        v = fact["values"]
        if v["segment"] == "all":
            add("hard_constraints", "hc-response-" + v["signal_id"],
                "Provide and document a response to this overlapping need without exposing personal details.",
                fact["evidence_ids"] + ["obs-brief-text-objective", "obs-brief-text-fictional"],
                dependencies=[fact["id"], "hc-nonadditive-needs"],
                rule={"need": v["signal"], "value": v["value"], "unit": v["unit"],
                      "fulfilled": None})
    success = brief_fact("fact-success-criteria", 18, "at least 80 percent", "obs-brief-text-objective",
                         check_in_target="80", unit="percent-of-registered", all_demos=True,
                         accessibility_response="documented-before-event")
    add("hard_constraints", "hc-success-criteria", "Preserve the stated success targets; the check-in target is not a capacity discount.",
        success["evidence_ids"], dependencies=[success["id"]],
        rule={"success_targets": success["values"], "headcount_discount_authorized": False})

    # Every source calendar interval retains its supplied priority and wording.
    for fact in tables["calendar-constraints"]:
        v = fact["values"]
        category = "preferences" if v["priority"] == "soft" else "hard_constraints"
        dependencies = [fact["id"]]
        if v["constraint_id"] == "CAL-006":
            dependencies.append("gate-venue-confirmation")
        rule = {"type": v["constraint_type"], "start_at": v["start_at"], "end_at": v["end_at"],
                "source_priority": v["priority"], "notes": v["notes"],
                "applicability": "if-this-event-date-is-proposed" if v["constraint_id"] in ("CAL-001", "CAL-002", "CAL-003", "CAL-008") else "as-specified"}
        if v["constraint_id"] == "CAL-005":
            rule["meaning"] = "decision-deadline-instant; not a scheduled activity"
        if v["constraint_id"] == "CAL-006":
            rule["requires_before"] = {"record_id": "gate-venue-confirmation", "before": v["start_at"]}
        add(category, "hc-" + v["constraint_id"] if category == "hard_constraints" else "pref-" + v["constraint_id"],
            f"Preserve {v['constraint_type']} with source priority {v['priority']}.",
            fact["evidence_ids"], owner=v["owner"], dependencies=dependencies, rule=rule)
    deadline = source_line(root, FOLLOWUP, 790, "September 4, 2026, at 17:00, Asia/Taipei time (+08:00)")
    add("source_facts", "fact-operations-deadline", "Stakeholder-confirmed Operations event-plan approval deadline.",
        ["obs-calendar-cal-005"], basis="stakeholder-rule", source_values=[deadline],
        values={"value": "2026-09-04T17:00:00+08:00", "timezone": "Asia/Taipei", "scope": "Operations event-plan approval"})
    venue = brief_fact("fact-venue-arrangement", 31, "500 usable audience places", "obs-brief-text-fictional",
                       audience_places="500", wheelchair_spaces_included="6", quiet_room_max_people="20",
                       companions="ordinary places", rooms=["4F Plenary Hall", "V.I.P. Room"], room_401="not-selected")
    brief_fact("fact-venue-case-confirmation", 32, "For this case, venue coordination confirms", "obs-brief-text-fictional")
    service = brief_fact("fact-base-service-confirmation", 33, "StreamNorth Q-008", "obs-brief-text-fictional")
    readiness = brief_fact("fact-base-readiness", 40, "For the 17 October 2026 exercise plan", "obs-brief-text-fictional",
                           applies_on="2026-10-17", condition="specified-base-bundles-only", real_world_test=False)
    windows = brief_fact("fact-setup-teardown-windows", 41, "07:30–09:30", "obs-brief-text-fictional",
                         setup_start="07:30", setup_end="09:30", teardown_start="17:00", teardown_end="18:30",
                         timezone="Asia/Taipei", mandatory_extra_buffer=None, individual_vendor_durations=None)
    add("hard_constraints", "hc-venue-allocation", "Respect the exercise room allocation and its separate audience, wheelchair and quiet-room limits.",
        venue["evidence_ids"] + ["obs-quote-q-001", "obs-quote-q-002"], dependencies=[venue["id"]],
        rule={"allocation": venue["values"], "real_reservation": False})
    add("hard_constraints", "hc-setup-teardown", "Fit readiness and clearance within the specified access windows; do not invent extra mandatory buffers.",
        windows["evidence_ids"] + ["obs-calendar-cal-003", "obs-calendar-cal-008"],
        dependencies=[windows["id"], readiness["id"]], rule=windows["values"])
    add("hard_constraints", "hc-security-readiness", "Provide the exercise baseline security service by opening; quote-specific first-aid staffing remains a service condition, not a vendor selection.",
        ["obs-quote-q-009", manual_brief["id"]], dependencies=[readiness["id"], "fact-quote-Q-009"],
        source_values=[source_line(root, BRIEF, 40, "security services are ready by 09:30")],
        rule={"required_service": "security", "ready_by_local_time": "09:30", "selected_vendor": None})
    for feature in ("step-free-programme", "step-free-restrooms", "wheelchair-seating", "live-captions", "staffed-quiet-room"):
        add("hard_constraints", "hc-accessibility-" + feature, f"Require {feature} with evidence of provision.",
            ["obs-brief-pdf-objective", "obs-brief-text-objective"], basis="explicit-exercise-requirement",
            source_values=[source_line(root, BRIEF, 17, "Hard requirements are step-free access")],
            rule={"feature": feature, "provision_verified": None})
    interview("hc-safety", 674, "safety standards", "Safety, hard accessibility and guaranteed access times are review requirements; no new technical standard is inferred.",
              ["obs-brief-text-approvals", "obs-calendar-cal-003"])
    programme = brief_fact("fact-programme-roster", 46, "Each demonstration needs 10 minutes", "obs-brief-text-programme")
    text = programme["source_values"][0]["excerpt"]
    demos = re.findall(r"DEMO-\d{2}", text)
    if len(demos) != 12 or len(set(demos)) != 12:
        raise ValueError("Unexpected programme roster")
    programme["values"] = {"demo_ids": demos, "presentation_minutes": "10", "changeover_minutes": "3",
                           "include_each": "once", "attendance_effect": "no-additional-people"}
    brief_fact("fact-programme-authority", 47, "Programme owns roster or duration changes", "obs-brief-text-programme")
    add("hard_constraints", "hc-programme-demos", "Include every source demo once with separate presentation and changeover allowances.",
        programme["evidence_ids"], dependencies=[programme["id"]], rule=programme["values"])
    for fact in tables["vendor-register"]:
        v = fact["values"];qid = v["quote_id"]
        add("hard_constraints", "hc-quote-" + qid, "If proposed, verify quote date, validity, service scope, capacity and source conditions.",
            fact["evidence_ids"], dependencies=[fact["id"], "hc-capacity-coverage"],
            rule={"applies_if": {"quote_proposed": qid}, "available_date": v["available_date"],
                  "valid_until": v["valid_until"], "source_status": v["status"],
                  "scope": v["option"], "capacity": v["capacity"], "conditions": v["notes"],
                  "expiry_cutoff_time": None, "availability_independently_confirmed": False})
    for qid, requirement in [("Q-004", "Named allergy coordination contacts must be available through Operations; do not publish their identities."),
                             ("Q-008", "Network-test evidence and venue confirmation are required before livestream use."),
                             ("Q-010", "Venue must supply the quiet room; the quote supplies staffing only.")]:
        add("hard_constraints", "hc-quote-prerequisites-" + qid, requirement,
            ["obs-quote-" + qid.lower(), "obs-brief-text-fictional"],
            dependencies=["fact-quote-" + qid, service["id"]],
            rule={"applies_if": {"quote_proposed": qid}, "requirement": requirement, "satisfied": None})
    interview("pref-familiar-suppliers", 436, "I prefer familiar suppliers", "Prefer familiar suppliers after hard requirements are satisfied; no supplier is presumed familiar.",
              ["source-group-vendor-register"], category="preferences")
    interview("hc-no-silent-unknowns", 372, "treated as unknown, never zero or approved",
              "Preserve missing and conflicting evidence as unknown, not zero or approval.", ["source-group-event-brief"])
    interview("hc-no-hard-conflict-override", 428, "render an option infeasible unless the owner resolves",
              "Do not override hard blackouts or access-window conflicts without evidenced owner resolution.",
              ["source-group-calendar-constraints"])
    add("hard_constraints", "hc-supported-alternatives", "Retain two materially different alternatives when supported; remaining hard dependencies are conditional and a second feasible option must not be fabricated.",
        ["obs-brief-pdf-exercise", manual_brief["id"]], basis="explicit-exercise-requirement",
        source_values=[source_line(root, BRIEF, 24, "do not fabricate a second feasible option")],
        rule={"alternative_target": "2", "unit": "materially-different-alternatives",
              "applies_if": "supported-by-evidence", "hard_dependency_classification": "conditional"})
    interview("hc-change-propagation", 364, "earliest affected basis", "Reevaluate from the earliest affected basis and update every dependent draft when evidence changes.",
              ["source-group-event-brief"])
    interview("hc-revised-review", 492, "seek review", "Scope changes require review by affected Operations or budget owners.",
              ["obs-brief-text-approvals"])
    interview("hc-draft-boundary", 682, "no final bookings", "Pending authorization prevents final bookings, releases and commitments.",
              ["obs-brief-text-approvals"], rule={"outputs": "draft", "external_actions_authorized": False})
    add("hard_constraints", "hc-privacy", "Do not expose individual attendee medical/contact details in general outputs; minimize unnecessary aggregate-needs circulation.",
        ["obs-brief-text-fictional", "source-group-attendee-signals"],
        source_values=[source_line(root, BRIEF, 33, "without inventing or publishing personal medical details")])
    for identifier, summary, owner, applies_if, evidence in [
        ("gate-operations", "Operations approval of the plan, date and venue.", "Operations", "before-final-plan-commitments", ["obs-brief-text-approvals", "obs-calendar-cal-005"]),
        ("gate-spending", "Category-owner authorization of spending and exceptions within the overall ceiling.", "Category budget owners", "before-spending", ["obs-brief-text-approvals"]),
        ("gate-programme", "Programme owns roster or duration changes; ordering within the source brief is a planning choice.", "Programme", "if-roster-or-duration-changes", ["obs-brief-text-programme"]),
        ("gate-venue-confirmation", "Venue confirmation is required before the accessibility walkthrough.", None, "before-accessibility-walkthrough", ["obs-calendar-cal-006"]),
        ("gate-external-actions", "Human authorization required before invitations, booking, commitments, payment or calendar writes.", None, "before-external-action", ["obs-brief-text-approvals"]),
    ]:
        approval = add("approval_requirements", identifier, summary, evidence, owner=owner,
                       status="pending", applies_if=applies_if)
        if identifier == "gate-operations":
            approval["deadline"] = "2026-09-04T17:00:00+08:00"
            approval["depends_on_record_ids"] = ["fact-operations-deadline"]

    # Retain every Stage 2 limitation, with the original ID as its upstream evidence.
    for gap in upstream["unresolved"]:
        category = "conflicts" if gap["category"] == "possible_interpretations_not_resolutions" else "unknowns"
        add(category, "unknown-inherited-" + gap["id"], gap["summary"], [gap["id"]],
            basis="unresolved-information", origin_record_id=gap["id"], original_detail=deepcopy(gap),
            resolution="unresolved", conflict_kind="potential" if category == "conflicts" else None)
    add("unknowns", "unknown-budget-reallocation", "Allocation transfer policy and whether planned amounts are fixed allocations are not explicitly established.",
        ["source-group-budget-allocations"], basis="unresolved-information", resolution="unresolved")
    add("unknowns", "unknown-live-accessibility", "Registered official observations identify the floor plan/index, not current operation, unobstructed routes, staffing or captions.",
        ["obs-floor-plan-level", "obs-floor-plan-venue", "obs-accessibility-index"],
        basis="unresolved-information", resolution="unresolved")
    add("unknowns", "unknown-approvals", "No genuine approval outcomes have been supplied; gate requirements remain pending.",
        ["obs-brief-text-approvals"], basis="unresolved-information", resolution="unresolved",
        dependencies=[r["id"] for r in state["approval_requirements"]])
    add("conflicts", "conflict-Q007-hearing-loop", "Q-007 excludes a hearing loop while a hearing-loop response is needed; conflict applies only if no adequate alternative is provided.",
        ["obs-quote-q-007", "obs-attendee-sig-009"], basis="unresolved-information",
        dependencies=["fact-quote-Q-007", "hc-response-SIG-009"],
        conflict_kind="conditional", applies_if="Q-007 proposed without adequate alternative hearing-loop response", resolution="unresolved")
    # A planned-allocation variance is not automatically an approval-limit breach.
    budgets = {f["values"]["category"]: f for f in tables["budget-allocations"]}
    for quote in tables["vendor-register"]:
        v = quote["values"];budget = budgets[v["category"]]
        if Decimal(v["quote_amount_twd"]) > Decimal(budget["values"]["planned_amount_twd"]):
            add("conflicts", "conflict-allocation-" + v["quote_id"],
                "This quote exceeds its category's planned allocation; that alone does not establish an approval-limit breach or infeasibility.",
                quote["evidence_ids"] + budget["evidence_ids"], basis="unresolved-information",
                dependencies=[quote["id"], budget["id"]], applies_if="quote-proposed",
                conflict_kind="potential-allocation-variance", resolution="unresolved")
    records = [r for category in (*CATEGORIES, "source_facts", "approval_requirements") for r in state[category]]
    identifiers = [r["id"] for r in records]
    if len(identifiers) != len(set(identifiers)) or set(identifiers) & upstream_ids:
        raise ValueError("Duplicate or reused constraint ID")
    for record in records:
        if not record["evidence_ids"] or not set(record["evidence_ids"]) <= upstream_ids:
            raise ValueError("Constraint evidence must resolve to Stage 2 produced records")
        if not set(record["depends_on_record_ids"]) <= set(identifiers):
            raise ValueError("Constraint dependency does not resolve")
    validate_dependencies(records)
    for area, prefix in [("budget", "hc-budget"), ("attendance", "hc-response"), ("calendar", "hc-CAL"),
                         ("accessibility", "hc-accessibility"), ("vendor", "hc-quote"), ("approvals", "gate-")]:
        coverage[area] = [r["id"] for r in records if r["id"].startswith(prefix)]
    state.update(business_clock=upstream["state"]["business_clock"],
                 business_timezone=upstream["state"]["business_timezone"], output_status="draft",
                 audience="internal-evidence-review", coverage=coverage)
    return {"run_id": upstream["run_id"], "predecessor": {
        "snapshot_id": upstream["snapshot_id"], "path": PREDECESSOR_PATH, "sha256": PREDECESSOR_HASH},
        "consumed_record_ids": sorted({eid for r in records for eid in r["evidence_ids"]}),
        "produced_record_ids": identifiers, "status": "partial", "state": state,
        "unresolved": deepcopy(state["unknowns"] + state["conflicts"]), "decisions": []}


def build_snapshot(root: Path) -> dict:
    """Build and validate in memory; never write a project deliverable."""
    from event_coordination.validation import validate_snapshot
    result = {"schema_version": "event-coordination-stage-snapshot/2", "snapshot_id": str(uuid4()),
              "stage": "constraint-model", "sequence": 3,
              "created_at": datetime.now(timezone.utc).isoformat(), **_inputs(root)}
    validate_snapshot(result, root)
    return result


def validate_stage3(snapshot: dict, root: Path) -> None:
    from jsonschema import Draft202012Validator, FormatChecker
    expected = _inputs(root)
    for key, value in expected.items():
        if snapshot.get(key) != value:
            raise ValueError(f"Stage 3 {key} differs from preserved source constraints")
    if snapshot["snapshot_id"] == snapshot["predecessor"]["snapshot_id"]:
        raise ValueError("Stage 3 requires a distinct snapshot ID")
    schema = json.loads((root / "snapshot.schema.json").read_bytes())
    validator = Draft202012Validator({"$ref": "#/$defs/record", "$defs": schema["$defs"]}, format_checker=FormatChecker())
    for category in (*CATEGORIES, "source_facts", "approval_requirements"):
        for record in snapshot["state"][category]:
            validator.validate(record)


def write_snapshot(root: Path) -> tuple[Path, str]:
    """Exclusive writer; use only after explicit generation authorization."""
    target = root / OUTPUT
    if target.exists():
        raise FileExistsError(target)
    snapshot = build_snapshot(root)
    content = (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(content)
    saved = target.read_bytes()
    if saved != content:
        raise ValueError("Saved Stage 3 bytes changed")
    from event_coordination.validation import validate_snapshot
    validate_snapshot(json.loads(saved), root)
    return target, hash_bytes(saved)
