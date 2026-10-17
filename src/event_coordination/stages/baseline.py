"""Stage 4: traceable draft baselines, without option selection or authorization."""

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from uuid import uuid4

from event_coordination.constraint_sources import validate_dependencies
from event_coordination.sources import hash_bytes
from event_coordination.stages.constraints import OUTPUT as PREDECESSOR_PATH

PREDECESSOR_HASH = "sha256:0b346b83d170f871b4ad22d13c951baabb9a437ecd1beaf3c9e75bee14f3ea37"
OUTPUT = "deliverables/snapshots/04-planning-baseline.json"
CATEGORIES = ("headcount_basis", "schedule_dependencies", "budget_baseline", "accessibility_baseline")
UPSTREAM_CATEGORIES = ("source_facts", "hard_constraints", "preferences", "assumptions",
                       "unknowns", "conflicts", "approval_requirements")


def _inputs(root: Path) -> dict:
    from event_coordination.validation import validate_snapshot

    content = (root / PREDECESSOR_PATH).read_bytes()
    if hash_bytes(content) != PREDECESSOR_HASH:
        raise ValueError("Stage 3 predecessor hash differs from approved snapshot")
    upstream = json.loads(content)
    validate_snapshot(upstream, root)  # Recursively verifies preserved evidence bytes.
    index = {r["id"]: r for category in UPSTREAM_CATEGORIES for r in upstream["state"][category]}
    upstream_ids = set(upstream["produced_record_ids"])
    state = {category: [] for category in CATEGORIES}
    consumed = set()

    def add(category, identifier, summary, evidence, *, values=None, basis="source-statement",
            dependencies=(), **extra):
        if not evidence or not set(evidence) <= upstream_ids:
            raise ValueError("Baseline evidence must reference Stage 3 produced records")
        consumed.update(evidence)
        record = {"id": identifier, "summary": summary, "evidence_ids": list(evidence),
                  "basis": basis, "values": deepcopy(values or {}),
                  "depends_on_record_ids": list(dependencies),
                  "verification": "inherits-upstream-limitations", "fulfillment": "not-evaluated",
                  "source_records": [deepcopy(index[e]) for e in evidence], **extra}
        state[category].append(record)
        return record

    def derived(category, identifier, summary, evidence, value, unit, operation, inputs, dependencies=()):
        return add(category, identifier, summary, evidence, basis="derived", values={"value": str(value)},
                   units={"value": unit}, dependencies=dependencies,
                   derivation={"operation": operation, "inputs": inputs})

    def signal(n):
        return f"fact-signal-SIG-{n:03}"

    def number(identifier, field="value"):
        return Decimal(index[identifier]["values"][field])

    def operands(ids, field="value", coefficient=1):
        return [{"record_id": i, "field": "values." + field, "coefficient": coefficient} for i in ids]

    hc = "headcount_basis"
    groups = [("registered", [signal(1), signal(2)]),
              ("required-onsite", [signal(3), signal(4)]),
              ("core", [signal(n) for n in range(1, 5)])]
    for name, ids in groups:
        derived(hc, "baseline-headcount-" + name, f"Derived {name} population; not actual check-ins.",
                ids, sum(number(i) for i in ids), "people", "weighted-sum", operands(ids))
    add(hc, "baseline-headcount-forecast", "Expected walk-ins remain a forecast, not confirmed attendance.",
        [signal(5), "hc-qualitative-confidence"], values=index[signal(5)]["values"],
        interpretation="forecast-estimate", units={"value": "people"})
    total = sum(number(signal(n)) for n in range(1, 6))
    if total != number("fact-declared-headcount"):
        raise ValueError("Attendee components do not reconcile to declared planning demand")
    derived(hc, "baseline-headcount-planning-demand", "Declared working planning demand including uncertain walk-ins; no final service quantity.",
            [signal(n) for n in range(1, 6)] + ["fact-declared-headcount", "hc-capacity-coverage"],
            total, "people", "weighted-sum", operands([signal(n) for n in range(1, 6)]),
            ["baseline-headcount-core", "baseline-headcount-forecast"])
    add(hc, "baseline-headcount-overlap", "Needs and demo slots add no people; confidence is qualitative.",
        ["hc-nonadditive-needs", "hc-qualitative-confidence", "fact-programme-roster"],
        basis="stakeholder-rule", values={"additional_people": 0})
    add(hc, "baseline-headcount-success-target", "Check-in success target does not discount capacity demand.",
        ["fact-success-criteria", "hc-success-criteria"], values=index["fact-success-criteria"]["values"])

    bc = "budget_baseline"
    ceiling = "fact-budget-total"
    add(bc, "baseline-budget-ceiling", "Overall ceiling, independent of category approval limits.",
        [ceiling, "hc-budget-total"], values=index[ceiling]["values"], units={"value": "TWD"})
    budget_ids = [i for i in index if i.startswith("fact-budget-") and i != ceiling]
    for i in budget_ids:
        category = index[i]["values"]["category"]
        add(bc, "baseline-budget-category-" + category, "Separate source allocation, approval limit and recorded commitment.",
            [i, "hc-budget-authorization-" + category, "unknown-budget-reallocation"],
            values=index[i]["values"], units=index[i]["units"], authorization_status="pending")
    for name, field in [("planned-total", "planned_amount_twd"), ("committed-total", "committed_amount_twd")]:
        derived(bc, "baseline-budget-" + name, "Sum of explicit source amounts; not spending authority.",
                budget_ids, sum(number(i, field) for i in budget_ids), "TWD", "weighted-sum", operands(budget_ids, field))
    for name, field in [("unallocated", "planned_amount_twd"), ("ceiling-less-commitments", "committed_amount_twd")]:
        derived(bc, "baseline-budget-" + name, "Ceiling less recorded amounts; not authorized spending.",
                [ceiling] + budget_ids, number(ceiling) - sum(number(i, field) for i in budget_ids),
                "TWD", "weighted-sum", operands([ceiling]) + operands(budget_ids, field, -1))
    add(bc, "baseline-budget-authorization", "All spending requires category-owner authorization; exceptions cannot exceed the ceiling.",
        ["gate-spending", "hc-draft-boundary", "unknown-approvals"], basis="stakeholder-rule",
        values={"authorization_status": "pending", "authorized_amount": None})

    sc = "schedule_dependencies"
    for n in range(1, 9):
        suffix = f"CAL-{n:03}"
        fact = "fact-calendar-" + suffix
        rule = ("pref-" if n in (2, 7) else "hc-") + suffix
        add(sc, "baseline-schedule-" + suffix, "Preserve source calendar values and priority without selecting a date.",
            [fact, rule], values=index[fact]["values"], timezone="Asia/Taipei",
            applicability=index[rule]["rule"]["applicability"],
            prerequisites=deepcopy(index[rule]["rule"].get("requires_before")),
            temporal_kind="deadline-instant" if n == 5 else "source-window",
            dependencies=(["gate-venue-confirmation"] if n == 6 else
                          ["baseline-schedule-readiness"] if n == 1 else
                          ["baseline-schedule-access-windows"] if n == 8 else []))
    for name, evidence in [
        ("access-windows", ["fact-setup-teardown-windows", "hc-setup-teardown"]),
        ("operations-deadline", ["fact-operations-deadline", "gate-operations"]),
        ("readiness", ["fact-base-readiness", "hc-security-readiness"]),
        ("programme-authority", ["fact-programme-authority", "gate-programme"]),
    ]:
        add(sc, "baseline-schedule-" + name, "Preserve scoped source requirement and unresolved prerequisites.", evidence,
            values=index[evidence[0]].get("values", {}), timezone="Asia/Taipei",
            dependencies=["baseline-schedule-access-windows"] if name == "readiness" else [])
    opening = next(r for r in state[sc] if r["id"] == "baseline-schedule-CAL-001")
    opening["prerequisites"] = {"record_id": "baseline-schedule-readiness",
                                "required_by": opening["values"]["start_at"],
                                "applicability": "specified-base-bundles-on-2026-10-17"}
    roster = "fact-programme-roster"
    rv = index[roster]["values"]
    add(sc, "baseline-programme-demos", "Include every source demo once, with each separate changeover; adds no attendees.",
        [roster, "hc-programme-demos"], values=rv)
    count = len(rv["demo_ids"])
    presentation = count * Decimal(rv["presentation_minutes"])
    changeover = count * Decimal(rv["changeover_minutes"])
    add(sc, "baseline-programme-duration", "Source demo allowance only; no finalized programme order or added buffer.",
        [roster, "hc-programme-demos"], basis="derived",
        values={"presentation": str(presentation), "changeover": str(changeover), "total": str(presentation + changeover)},
        units={"presentation": "minutes", "changeover": "minutes", "total": "minutes"},
        derivation={"operation": "roster-count-times-each-duration", "record_id": roster,
                    "count_field": "values.demo_ids", "fields": ["values.presentation_minutes", "values.changeover_minutes"]},
        dependencies=["baseline-programme-demos"])

    ac = "accessibility_baseline"
    for i in index:
        if i.startswith("hc-accessibility-"):
            add(ac, "baseline-accessibility-" + i.removeprefix("hc-accessibility-"),
                "Mandatory provision requirement; fulfillment has not been established.", [i],
                basis="stakeholder-rule", values=index[i]["rule"])
    for n in range(6, 14):
        suffix = f"SIG-{n:03}"
        add(ac, "baseline-needs-" + suffix, "Overlapping source need requiring a documented response; not additional attendance.",
            [signal(n), "hc-response-" + suffix, "hc-nonadditive-needs", "hc-privacy"],
            values=index[signal(n)]["values"], units=index[signal(n)]["units"], adds_people=False)
    for name, evidence in [
        ("space-limits", ["fact-venue-arrangement", "hc-venue-allocation"]),
        ("verification", ["unknown-live-accessibility", "fact-venue-case-confirmation", "fact-base-service-confirmation"]),
    ]:
        add(ac, "baseline-accessibility-" + name, "Preserve exercise scope and verification limitations; no operational certification.",
            evidence, values=index[evidence[0]].get("values", {}))
    add(ac, "baseline-safety-coverage", "Required safety and readiness; quote-specific first aid is conditional, not a vendor selection.",
        ["hc-safety", "hc-security-readiness", "fact-quote-Q-009"], basis="stakeholder-rule")
    add(ac, "baseline-needs-privacy", "Keep individual medical/contact details out of general artifacts.", ["hc-privacy"], basis="stakeholder-rule")
    for qid in ("Q-004", "Q-008", "Q-010"):
        i = "hc-quote-prerequisites-" + qid
        add(ac, "baseline-service-condition-" + qid, index[i]["summary"], [i],
            basis="stakeholder-rule", values=index[i]["rule"])

    # Inherited identities and their historical evidence links remain untouched.
    # Their IDs are consumed directly; source_records above retain full provenance.
    state["approval_requirements"] = deepcopy(upstream["state"]["approval_requirements"])
    unresolved = deepcopy(upstream["unresolved"])
    consumed.update(r["id"] for r in unresolved + state["approval_requirements"])
    records = [r for category in CATEGORIES for r in state[category]]
    inherited = unresolved + state["approval_requirements"]
    identifiers = [r["id"] for r in records + inherited]
    if len(identifiers) != len(set(identifiers)) or any(r["id"] in upstream_ids for r in records):
        raise ValueError("Duplicate or reused baseline ID")
    # Local edges may reference new baseline records or the five inherited gates.
    local_ids = set(identifiers)
    if any(not set(r["depends_on_record_ids"]) <= local_ids for r in records):
        raise ValueError("Baseline dependency does not resolve")
    # Historical dependencies retain their original Stage 3 graph for validation.
    graph = {**index, **{r["id"]: r for r in records}}
    validate_dependencies(list(graph.values()))
    state.update(business_clock=upstream["state"]["business_clock"],
                 business_timezone=upstream["state"]["business_timezone"],
                 output_status="draft", audience="internal-evidence-review", assumptions=[], planning_choices=[],
                 inherited_record_ids=[r["id"] for r in inherited])
    return {"run_id": upstream["run_id"], "predecessor": {"snapshot_id": upstream["snapshot_id"],
            "path": PREDECESSOR_PATH, "sha256": PREDECESSOR_HASH},
            "consumed_record_ids": sorted(consumed), "produced_record_ids": identifiers,
            "status": "partial", "state": state, "unresolved": unresolved, "decisions": []}


