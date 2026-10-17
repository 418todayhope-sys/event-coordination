"""Stage 6: scoped evidence checks, proposed schedules and derived classifications.

No source retrieval, recommendation, granted approval or external action.
"""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import re
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from event_coordination.sources import hash_bytes
from event_coordination.stages.options import OUTPUT as PREDECESSOR_PATH

PREDECESSOR_HASH = "sha256:e0454834f384615926edbf2cc8130ea4c0f0a3ae1e8c942a8010f9fad92dc65d"
OUTPUT = "deliverables/snapshots/06-feasibility-testing.json"
OUTCOMES = {"pass", "fail", "conditional", "unknown", "not-applicable"}
RECORD_ARRAYS = ("option_results", "checks", "schedule_witnesses", "assessment_policy",
                 "retained_early_screening", "screening_checks", "approval_requirements", "unresolved_conditions")


def aggregate(checks: list[dict]) -> str:
    """Classify applicable hard checks without converting authorization to feasibility."""
    if any(type(c["hard_requirement"]) is not bool for c in checks):
        raise ValueError("Hard-requirement applicability must be Boolean")
    if any(c["outcome"] not in OUTCOMES for c in checks):
        raise ValueError("Unknown check outcome")
    applicable = [c["outcome"] for c in checks if c["hard_requirement"] and c["outcome"] != "not-applicable"]
    if not applicable:
        raise ValueError("No applicable hard checks")
    for outcome, result in [("fail", "infeasible"), ("unknown", "unverified"), ("conditional", "conditional")]:
        if outcome in applicable:
            return result
    return "feasible"


def capacity_outcome(capacity, demand) -> str:
    if capacity is None or demand is None:
        return "unknown"
    capacity, demand = Decimal(capacity), Decimal(demand)
    if any(not v.is_finite() or v < 0 for v in (capacity, demand)):
        raise ValueError("Capacity and demand must be finite nonnegative values")
    return "pass" if capacity >= demand else "fail"


def quote_outcome(values: dict, event_date: str, clock: str) -> str:
    """A date-only expiry cannot establish its cutoff on the expiry day."""
    instant = datetime.fromisoformat(clock)
    if instant.utcoffset() is None:
        raise ValueError("Business clock must be timezone aware")
    today = instant.astimezone(ZoneInfo("Asia/Taipei")).date()
    available = values.get("available_date")
    expiry = date.fromisoformat(values["valid_until"]) if values.get("valid_until") else None
    if (available is not None and available != event_date) or (expiry is not None and expiry < today):
        return "fail"
    if available is None or expiry is None:
        return "unknown"
    if expiry == today:
        return "unknown"
    if values.get("status") == "conditional":
        return "conditional"
    return "pass" if values.get("status") in ("available", "held") else "unknown"


def reconstruct_costs(quote_records: dict, quote_ids: list[str], allowances: dict) -> dict:
    """Use source_fact values, not copied candidate totals or category subtotals."""
    if len(quote_ids) != len(set(quote_ids)):
        raise ValueError("Duplicate quoted service")
    by_category = {}
    for qid in quote_ids:
        v = quote_records[qid]["source_fact"]["values"]
        amount = Decimal(v["quote_amount_twd"])
        if not amount.is_finite() or amount < 0:
            raise ValueError("Invalid quoted amount")
        by_category[v["category"]] = by_category.get(v["category"], Decimal(0)) + amount
    subtotal = sum(by_category.values(), Decimal(0))
    allowance_values = {c: Decimal(v) for c, v in allowances.items()}
    if set(by_category) & set(allowance_values):
        raise ValueError("Allowance duplicates a quoted category")
    if any(not v.is_finite() or v < 0 for v in allowance_values.values()):
        raise ValueError("Invalid allowance")
    return {"quoted_by_category": {c: str(v) for c, v in by_category.items()},
            "quoted_subtotal": str(subtotal), "retained_allowances": deepcopy(allowances),
            "planning_total": str(subtotal + sum(allowance_values.values(), Decimal(0)))}



def validate_assessment_types(value, expected, path="snapshot") -> None:
    """Type-strict supplemental validation; Python equality conflates bool and int.

    The expected structure is reconstructed from verified evidence. Recursing also
    validates additional local assessment fields without changing the public schema.
    """
    if type(value) is not type(expected):
        raise ValueError(f"Stage 6 type mismatch at {path}")
    if isinstance(expected, dict):
        if value.keys() != expected.keys():
            raise ValueError(f"Stage 6 structure mismatch at {path}")
        for key in expected:
            validate_assessment_types(value[key], expected[key], path + "." + key)
    elif isinstance(expected, list):
        if len(value) != len(expected):
            raise ValueError(f"Stage 6 list length mismatch at {path}")
        for n, (actual, wanted) in enumerate(zip(value, expected, strict=True)):
            validate_assessment_types(actual, wanted, f"{path}[{n}]")


