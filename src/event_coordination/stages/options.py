"""Stage 5: evidence-backed candidate generation, not feasibility or approval."""

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from uuid import uuid4

from event_coordination.sources import hash_bytes
from event_coordination.stages.baseline import CATEGORIES as BASELINE_CATEGORIES
from event_coordination.stages.baseline import OUTPUT as PREDECESSOR_PATH
from event_coordination.run_contract import read_predecessor
from event_coordination.stages.constraints import OUTPUT as STAGE3_PATH
from event_coordination.stages.capture import OUTPUT as STAGE2_PATH

PREDECESSOR_HASH = "sha256:321e45c0ce912ca95223f0ed72f627e19d539c40bf71c4f97a12bc691db25098"
OUTPUT = "deliverables/snapshots/05-option-generation.json"
RECORD_ARRAYS = ("options", "rejected_early", "quote_evidence", "ancestor_references", "comparison_basis")
PACKAGES = {
    "green-table": ("Q-001", "Q-003", "Q-005", "Q-006", "Q-009", "Q-010"),
    "city-pantry": ("Q-001", "Q-004", "Q-005", "Q-006", "Q-009", "Q-010"),
}


def _inputs(root: Path) -> dict:
    from event_coordination.validation import validate_snapshot

    content = read_predecessor(root, PREDECESSOR_PATH, PREDECESSOR_HASH)
    predecessor_hash = hash_bytes(content)
    upstream = json.loads(content)
    validate_snapshot(upstream, root)  # Recursively validates schemas, hashes and original evidence.
    stage3_bytes = (root / STAGE3_PATH).read_bytes()
    stage3 = json.loads(stage3_bytes)
    stage2_bytes = (root / STAGE2_PATH).read_bytes()
    stage2 = json.loads(stage2_bytes)
    for parent, child, path, data in [(upstream, stage3, STAGE3_PATH, stage3_bytes),
                                      (stage3, stage2, STAGE2_PATH, stage2_bytes)]:
        if parent["predecessor"] != {"snapshot_id": child["snapshot_id"], "path": path, "sha256": hash_bytes(data)}:
            raise ValueError("Ancestor chain identity/hash mismatch")
        if child["run_id"] != upstream["run_id"]:
            raise ValueError("Ancestor run ID mismatch")
    facts = {r["id"]: r for r in stage3["state"]["source_facts"]}
    rules = {r["id"]: r for r in stage3["state"]["hard_constraints"]}
    baselines = {r["id"]: r for c in BASELINE_CATEGORIES for r in upstream["state"][c]}
    basis_ids = list(baselines)
    captures = {c["id"]: c for c in stage2["state"]["sources"]}
    observations = {o["id"]: (c, o) for c in captures.values() for o in c["observations"]}
    state = {c: [] for c in RECORD_ARRAYS}
    consumed = set(basis_ids)

    def add(category, identifier, summary, evidence, **extra):
        r = {"id": identifier, "summary": summary, "evidence_ids": list(dict.fromkeys(evidence)),
             "verification": "inherits-upstream-limitations", **extra}
        state[category].append(r)
        return r

    def ancestor(identifier, snapshot, path, data, record_id):
        if record_id not in snapshot["produced_record_ids"]:
            raise ValueError("Ancestor reference is not a produced record of its declared snapshot")
        consumed.add(record_id)
        return add("ancestor_references", identifier, "Verified ancestor record ownership; no upgrade of source verification.",
                   [record_id], snapshot_id=snapshot["snapshot_id"], snapshot_path=path,
                   snapshot_sha256=hash_bytes(data), record_id=record_id,
                   run_id=snapshot["run_id"], stage=snapshot["stage"])["id"]

    capacity_meanings = {
        "Q-001": "venue audience allocation; wheelchair spaces are included",
        "Q-002": "venue audience allocation; wheelchair spaces are included",
        "Q-003": "catering service capacity; nominal margin against planning demand",
        "Q-004": "catering service capacity; nominal margin against planning demand",
        "Q-005": "captioning service scope; not extra audience seating",
        "Q-006": "AV/hearing-loop package service scope; not extra audience seating",
        "Q-007": "basic AV service scope; excludes hearing loop",
        "Q-008": "livestream service capacity; not physical seating",
        "Q-009": "security service scope; not a count of security staff",
        "Q-010": "quiet-room staffing scope; separate from total event attendance",
    }
    source_quotes = {}
    for n in range(1, 11):
        qid = f"Q-{n:03}"
        fact_id = "fact-quote-" + qid
        fact = facts[fact_id]
        obs_id, = fact["evidence_ids"]
        capture, observation = observations[obs_id]
        provenance, = fact["provenance"]
        if provenance["capture_id"] != capture["id"] or provenance["sha256"] != capture["content_hash"]:
            raise ValueError("Quote fact does not match source capture")
        if provenance["locator"] != observation["locator"]:
            raise ValueError("Quote fact locator differs from observation")
        anchors = [ancestor("ancestor-stage3-quote-" + qid, stage3, STAGE3_PATH, stage3_bytes, fact_id),
                   ancestor("ancestor-stage3-rule-" + qid, stage3, STAGE3_PATH, stage3_bytes, "hc-quote-" + qid),
                   ancestor("ancestor-stage2-observation-" + qid, stage2, STAGE2_PATH, stage2_bytes, obs_id)]
        source_quotes[qid] = add("quote_evidence", "option-source-" + qid,
            "Preserved exercise quote with original values, scope, dates, conditions and located provenance.", anchors,
            basis="source-statement", values=deepcopy(fact["values"]), source_fact=deepcopy(fact),
            source_observation=deepcopy(observation), source_conditions=deepcopy(rules["hc-quote-" + qid]),
            capture_reference={"id": capture["id"], "path": capture["local_reference"],
                               "sha256": capture["content_hash"], "retrieval_status": capture["retrieval_status"],
                               "version_metadata": deepcopy(capture["version_metadata"])},
            capacity={"source_value": fact["values"]["capacity"], "source_unit": None,
                      "interpretation": capacity_meanings[qid],
                      "interpretation_evidence_ids": ["baseline-accessibility-space-limits", "baseline-headcount-planning-demand"]},
            expiration_cutoff_time=None)
    capture_id = next(iter(source_quotes.values()))["capture_reference"]["id"]
    capture_anchor = ancestor("ancestor-stage2-vendor-capture", stage2, STAGE2_PATH, stage2_bytes, capture_id)
    for quote in source_quotes.values():
        quote["evidence_ids"].append(capture_anchor)
    alternatives = ancestor("ancestor-stage3-supported-alternatives", stage3, STAGE3_PATH, stage3_bytes, "hc-supported-alternatives")
    add("comparison_basis", "option-policy-supported-alternatives", "Generate supported alternatives without fabricating a second feasible option.",
        [alternatives], basis="stakeholder-rule", source_record=deepcopy(rules["hc-supported-alternatives"]))
    add("comparison_basis", "option-baseline-context", "Preserved Stage 4 baseline records; proposals do not finalize demand, date or fulfillment.",
        basis_ids, basis="source-statement", source_records=deepcopy(list(baselines.values())))

    def number(value):
        return Decimal(value)

    allowances = {c: baselines["baseline-budget-category-" + c]["values"]["planned_amount_twd"]
                  for c in ("communications", "contingency")}
    allowance_total = sum(number(v) for v in allowances.values())
    add("comparison_basis", "option-policy-retained-allowances", "Retain communications and contingency allocations as allowances, not vendor offers or authority to spend.",
        ["baseline-budget-category-communications", "baseline-budget-category-contingency", "baseline-budget-authorization"],
        basis="planning-choice", rationale="Compare packages on the same allowance basis without adding already replaced category allocations.",
        values=allowances, currency="TWD", derivation={"operation": "retain-baseline-planned-amounts", "fields": {
            c: {"record_id": "baseline-budget-category-" + c, "field": "values.planned_amount_twd"} for c in allowances}})
    demand = number(baselines["baseline-headcount-planning-demand"]["values"]["value"])
    ceiling = number(baselines["baseline-budget-ceiling"]["values"]["value"])
    inherited_ids = [r["id"] for r in upstream["unresolved"]]
    options = {}
    for name, qids in PACKAGES.items():
        by_category = {}
        for qid in qids:
            v = source_quotes[qid]["values"]
            by_category[v["category"]] = by_category.get(v["category"], Decimal(0)) + number(v["quote_amount_twd"])
        subtotal = sum(by_category.values())
        total = subtotal + allowance_total
        catering = source_quotes[qids[1]]["values"]
        variances = {}
        for category, cost in {**by_category, **{c: number(v) for c, v in allowances.items()}}.items():
            baseline = baselines["baseline-budget-category-" + category]["values"]
            variances[category] = {"candidate_amount": str(cost),
                "planned_allocation": baseline["planned_amount_twd"], "approval_limit": baseline["approval_limit_twd"],
                "recorded_commitment": baseline["committed_amount_twd"],
                "difference_from_allocation": str(cost - number(baseline["planned_amount_twd"])),
                "authorization_status": "pending"}
        capacities = [{"quote_id": q, "source_value": source_quotes[q]["values"]["capacity"],
                       "scope": source_quotes[q]["values"]["option"], "source_unit": None,
                       "interpretation": capacity_meanings[q],
                       "interpretation_basis": "quote scope plus preserved baseline; exact source unit not supplied",
                       "assessment_status": "not-yet-tested"} for q in qids]
        options[name] = add("options", "option-oct17-" + name, "Proposed October 17 package; no winner, feasibility result or spending approval.",
            ["option-source-" + q for q in qids] + ["option-policy-retained-allowances", "option-policy-supported-alternatives", "option-baseline-context"],
            basis="planning-choice", proposed_event_date="2026-10-17", timezone="Asia/Taipei",
            component_quote_ids=list(qids), baseline_record_ids=basis_ids,
            quoted_costs_by_category={c: str(v) for c, v in by_category.items()}, retained_allowances=deepcopy(allowances),
            currency="TWD", quoted_subtotal=str(subtotal), planning_total=str(total),
            difference_below_ceiling=str(ceiling-total),
            cost_derivations={"quoted_subtotal": {"operation": "sum", "inputs": [
                {"record_id": "option-source-" + q, "field": "values.quote_amount_twd"} for q in qids]},
                "planning_total": {"operation": "quoted-subtotal-plus-retained-allowances", "allowance_record_id": "option-policy-retained-allowances"},
                "difference_below_ceiling": {"operation": "ceiling-minus-planning-total", "ceiling_record_id": "baseline-budget-ceiling"}},
            service_capacity_basis=capacities, catering_capacity_margin={"value": str(number(catering["capacity"])-demand),
                "basis": "derived", "operation": "recorded-catering-capacity-minus-planning-demand",
                "capacity_record_id": "option-source-" + qids[1], "demand_record_id": "baseline-headcount-planning-demand",
                "interpretation": "nominal catering margin; not a feasibility conclusion"},
            allocation_variances=variances,
            conditions=[deepcopy(baselines["baseline-service-condition-" + q]) for q in ("Q-004", "Q-010") if q in qids],
            unresolved_ids=inherited_ids, material_differences={"catering_quote": qids[1],
                "catering_capacity": catering["capacity"], "catering_price": catering["quote_amount_twd"],
                "interpretation": "Different cost and nominal capacity; safety requirements are unchanged."},
            assessment_status="not-yet-tested", authorization_status="pending", selected=False)

    def screen(identifier, summary, quote_ids, reasons, reconsideration, **extra):
        return add("rejected_early", identifier, summary,
            ["option-source-" + q for q in quote_ids] + ["option-baseline-context", "option-policy-retained-allowances"],
            basis="planning-choice", candidate_composition=list(quote_ids), screening_scope="candidate-as-described-under-retained-allowance-policy",
            screening_reasons=reasons, reconsideration_requirements=reconsideration,
            assessment_status="screened-out-before-full-testing", authorization_status="pending", **extra)
    screen("screen-oct24-incomplete-package", "Fallback venue is not a supported complete package.", ["Q-002"],
           ["Keynote unavailable on October 24.", "Other supplied service offers and demo/readiness confirmation apply to October 17, not October 24."],
           ["Evidenced resolution of programme conflict and date-compatible service offers/readiness."],
           proposed_event_date="2026-10-24", missing_service_quotes=[f"Q-{n:03}" for n in range(3, 11)])
    loop_excluded = "no hearing loop" in source_quotes["Q-007"]["values"]["notes"].casefold()
    screen("screen-oct17-q007-no-loop", "Q-007 alone does not evidence the required hearing-loop response.", ["Q-007"],
           (["Quote excludes hearing loop; no replacement service or price is evidenced."] if loop_excluded else
            ["Current Q-007 scope requires review; live loop provision and applicability of exercise readiness are unverified."]),
           ["Evidence of adequate hearing-loop response and its service scope/cost."],
           proposed_event_date="2026-10-17", source_condition=deepcopy(source_quotes["Q-007"]["values"]))
    for name, base in options.items():
        add_on = number(source_quotes["Q-008"]["values"]["quote_amount_twd"])
        total = number(base["planning_total"]) + add_on
        screen("screen-oct17-" + name + "-stream",
               ("Livestream addition exceeds the ceiling under this allowance policy and retains unmet prerequisites." if total>ceiling else
                "Livestream addition fits the calculated ceiling but retains unmet operational prerequisites; not selected."),
               [*base["component_quote_ids"], "Q-008"],
               [("Planning total exceeds the overall ceiling under the retained allowances." if total>ceiling else "Planning total is within the overall ceiling under the retained allowances; this is not spending authority."), "Network-test evidence and venue confirmation remain unresolved."],
               ["Evidence-backed package within the ceiling and evidenced network test/venue confirmation; no assumed remedy."],
               proposed_event_date="2026-10-17", base_option_id=base["id"], planning_total=str(total),
               difference_above_ceiling=str(total-ceiling), currency="TWD",
               derivation={"operation": "base-planning-total-plus-add-on", "base_record_id": base["id"],
                           "base_field": "planning_total", "add_on_record_id": "option-source-Q-008", "add_on_field": "values.quote_amount_twd"},
               conditions=[deepcopy(baselines["baseline-service-condition-Q-008"])])

    state["approval_requirements"] = deepcopy(upstream["state"]["approval_requirements"])
    unresolved = deepcopy(upstream["unresolved"])
    inherited = unresolved + state["approval_requirements"]
    consumed.update(r["id"] for r in inherited)
    new_records = [r for c in RECORD_ARRAYS for r in state[c]]
    ids = [r["id"] for r in new_records + inherited]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate option-generation record IDs")
    allowed = set(ids) | consumed
    if any(not r["evidence_ids"] or not set(r["evidence_ids"]) <= allowed for r in new_records):
        raise ValueError("Unresolved option evidence reference")
    state.update(business_clock=upstream["state"]["business_clock"], business_timezone=upstream["state"]["business_timezone"],
                 output_status="draft", audience="internal-evidence-review", inherited_record_ids=[r["id"] for r in inherited])
    return {"run_id": upstream["run_id"], "predecessor": {"snapshot_id": upstream["snapshot_id"], "path": PREDECESSOR_PATH, "sha256": predecessor_hash},
            "consumed_record_ids": sorted(consumed), "produced_record_ids": ids,
            "status": "partial", "state": state, "unresolved": unresolved, "decisions": []}