def build_snapshot(root: Path) -> dict:
    """Build and validate in memory without creating a deliverable."""
    from event_coordination.validation import validate_snapshot
    snapshot = {"schema_version": "event-coordination-stage-snapshot/2", "snapshot_id": str(uuid4()),
                "stage": "planning-baseline", "sequence": 4,
                "created_at": datetime.now(timezone.utc).isoformat(), **_inputs(root)}
    validate_snapshot(snapshot, root)
    return snapshot


def validate_stage4(snapshot: dict, root: Path) -> None:
    from jsonschema import Draft202012Validator, FormatChecker
    expected = _inputs(root)
    for key, value in expected.items():
        if snapshot.get(key) != value:
            raise ValueError(f"Stage 4 {key} differs from preserved baseline inputs")
    if snapshot["snapshot_id"] == snapshot["predecessor"]["snapshot_id"]:
        raise ValueError("Stage 4 requires a distinct snapshot ID")
    schema = json.loads((root / "snapshot.schema.json").read_bytes())
    validator = Draft202012Validator({"$ref": "#/$defs/record", "$defs": schema["$defs"]}, format_checker=FormatChecker())
    for r in snapshot["state"]["approval_requirements"] + snapshot["unresolved"]:
        validator.validate(r)


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
        raise ValueError("Saved Stage 4 bytes changed")
    from event_coordination.validation import validate_snapshot
    validate_snapshot(json.loads(saved), root)
    return target, hash_bytes(saved)