def evaluate_quote_scope(values: dict, context: dict) -> dict:
    """Evaluate reviewed quote inclusions/exclusions and evidenced prerequisites.

    Availability/status is deliberately not consulted. Text rules target disclosed
    offers; unfamiliar wording yields unknown rather than inferred coverage.
    Context values must be actual booleans/None derived from scoped source records.
    Readiness and date/expiry remain separate checks.
    """
    if any(v is not None and type(v) is not bool for v in context.values()):
        raise ValueError("Scope confirmation must be Boolean or unknown")
    qid = values["quote_id"]
    scope = values.get("option", "").casefold()
    notes = values.get("notes", "").casefold()
    assessments = []
    def inclusion(requirement, positive, exclusion=None):
        negative = exclusion is not None and re.search(exclusion, scope + "; " + notes) is not None
        outcome = "fail" if negative else "pass" if positive else "unknown"
        assessments.append({"requirement": requirement, "outcome": outcome,
                            "basis": "quote-inclusion-or-exclusion", "explicit_exclusion": negative})
    def prerequisite(requirement, key):
        value = context.get(key)
        outcome = "pass" if value is True else "fail" if value is False else "conditional"
        assessments.append({"requirement": requirement, "outcome": outcome,
                            "basis": "scoped-source-prerequisite", "context_key": key})
    if qid in ("Q-001", "Q-002"):
        inclusion("programme-and-quiet-room-package", "4f plenary hall" in scope and "v.i.p. room" in scope,
                  r"(?:no|without|excludes)\s+(?:quiet|v\.i\.p\.) room")
        prerequisite("venue-room-allocation", "venue_allocation")
    elif qid in ("Q-003", "Q-004"):
        inclusion("lunch-and-two-breaks", "lunch and two breaks" in scope,
                  r"(?:no|without|excludes)\s+(?:lunch|breaks)")
        prerequisite("dietary-and-allergy-coordination", "dietary_response")
        if qid == "Q-004":
            inclusion("named-contact-process-disclosed", "allergy process requires named contacts" in notes)
            prerequisite("Operations-held-allergy-contacts", "allergy_contacts")
    elif qid == "Q-005":
        inclusion("live-captions", "live captions" in scope,
                  r"(?:no|without|excludes)\s+(?:live )?captions")
        inclusion("transcript", "transcript" in scope, r"(?:no|without|excludes)\s+transcript")
        inclusion("two-captioners", "two captioners included" in notes, r"(?:no|without|excludes)\s+captioners")
        prerequisite("caption-adequacy-for-case", "caption_adequacy")
    elif qid in ("Q-006", "Q-007"):
        inclusion("AV", "av package" in scope, r"(?:no|without|excludes)\s+av")
        inclusion("hearing-loop", "with hearing loop" in scope,
                  r"(?:no|without|excludes)\s+(?:a )?hearing loop")
        prerequisite("hearing-loop-adequacy-for-case", "loop_adequacy")
    elif qid == "Q-008":
        inclusion("livestream-add-on", "livestream add-on" in scope)
        prerequisite("network-test", "network_test")
        prerequisite("venue-confirmation-for-streaming", "streaming_venue_confirmation")
    elif qid == "Q-009":
        inclusion("four-security-staff", "four staff" in scope)
        inclusion("first-aid-lead", "includes first aid lead" in notes,
                  r"(?:no|without|excludes)\s+first aid")
    elif qid == "Q-010":
        inclusion("quiet-room-staffing", "quiet room staffing" in scope,
                  r"(?:no|without|excludes)\s+(?:quiet room )?staffing")
        inclusion("room-supply-condition-disclosed", "room itself supplied by venue" in notes)
        prerequisite("venue-supplies-quiet-room", "quiet_room_available")
    else:
        assessments.append({"requirement": "supported-service-scope", "outcome": "unknown", "basis": "unrecognized-offer"})
    outcomes = [r["outcome"] for r in assessments]
    outcome = next((o for o in ("fail", "unknown", "conditional") if o in outcomes), "pass")
    return {"outcome": outcome, "assessments": assessments, "source_scope": values.get("option"),
            "source_notes": values.get("notes"), "prerequisite_context": deepcopy(context),
            "availability_assessed_separately": True, "readiness_assessed_separately": True}