def build_snapshot(root: Path) -> dict:
    """Build and validate in memory without writing Snapshot 05."""
    from event_coordination.validation import validate_snapshot
    snapshot = {"schema_version": "event-coordination-stage-snapshot/2", "snapshot_id": str(uuid4()),
                "stage": "option-generation", "sequence": 5, "created_at": datetime.now(timezone.utc).isoformat(), **_inputs(root)}
    validate_snapshot(snapshot, root)
    return snapshot


def validate_stage5(snapshot: dict, root: Path) -> None:
    from jsonschema import Draft202012Validator, FormatChecker
    expected = _inputs(root)
    for key, value in expected.items():
        if snapshot.get(key) != value:
            raise ValueError(f"Stage 5 {key} differs from preserved option-generation inputs")
    if snapshot["snapshot_id"] == snapshot["predecessor"]["snapshot_id"]:
        raise ValueError("Stage 5 requires a distinct snapshot ID")
    schema = json.loads((root / "snapshot.schema.json").read_bytes())
    validator = Draft202012Validator({"$ref": "#/$defs/record", "$defs": schema["$defs"]}, format_checker=FormatChecker())
    for r in [r for c in RECORD_ARRAYS for r in snapshot["state"][c]] + snapshot["unresolved"] + snapshot["state"]["approval_requirements"]:
        validator.validate(r)


def write_snapshot(root: Path) -> tuple[Path, str]:
    """Exclusive writer for a separately authorized generation step."""
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
        raise ValueError("Saved Stage 5 bytes changed")
    from event_coordination.validation import validate_snapshot
    validate_snapshot(json.loads(saved), root)
    return target, hash_bytes(saved)