def _aware(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("Schedule timestamp lacks timezone")
    local = result.astimezone(ZoneInfo("Asia/Taipei"))
    if result.utcoffset() != local.utcoffset():
        raise ValueError("Schedule timestamp must use Asia/Taipei offset")
    return result


def build_witness(name: str, event_date: str, roster: dict, calendar: dict, windows: dict) -> dict:
    """Create a proposed witness; break/order choices are not source observations."""
    tz = ZoneInfo("Asia/Taipei")
    def at(t):
        return datetime.fromisoformat(event_date + "T" + t).replace(tzinfo=tz)
    intervals = []
    def interval(identifier, kind, start, end, basis="planning-choice", lane="programme"):
        intervals.append({"id": f"witness-{name}-{identifier}", "kind": kind, "lane": lane,
                          "start_at": start.isoformat(), "end_at": end.isoformat(), "basis": basis})
    interval("setup", "setup-envelope", at(windows["setup_start"]), at(windows["setup_end"]), "source-statement", "venue-access")
    start = _aware(calendar["CAL-001"]["start_at"])
    keynote_start = _aware(calendar["CAL-004"]["start_at"])
    keynote_end = _aware(calendar["CAL-004"]["end_at"])
    interval("opening", "opening", start, keynote_start)
    interval("keynote", "keynote", keynote_start, keynote_end, "source-statement")
    current = keynote_end
    interval("break-1", "break", current, current + timedelta(minutes=15))
    current += timedelta(minutes=15)
    for n, demo_id in enumerate(roster["demo_ids"]):
        if n == 6:
            interval("lunch", "lunch", current, current + timedelta(minutes=60))
            current += timedelta(minutes=60)
        end = current + timedelta(minutes=float(Decimal(roster["presentation_minutes"])))
        interval(demo_id, "demo", current, end, "source-duration; proposed-order")
        intervals[-1]["demo_id"] = demo_id
        current = end
        end = current + timedelta(minutes=float(Decimal(roster["changeover_minutes"])))
        interval(demo_id + "-changeover", "changeover", current, end, "source-duration; proposed-order")
        intervals[-1]["demo_id"] = demo_id
        current = end
    interval("break-2", "break", current, current + timedelta(minutes=15))
    current += timedelta(minutes=15)
    interval("flex", "flexible-programme-closing-allowance", current, _aware(calendar["CAL-001"]["end_at"]))
    interval("teardown", "teardown-envelope", at(windows["teardown_start"]), at(windows["teardown_end"]), "source-statement", "venue-access")
    return {"id": "witness-oct17-" + name, "summary": "Proposed resource-aware schedule, not an approved run of show or executed activity.",
            "evidence_ids": ["option-oct17-" + name, "option-baseline-context"],
            "basis": "planning-choice", "timezone": "Asia/Taipei", "event_date": event_date,
            "intervals": intervals, "readiness_at": at(windows["setup_end"]).isoformat(),
            "individual_vendor_durations": None, "extra_mandatory_buffer": None}


def validate_witness(witness: dict, roster: dict, calendar: dict, windows: dict) -> None:
    """Reject duplicate/omitted activities, overlaps, duration changes and window overruns."""
    if witness["timezone"] != "Asia/Taipei":
        raise ValueError("Incorrect witness timezone")
    intervals = witness["intervals"]
    for kind, count in [("setup-envelope", 1), ("opening", 1), ("keynote", 1), ("break", 2),
                        ("lunch", 1), ("flexible-programme-closing-allowance", 1), ("teardown-envelope", 1)]:
        if sum(i["kind"] == kind for i in intervals) != count:
            raise ValueError("Missing or duplicate required witness element")
    if len({i["id"] for i in intervals}) != len(intervals):
        raise ValueError("Duplicate schedule interval")
    lanes = {}
    for i in intervals:
        start, end = _aware(i["start_at"]), _aware(i["end_at"])
        if start >= end or start.date().isoformat() != witness["event_date"] or end.date() != start.date():
            raise ValueError("Invalid schedule interval/date")
        expected_lane = "venue-access" if i["kind"] in ("setup-envelope", "teardown-envelope") else "programme"
        if i["lane"] != expected_lane:
            raise ValueError("Activity assigned to an unsupported resource lane")
        lanes.setdefault(i["lane"], []).append((start, end))
        if i["lane"] == "programme" and (start < _aware(calendar["CAL-001"]["start_at"]) or end > _aware(calendar["CAL-001"]["end_at"])):
            raise ValueError("Programme exceeds event window")
    for spans in lanes.values():
        ordered = sorted(spans)
        if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
            raise ValueError("Resource overlap")
    for kind, minutes in [("demo", roster["presentation_minutes"]), ("changeover", roster["changeover_minutes"])]:
        items = [i for i in intervals if i["kind"] == kind]
        if sorted(i.get("demo_id") for i in items) != sorted(roster["demo_ids"]):
            raise ValueError("Missing or duplicated programme item")
        for i in items:
            duration = Decimal(str((_aware(i["end_at"]) - _aware(i["start_at"])).total_seconds())) / 60
            if duration != Decimal(minutes):
                raise ValueError("Programme duration differs from source")
    for demo in [i for i in intervals if i["kind"] == "demo"]:
        change = next(i for i in intervals if i["kind"] == "changeover" and i["demo_id"] == demo["demo_id"])
        if _aware(demo["end_at"]) != _aware(change["start_at"]):
            raise ValueError("Changeover must immediately follow its demo")
    keynote, = [i for i in intervals if i["kind"] == "keynote"]
    if keynote["start_at"] != calendar["CAL-004"]["start_at"] or keynote["end_at"] != calendar["CAL-004"]["end_at"]:
        raise ValueError("Keynote differs from source window")
    for kind, first, last in [("setup-envelope", "setup_start", "setup_end"), ("teardown-envelope", "teardown_start", "teardown_end")]:
        item, = [i for i in intervals if i["kind"] == kind]
        expected = [datetime.fromisoformat(witness["event_date"] + "T" + windows[k]).replace(tzinfo=ZoneInfo("Asia/Taipei")) for k in (first, last)]
        if [_aware(item["start_at"]), _aware(item["end_at"])] != expected:
            raise ValueError("Access envelope differs from source")
        hold_start, hold_end = (_aware(calendar["CAL-003"][k]) for k in ("start_at", "end_at"))
        if expected[0] < hold_start or expected[1] > hold_end:
            raise ValueError("Access exceeds venue hold")
    opening = next(i for i in intervals if i["kind"] == "opening")
    setup = next(i for i in intervals if i["kind"] == "setup-envelope")
    event_start, event_end = (_aware(calendar["CAL-001"][k]) for k in ("start_at", "end_at"))
    if _aware(opening["start_at"]) != event_start:
        raise ValueError("Opening must start at the source event opening time")
    if _aware(opening["end_at"]) != _aware(keynote["start_at"]):
        raise ValueError("Proposed opening must meet the keynote boundary")
    if _aware(setup["end_at"]) != _aware(witness["readiness_at"]) or _aware(witness["readiness_at"]) != event_start:
        raise ValueError("Setup completion, readiness and opening must coincide")
    programme_spans = sorted(lanes["programme"])
    if programme_spans[0][0] != event_start or programme_spans[-1][1] != event_end:
        raise ValueError("Witness must cover the programme boundaries")
    if any(a[1] != b[0] for a, b in zip(programme_spans, programme_spans[1:])):
        raise ValueError("Unaccounted gap in proposed programme witness")
    teardown = next(i for i in intervals if i["kind"] == "teardown-envelope")
    if _aware(teardown["start_at"]) != event_end:
        raise ValueError("Teardown must follow the programme boundary")
    if (_aware(teardown["start_at"]) < _aware(calendar["CAL-008"]["start_at"])
            or _aware(teardown["end_at"]) > _aware(calendar["CAL-008"]["end_at"])):
        raise ValueError("Teardown exceeds calendar clearance window")
    if _aware(witness["readiness_at"]) != _aware(calendar["CAL-001"]["start_at"]):
        raise ValueError("Readiness must coincide with opening")


def _inputs(root: Path) -> dict:
    from event_coordination.validation import validate_snapshot
    content = (root / PREDECESSOR_PATH).read_bytes()
    if hash_bytes(content) != PREDECESSOR_HASH:
        raise ValueError("Stage 5 predecessor hash differs from approved snapshot")
    upstream = json.loads(content)
    validate_snapshot(upstream, root)
    state = {key: [] for key in RECORD_ARRAYS}
    baseline_context = next(r for r in upstream["state"]["comparison_basis"] if r["id"] == "option-baseline-context")
    baseline = {r["id"]: r for r in baseline_context["source_records"]}
    quotes = {r["values"]["quote_id"]: r for r in upstream["state"]["quote_evidence"]}
    upstream_ids = set(upstream["produced_record_ids"])
    consumed = set()
    gates = {r["id"]: r for r in upstream["state"]["approval_requirements"]}
    inherited = deepcopy(upstream["unresolved"])
    new_conditions = []
    def values(identifier):
        return baseline[identifier]["values"]
    def original(identifier):
        return next(r for b in baseline.values() for r in b["source_records"] if r["id"] == identifier)
    def confirmed(identifier, phrases):
        record = original(identifier)
        text = " ".join(s.get("excerpt", "") for s in record.get("source_values", []))
        return all(p in text for p in phrases)
    def resolution_details(suffix, option):
        inherited_index = {r["id"]: r for r in inherited}
        owner, deadline = None, None
        owner_roles = []
        evidence = []
        if suffix.startswith("allocation-policy-"):
            category = suffix.removeprefix("allocation-policy-")
            b = baseline["baseline-budget-category-" + category]
            owner = b["values"]["owner"]
            required = f"Document the category-owner determination for {category}: whether the proposed allocation variance is permitted, its amount and plan revision, and any approved transfer or revised allocation."
            links = ["unknown-budget-reallocation"]
            evidence = [{"parent_record_id": "option-baseline-context", "nested_record_id": b["id"]}]
        elif suffix == "walkthrough-prerequisite":
            required = "Provide dated venue-confirmation evidence covering this date/room and the accessibility walkthrough, before the source walkthrough start. A description of the gate alone is insufficient."
            links = [r["id"] for r in inherited if "CAL-006 explicitly requires venue confirmation" in r["summary"]]
            owner = gates["gate-venue-confirmation"]["owner"]
            deadline = {"before": values("baseline-schedule-CAL-006")["start_at"], "timezone": "Asia/Taipei"}
            evidence = [{"parent_record_id": "option-baseline-context", "nested_record_id": "baseline-schedule-CAL-006"}, {"record_id": "gate-venue-confirmation"}]
        elif suffix == "live-verification":
            required = "For real deployment, obtain current venue confirmation or inspection of elevator operation, unobstructed step-free routes, accessible restrooms/seating and room configuration, plus service-provider confirmation of captions, loop and quiet-room staffing. Preserve dates, scope and source locators."
            links = ["unknown-live-accessibility"]
            evidence = [{"parent_record_id": "option-baseline-context", "nested_record_id": "baseline-accessibility-verification"}]
        elif suffix == "authorization":
            required = "Record genuine decisions for the applicable gates, identifying authorized actor/role, plan revision, date/room or category amount, timestamp, outcome and conditions. Programme review is required only for roster/duration changes; external-action permission must cover the specific action."
            links = ["unknown-approvals"]
            owner_roles = [{"role": g["owner"], "applies_if": g["applies_if"]} for g in gates.values() if g["owner"] is not None]
            evidence = [{"record_id": g} for g in gates]
        elif suffix.startswith("scope-"):
            qid = suffix.removeprefix("scope-")
            required = f"Obtain a dated, source-located clarification for {qid} establishing every unknown inclusion and satisfying each unresolved prerequisite recorded in the scope assessment; retain its applicable date, service scope and version."
            links = []
            evidence = [{"record_id": "option-source-" + qid}]
        else:
            required = f"Supply located evidence for the recorded inputs and unmet requirement {suffix} for {option['id']}; rerun the affected check without treating missing values as satisfied."
            links = []
        if not set(links) <= set(inherited_index):
            raise ValueError("Resolution link lacks inherited evidence")
        return {"required_evidence": required, "related_inherited_unresolved_ids": links,
                "owner": owner, "owner_roles": owner_roles, "resolution_deadline": deadline, "resolution_basis": evidence}

    def add(category, identifier, summary, evidence, **extra):
        if not evidence or not set(evidence) <= upstream_ids:
            raise ValueError("Feasibility evidence must resolve to Stage 5 produced records")
        consumed.update(evidence)
        r = {"id": identifier, "summary": summary, "evidence_ids": list(dict.fromkeys(evidence)), **extra}
        state[category].append(r)
        return r
    add("assessment_policy", "policy-stage6-aggregation", "Applicable technical hard checks: fail > unknown > conditional > pass; authorization is separate.",
        ["option-policy-supported-alternatives", "option-baseline-context"], basis="planning-choice",
        assessment_scope="fictional-exercise", precedence=["fail", "unknown", "conditional", "pass"],
        live_operational_verification="not-established", authorization_in_technical_aggregation=False)
    calendar = {f"CAL-{n:03}": values(f"baseline-schedule-CAL-{n:03}") for n in range(1, 9)}
    roster = values("baseline-programme-demos")
    windows = values("baseline-schedule-access-windows")
    allowances = next(r for r in upstream["state"]["comparison_basis"] if r["id"] == "option-policy-retained-allowances")["values"]
    clock = upstream["state"]["business_clock"]
    for option in upstream["state"]["options"]:
        name = option["id"].removeprefix("option-oct17-")
        checks = []
        base_evidence = [option["id"], "option-baseline-context"]
        def check(suffix, outcome, rationale, *, hard=True, basis="derived", inputs=None, evidence=(), derivation=None, nested=()):
            if outcome not in OUTCOMES:
                raise ValueError("Invalid check outcome")
            c = add("checks", f"check-oct17-{name}-{suffix}", rationale, base_evidence + list(evidence),
                    candidate_id=option["id"], requirement=suffix, assessment_scope="fictional-exercise",
                    applicability="this-candidate", hard_requirement=hard, basis=basis, inputs=deepcopy(inputs or {}),
                    outcome=outcome, rationale=rationale, derivation=derivation, condition_ids=[],
                    nested_source_references=[{"parent_record_id": "option-baseline-context", "nested_record_id": i} for i in nested],
                    source_limitations=["Local copies remain unverified against online sources.", "Exercise confirmation is not live operational verification."])
            checks.append(c)
            if outcome in ("unknown", "conditional"):
                identifier = "condition-" + c["id"]
                condition = {"id": identifier, "summary": rationale, "evidence_ids": c["evidence_ids"],
                             "affected_candidate_ids": [option["id"]], "affected_check_ids": [c["id"]],
                             "kind": "technical-prerequisite" if hard else "review-or-verification-limitation",
                             "resolution_state": "unresolved", "blocks_technical_assessment": hard,
                             **resolution_details(suffix, option)}
                new_conditions.append(condition)
                c["condition_ids"].append(identifier)
            return c
        qids = option["component_quote_ids"]
        costs = reconstruct_costs(quotes, qids, allowances)
        subtotal, total = Decimal(costs["quoted_subtotal"]), Decimal(costs["planning_total"])
        quote_evidence = ["option-source-" + q for q in qids]
        check("quote-subtotal", "pass" if subtotal == Decimal(option["quoted_subtotal"]) else "fail",
              "Reconstructed quoted subtotal from preserved source_fact amounts.", inputs=costs,
              evidence=quote_evidence, derivation={"operation": "sum", "inputs": [{"record_id": "option-source-" + q, "field": "source_fact.values.quote_amount_twd"} for q in qids]})
        check("planning-total", "pass" if total == Decimal(option["planning_total"]) else "fail",
              "Quoted costs plus retained communications/contingency allowances exactly once.", inputs=costs,
              evidence=["option-policy-retained-allowances"], derivation={"operation": "quoted-subtotal-plus-allowances"})
        ceiling = Decimal(values("baseline-budget-ceiling")["value"])
        check("budget-ceiling", capacity_outcome(ceiling, total), "Compare reconstructed planning cost to overall ceiling.",
              inputs={"planning_total": str(total), "ceiling": str(ceiling), "difference": str(ceiling-total), "unit": "TWD"}, nested=["baseline-budget-ceiling"])
        category_costs = {**costs["quoted_by_category"], **allowances}
        for category, amount in category_costs.items():
            b = values("baseline-budget-category-" + category)
            variance = Decimal(amount) - Decimal(b["planned_amount_twd"])
            check("category-" + category, capacity_outcome(b["approval_limit_twd"], amount),
                  "Compare category amount with approval limit; spending authority remains pending, not inferred.",
                  inputs={"proposed": amount, "allocation": b["planned_amount_twd"], "allocation_variance": str(variance),
                          "approval_limit": b["approval_limit_twd"], "recorded_commitment": b["committed_amount_twd"], "unit": "TWD", "authorization_status": "pending"},
                  nested=["baseline-budget-category-" + category])
            if variance > 0:
                check("allocation-policy-" + category, "unknown", "Positive allocation variance requires review; transfer policy is not established and no fixed-allocation rule is invented.",
                      hard=False, inputs={"variance": str(variance), "unit": "TWD"}, nested=["baseline-budget-category-" + category])
        demand = Decimal(values("baseline-headcount-planning-demand")["value"])
        core = Decimal(values("baseline-headcount-core")["value"])
        forecast = Decimal(values("baseline-headcount-forecast")["value"])
        check("attendance-basis", "pass" if core + forecast == demand and values("baseline-headcount-overlap")["additional_people"] == 0 else "fail",
              "Registered/required cohorts plus uncertain forecast reconcile; needs and demo slots add no people.",
              inputs={"registered": values("baseline-headcount-registered"), "required_onsite": values("baseline-headcount-required-onsite"), "forecast": values("baseline-headcount-forecast"), "planning_demand": str(demand), "unit": "people", "success_target_is_capacity_discount": False})
        rooms = values("baseline-accessibility-space-limits")
        cater_q = next(q for q in qids if quotes[q]["values"]["category"] == "catering")
        capacities = [("audience", rooms["audience_places"], str(demand)),
                      ("catering", quotes[cater_q]["values"]["capacity"], str(demand)),
                      ("venue-quote", quotes["Q-001"]["values"]["capacity"] if "Q-001" in qids else None, str(demand)),
                      ("caption-service", quotes["Q-005"]["values"]["capacity"] if "Q-005" in qids else None, str(demand)),
                      ("av-service", quotes["Q-006"]["values"]["capacity"] if "Q-006" in qids else None, str(demand)),
                      ("security-service", quotes["Q-009"]["values"]["capacity"] if "Q-009" in qids else None, str(demand)),
                      ("wheelchair", rooms["wheelchair_spaces_included"], values("baseline-needs-SIG-006")["value"]),
                      ("quiet-room", rooms["quiet_room_max_people"], values("baseline-needs-SIG-010")["value"]),
                      ("quiet-staffing", quotes["Q-010"]["values"]["capacity"] if "Q-010" in qids else None, values("baseline-needs-SIG-010")["value"])]
        for service, cap, needed in capacities:
            check("capacity-" + service, capacity_outcome(cap, needed), "Service-specific capacity comparison; capacities and overlapping needs are not additive.",
                  inputs={"service": service, "capacity": cap, "applicable_demand": needed}, evidence=quote_evidence)
        check("capacity-companions", "pass" if rooms["companions"] == "ordinary places" else "unknown",
              "Companions use ordinary places within the reconciled audience demand.", inputs={"companion_signal": values("baseline-needs-SIG-007"), "seating_rule": rooms["companions"]})
        for qid in qids:
            v = quotes[qid]["source_fact"]["values"]
            check("quote-" + qid, quote_outcome(v, option["proposed_event_date"], clock),
                  "Check quote date/status/expiry against the fixed business clock; date-only cutoff remains unspecified.",
                  inputs={"source_values": v, "business_clock": clock, "expiration_cutoff_time": None}, evidence=["option-source-" + qid])
            scope_context = {
                "venue_allocation": confirmed("fact-venue-arrangement", ["4F Plenary Hall", "V.I.P. Room"]),
                "dietary_response": confirmed("fact-base-service-confirmation", ["both catering options", "Operations-coordinated dietary response"]),
                "allergy_contacts": confirmed("fact-base-service-confirmation", ["Named contacts are held by Operations"]),
                "caption_adequacy": confirmed("fact-base-service-confirmation", ["adequate captioning"]),
                "loop_adequacy": confirmed("fact-base-service-confirmation", ["hearing-loop and allergy coordination"]),
                "quiet_room_available": "V.I.P. Room" in rooms["rooms"] and confirmed("fact-venue-arrangement", ["quiet space"]),
                "network_test": None, "streaming_venue_confirmation": None,
            }
            # A missing affirmation is unknown, not evidence of a negative fact.
            scope_context = {key: True if value else None for key, value in scope_context.items()}
            scope_assessment = evaluate_quote_scope(v, scope_context)
            check("scope-" + qid, scope_assessment["outcome"],
                  "Evaluate quote inclusions, explicit exclusions and source-supported prerequisites; availability and opening readiness are tested separately.",
                  basis="derived", inputs=scope_assessment, evidence=["option-source-" + qid],
                  nested=["baseline-accessibility-verification", "baseline-accessibility-space-limits"])
        ready = values("baseline-schedule-readiness")
        base_supported = (set(qids) == {"Q-001", cater_q, "Q-005", "Q-006", "Q-009", "Q-010"}
                          and cater_q in ("Q-003", "Q-004") and ready["applies_on"] == option["proposed_event_date"]
                          and confirmed("fact-base-readiness", ["either Q-003 or Q-004", "ready by 09:30", "18:30"]))
        witness = build_witness(name, option["proposed_event_date"], roster, calendar, windows)
        try:
            validate_witness(witness, roster, calendar, windows)
            schedule_outcome = "pass"
        except ValueError:
            schedule_outcome = "fail"
        state["schedule_witnesses"].append(witness)
        consumed.update(witness["evidence_ids"])
        check("programme", schedule_outcome, "Proposed witness preserves keynote and all twelve ten-minute demos with twelve three-minute changeovers, without lane conflicts.",
              inputs={"witness_id": witness["id"], "demo_minutes": str(Decimal(roster["presentation_minutes"])*len(roster["demo_ids"])),
                      "changeover_minutes": str(Decimal(roster["changeover_minutes"])*len(roster["demo_ids"]))}, basis="derived")
        check("access-windows", "pass" if schedule_outcome == "pass" and base_supported else "unknown",
              "Exercise base-bundle confirmation supports setup/readiness and clearance within source windows; individual vendor durations remain unknown.",
              inputs={"windows": windows, "readiness": ready, "witness_id": witness["id"]}, nested=["baseline-schedule-readiness", "baseline-schedule-access-windows"])
        check("walkthrough-prerequisite", {"pending": "conditional", "approved": "pass", "rejected": "fail"}.get(gates["gate-venue-confirmation"]["status"], "unknown"),
              "Venue confirmation before the accessibility walkthrough remains an operational prerequisite; the gate is not silently resolved.",
              inputs={"gate": deepcopy(gates["gate-venue-confirmation"]), "walkthrough": calendar["CAL-006"]}, evidence=["gate-venue-confirmation"])
        check("rehearsal-preference", "pass", "Preserve soft rehearsal window and remote-backup allowance; no attendance or venue confirmation is inferred.",
              hard=False, basis="source-statement", inputs=calendar["CAL-007"])
        check("decision-deadline", "pass", "Preserve Operations deadline as a review milestone, not an approved decision or scheduled programme activity.",
              hard=False, basis="source-statement", inputs=values("baseline-schedule-operations-deadline"), evidence=["gate-operations"])
        step_free = confirmed("fact-venue-case-confirmation", ["confirms step-free access", "accessible restroom"])
        service_confirmed = confirmed("fact-base-service-confirmation", ["adequate captioning, hearing-loop and allergy coordination", "both catering options"])
        features = {
            "step-free-programme": step_free,
            "step-free-restrooms": step_free,
            "wheelchair-seating": capacity_outcome(rooms["wheelchair_spaces_included"], values("baseline-needs-SIG-006")["value"]) == "pass",
            "live-captions": "Q-005" in qids and service_confirmed and base_supported,
            "hearing-loop": "Q-006" in qids and service_confirmed and base_supported,
            "quiet-room-availability": "V.I.P. Room" in rooms["rooms"] and confirmed("fact-venue-arrangement", ["quiet space"]),
            "quiet-room-staffing": "Q-010" in qids and base_supported,
        }
        for feature, supported in features.items():
            check("accessibility-" + feature, "pass" if supported else "unknown",
                  "Assess the individual requirement using exercise-scoped service/venue evidence; no live provision is asserted.",
                  basis="source-statement", inputs={"feature": feature, "exercise_support": supported, "live_provision_verified": None,
                         "relevant_needs": {k: values("baseline-needs-" + k) for k in ("SIG-006", "SIG-007", "SIG-008", "SIG-009", "SIG-010")}},
                  nested=["baseline-accessibility-verification", "baseline-accessibility-space-limits"], evidence=quote_evidence)
        for need in ("SIG-011", "SIG-012", "SIG-013"):
            supported = confirmed("fact-base-service-confirmation", ["Operations-coordinated dietary response", "Named contacts are held by Operations"])
            check("dietary-" + need, "pass" if supported and cater_q in ("Q-003", "Q-004") else "unknown",
                  "Exercise record supplies dietary/allergy coordination, not invented contact identities or completed attendee fulfillment.",
                  basis="source-statement", inputs={"need": values("baseline-needs-" + need), "contacts": "held-by-Operations-in-exercise-record", "individual_details": "not-reproduced"},
                  nested=["baseline-accessibility-verification", "baseline-needs-" + need], evidence=["option-source-" + cater_q])
        check("safety", "pass" if "Q-009" in qids and base_supported and "first aid lead" in quotes["Q-009"]["values"]["notes"] else "unknown",
              "Assess quoted security/first-aid scope and exercise opening readiness, without inventing a safety certification or technical standard.",
              basis="source-statement", inputs={"security_quote": quotes["Q-009"]["values"], "base_readiness_supported": base_supported}, evidence=["option-source-Q-009"], nested=["baseline-safety-coverage"])
        check("provenance-integrity", "pass", "Recursive validation verified source bytes, ancestor ownership and predecessor chain; integrity does not authenticate online origin.",
              basis="source-statement", inputs={"ancestor_reference_ids": [r["id"] for r in upstream["state"]["ancestor_references"]]}, evidence=[r["id"] for r in upstream["state"]["ancestor_references"]])
        check("live-verification", "unknown", "Current real-world accessibility/service operation is not independently verified; this is outside the exercise technical scope.",
              hard=False, basis="source-statement", nested=["baseline-accessibility-verification"])
        check("livestream-prerequisites", "not-applicable" if "Q-008" not in qids else "conditional",
              "Livestream is absent from this base package; its unresolved tests remain on retained alternatives.", inputs={"quote_proposed": "Q-008" in qids})
        check("authorization", "conditional", "Operations, spending and external-action authorizations remain pending; Programme gate applies only to roster/duration changes.",
              hard=False, basis="stakeholder-rule", inputs={"gate_statuses": {k: g["status"] for k, g in gates.items()}}, evidence=list(gates))
        result = aggregate(checks)
        add("option_results", "result-oct17-" + name, "Evidence-derived exercise assessment; not a recommendation, booking or authorization.",
            base_evidence + quote_evidence, candidate_id=option["id"], assessment_scope="fictional-exercise", feasibility=result,
            classification_rationale="Computed from applicable hard checks using fail > unknown > conditional > pass.",
            check_ids=[c["id"] for c in checks], blocking_check_ids=[c["id"] for c in checks if c["hard_requirement"] and c["outcome"] in ("fail", "unknown", "conditional")],
            applicable_condition_ids=[i for c in checks for i in c["condition_ids"]], reconstructed_costs=costs,
            schedule_witness_id=witness["id"], approval_requirement_ids=list(gates), authorization_status="pending", selected=False)
    state["retained_early_screening"] = deepcopy(upstream["state"]["rejected_early"])
    for screen in upstream["state"]["rejected_early"]:
        evidence = [screen["id"], "option-baseline-context"]
        details = {"scope": screen["screening_scope"], "conditions": deepcopy(screen.get("conditions", []))}
        if screen["id"].endswith("-stream"):
            costs = reconstruct_costs(quotes, screen["candidate_composition"], allowances)
            ceiling = Decimal(values("baseline-budget-ceiling")["value"])
            outcome = capacity_outcome(ceiling, costs["planning_total"])
            details.update(costs, ceiling=str(ceiling), operation="sum-quoted-components-plus-retained-allowances")
            evidence += ["option-source-" + q for q in screen["candidate_composition"]]
        elif screen["id"] == "screen-oct17-q007-no-loop":
            outcome = "fail" if "No hearing loop included" in quotes["Q-007"]["values"]["notes"] else "unknown"
            details["coverage_gap"] = "Q-007 alone excludes loop; adequate replacement response is not evidenced."
            evidence += ["option-source-Q-007"]
        else:
            outcome = "fail" if "Keynote unavailable on fallback date" in calendar["CAL-004"]["notes"] else "unknown"
            details["missing_date_compatible_services"] = deepcopy(screen["missing_service_quotes"])
            details["missing_evidence_is_not_a_fabricated_offer"] = True
            evidence += ["option-source-Q-002"]
        add("screening_checks", "assessment-" + screen["id"], "Scoped screening audit; original alternative and unresolved dependencies remain intact.",
            evidence, source_screening_id=screen["id"], outcome=outcome, inputs=details,
            assessment_scope="fictional-exercise; alternative-as-described", classification_scope="screening-only-not-a-full-option-result")
    state["approval_requirements"] = deepcopy(upstream["state"]["approval_requirements"])
    state["unresolved_conditions"] = inherited + new_conditions
    consumed.update(r["id"] for r in inherited + state["retained_early_screening"] + state["approval_requirements"])
    ids = [r["id"] for key in RECORD_ARRAYS for r in state[key]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate feasibility record IDs")
    state.update(business_clock=clock, business_timezone=upstream["state"]["business_timezone"], output_status="draft", audience="internal-evidence-review",
                 inherited_unresolved_ids=[r["id"] for r in inherited], source_snapshot=deepcopy(upstream["predecessor"]))
    return {"run_id": upstream["run_id"], "predecessor": {"snapshot_id": upstream["snapshot_id"], "path": PREDECESSOR_PATH, "sha256": PREDECESSOR_HASH},
            "consumed_record_ids": sorted(consumed), "produced_record_ids": ids, "state": state,
            "status": "partial", "unresolved": deepcopy(state["unresolved_conditions"]), "decisions": []}


def build_snapshot(root: Path) -> dict:
    """Build and validate only in memory."""
    from event_coordination.validation import validate_snapshot
    result = {"schema_version": "event-coordination-stage-snapshot/2", "snapshot_id": str(uuid4()), "stage": "feasibility-testing", "sequence": 6,
              "created_at": datetime.now(timezone.utc).isoformat(), **_inputs(root)}
    validate_snapshot(result, root)
    return result


def validate_stage6(snapshot: dict, root: Path) -> None:
    from jsonschema import Draft202012Validator, FormatChecker
    expected = _inputs(root)
    for key, value in expected.items():
        validate_assessment_types(snapshot.get(key), value, key)
        if snapshot.get(key) != value:
            raise ValueError(f"Stage 6 {key} differs from preserved feasibility inputs")
    if snapshot["snapshot_id"] == snapshot["predecessor"]["snapshot_id"]:
        raise ValueError("Stage 6 requires a distinct snapshot ID")
    schema = json.loads((root / "snapshot.schema.json").read_bytes())
    validator = Draft202012Validator({"$ref": "#/$defs/record", "$defs": schema["$defs"]}, format_checker=FormatChecker())
    for key in RECORD_ARRAYS:
        for record in snapshot["state"][key]:
            validator.validate(record)


def write_snapshot(root: Path) -> tuple[Path, str]:
    """Exclusive writer, for a separately authorized generation step."""
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
        raise ValueError("Saved Stage 6 bytes changed")
    from event_coordination.validation import validate_snapshot
    validate_snapshot(json.loads(saved), root)
    return target, hash_bytes(saved)
