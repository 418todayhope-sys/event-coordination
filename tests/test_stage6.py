"""Stage 6 checks against preserved evidence and isolated synthetic boundaries."""

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import shutil

from jsonschema import ValidationError
import pytest

from event_coordination.sources import hash_bytes
from event_coordination.stages.feasibility import (
    OUTPUT, PREDECESSOR_HASH, PREDECESSOR_PATH, RECORD_ARRAYS, aggregate,
    build_snapshot, build_witness, capacity_outcome, quote_outcome,
    reconstruct_costs, validate_witness, write_snapshot,
)
from event_coordination.validation import validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Stage 6 must not retrieve sources")
    monkeypatch.setattr("socket.socket.connect", deny)


@pytest.fixture
def project(tmp_path):
    for directory in ["interviews", "evidence/originals", "evidence/captures"]:
        shutil.copytree(ROOT / directory, tmp_path / directory)
    shutil.copyfile(ROOT / "snapshot.schema.json", tmp_path / "snapshot.schema.json")
    dest = tmp_path / "deliverables/snapshots"; dest.mkdir(parents=True)
    for p in (ROOT / "deliverables/snapshots").glob("0[1-5]-*.json"):
        shutil.copyfile(p, dest / p.name)
    return tmp_path


@pytest.fixture
def assessment():
    # Immutable in-memory fixture; mutation tests must explicitly deepcopy.
    return build_snapshot(ROOT)


def previous(root=ROOT):
    return json.loads((root / PREDECESSOR_PATH).read_bytes())


def schedule_inputs():
    context = next(r for r in previous()["state"]["comparison_basis"] if r["id"] == "option-baseline-context")
    baseline = {r["id"]: r["values"] for r in context["source_records"]}
    return (baseline["baseline-programme-demos"],
            {f"CAL-{n:03}": baseline[f"baseline-schedule-CAL-{n:03}"] for n in range(1, 9)},
            baseline["baseline-schedule-access-windows"])


@pytest.mark.parametrize("outcomes,expected", [
    (["pass"], "feasible"), (["pass", "conditional"], "conditional"),
    (["conditional", "unknown"], "unverified"), (["fail", "unknown", "conditional"], "infeasible"),
    (["not-applicable", "pass"], "feasible"),
])
def test_aggregation_precedence(outcomes, expected):
    checks = [{"outcome": o, "hard_requirement": True} for o in outcomes]
    assert aggregate(checks) == expected
    assert aggregate(list(reversed(checks))) == expected


def test_authorization_and_live_verification_do_not_decide_technical_result():
    assert aggregate([{"outcome": "pass", "hard_requirement": True},
                      {"outcome": "conditional", "hard_requirement": False},
                      {"outcome": "unknown", "hard_requirement": False}]) == "feasible"
    for checks in [[], [{"outcome": "not-applicable", "hard_requirement": True}],
                   [{"outcome": "invented", "hard_requirement": True}]]:
        with pytest.raises(ValueError):
            aggregate(checks)


@pytest.mark.parametrize("capacity,demand,expected", [(245, 245, "pass"), (244, 245, "fail"), (246, 245, "pass"), (None, 245, "unknown"), (20, 9, "pass"), (6, 6, "pass"), (5, 6, "fail")])
def test_capacity_boundaries(capacity, demand, expected):
    assert capacity_outcome(capacity, demand) == expected


@pytest.mark.parametrize("expiry,event,status,expected", [
    ("2026-08-25", "2026-10-17", "available", "fail"),
    ("2026-08-26", "2026-10-17", "available", "unknown"),
    ("2026-08-27", "2026-10-17", "available", "pass"),
    ("2026-09-05", "2026-10-24", "available", "fail"),
    ("2026-09-05", "2026-10-17", "conditional", "conditional"),
    ("2026-09-05", "2026-10-17", "held", "pass"),
    (None, "2026-10-17", "available", "unknown"),
])
def test_quote_validity_uses_business_clock_and_unknown_cutoff(expiry, event, status, expected):
    assert quote_outcome({"available_date": "2026-10-17", "valid_until": expiry, "status": status}, event, "2026-08-26T12:00:00+08:00") == expected


def test_known_quote_violation_dominates_missing_fields():
    assert quote_outcome({"available_date": None, "valid_until": "2026-08-25"}, "2026-10-17", "2026-08-26T12:00:00+08:00") == "fail"
    assert quote_outcome({"available_date": "2026-10-24", "valid_until": None}, "2026-10-17", "2026-08-26T12:00:00+08:00") == "fail"


def test_invalid_capacity_rejected():
    for value in ("NaN", "Infinity", "-1"):
        with pytest.raises(ValueError):
            capacity_outcome(value, "245")


def test_naive_clock_rejected():
    with pytest.raises(ValueError):
        quote_outcome({"available_date": "2026-10-17", "valid_until": "2026-09-05"}, "2026-10-17", "2026-08-26T12:00:00")


def test_independent_money_uses_source_values_and_refuses_double_counting():
    quotes = {"synthetic": {"source_fact": {"values": {"category": "venue", "quote_amount_twd": "0.10"}}, "values": {"quote_amount_twd": "999"}}}
    result = reconstruct_costs(quotes, ["synthetic"], {"communications": "0.20"})
    assert Decimal(result["planning_total"]) == Decimal("0.30")
    with pytest.raises(ValueError):
        reconstruct_costs(quotes, ["synthetic", "synthetic"], {})
    with pytest.raises(ValueError):
        reconstruct_costs(quotes, ["synthetic"], {"venue": "1"})


def test_complete_witness_and_supported_durations():
    roster, calendar, windows = schedule_inputs()
    witness = build_witness("synthetic", "2026-10-17", roster, calendar, windows)
    validate_witness(witness, roster, calendar, windows)
    assert len([i for i in witness["intervals"] if i["kind"] == "demo"]) == 12
    assert len([i for i in witness["intervals"] if i["kind"] == "changeover"]) == 12
    assert all(i["start_at"].endswith("+08:00") for i in witness["intervals"])
    assert witness["individual_vendor_durations"] is None and witness["extra_mandatory_buffer"] is None
    assert all(i["basis"] == "planning-choice" for i in witness["intervals"] if i["kind"] in ("break", "lunch", "opening"))


@pytest.mark.parametrize("mutation", ["missing-demo", "missing-changeover", "duplicate-demo", "duration", "overlap", "timezone", "lane", "keynote", "setup", "teardown", "readiness", "opening", "calendar-clearance"])
def test_witness_rejects_timing_conflicts(mutation):
    roster, calendar, windows = schedule_inputs()
    w = build_witness("synthetic", "2026-10-17", roster, calendar, windows)
    demo = next(i for i in w["intervals"] if i["kind"] == "demo")
    if mutation.startswith("missing-"):
        kind = mutation.removeprefix("missing-")
        w["intervals"].remove(next(i for i in w["intervals"] if i["kind"] == kind))
    elif mutation == "duplicate-demo":
        demos = [i for i in w["intervals"] if i["kind"] == "demo"]
        demos[1]["demo_id"] = demos[0]["demo_id"]
    elif mutation == "duration": demo["end_at"] = "2026-10-17T11:26:00+08:00"
    elif mutation == "overlap": demo["start_at"] = "2026-10-17T11:14:00+08:00"
    elif mutation == "timezone": demo["start_at"] = "2026-10-17T11:15:00"
    elif mutation == "lane": demo["lane"] = "invented-lane"
    elif mutation == "keynote": next(i for i in w["intervals"] if i["kind"] == "keynote")["end_at"] = "2026-10-17T10:59:00+08:00"
    elif mutation == "setup": next(i for i in w["intervals"] if i["kind"] == "setup-envelope")["start_at"] = "2026-10-17T07:00:00+08:00"
    elif mutation == "teardown": next(i for i in w["intervals"] if i["kind"] == "teardown-envelope")["end_at"] = "2026-10-17T18:31:00+08:00"
    elif mutation == "readiness": w["readiness_at"] = "2026-10-17T09:31:00+08:00"
    elif mutation == "opening": w["intervals"].remove(next(i for i in w["intervals"] if i["kind"] == "opening"))
    else: calendar["CAL-008"]["end_at"] = "2026-10-17T18:00:00+08:00"
    with pytest.raises(ValueError):
        validate_witness(w, roster, calendar, windows)


def test_chain_schema_provenance_and_no_writes(project):
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    s = build_snapshot(project)
    validate_snapshot(s, project)
    p = previous(project)
    assert s["run_id"] == p["run_id"] == "988f5ccf-4aeb-44d7-984d-777b1a2412e1"
    assert s["predecessor"] == {"snapshot_id": p["snapshot_id"], "path": PREDECESSOR_PATH, "sha256": PREDECESSOR_HASH}
    assert PREDECESSOR_HASH == hash_bytes(before[project/PREDECESSOR_PATH])
    assert s["snapshot_id"] != p["snapshot_id"] and s["sequence"] == 6
    assert set(s["consumed_record_ids"]) <= set(p["produced_record_ids"])
    ids = [r["id"] for c in RECORD_ARRAYS for r in s["state"][c]]
    assert len(ids) == len(set(ids)) and ids == s["produced_record_ids"]
    for c in ["checks", "option_results", "assessment_policy", "screening_checks"]:
        for r in s["state"][c]:
            assert r["evidence_ids"] and set(r["evidence_ids"]) <= set(p["produced_record_ids"])
    assert s["unresolved"] == s["state"]["unresolved_conditions"]
    assert all(p.read_bytes() == b for p, b in before.items())
    assert not (project/OUTPUT).exists()


def test_independent_matrices_and_classification(assessment):
    s=assessment
    assert len(s["state"]["option_results"]) == 2
    matrices=[]
    for r, expected_subtotal, expected_total in zip(s["state"]["option_results"], [429000,447000], [494000,512000], strict=True):
        checks=[c for c in s["state"]["checks"] if c["candidate_id"] == r["candidate_id"]]
        matrices.append({c["requirement"] for c in checks if not c["requirement"].startswith(("quote-", "scope-", "allocation-policy-"))})
        assert r["feasibility"] == aggregate(checks)
        assert r["feasibility"] == "conditional"
        assert r["blocking_check_ids"] == [c["id"] for c in checks if c["hard_requirement"] and c["outcome"] in ("fail","unknown","conditional")]
        assert all("walkthrough-prerequisite" in i for i in r["blocking_check_ids"])
        assert Decimal(r["reconstructed_costs"]["quoted_subtotal"]) == expected_subtotal
        assert Decimal(r["reconstructed_costs"]["planning_total"]) == expected_total
        assert not r["selected"] and r["authorization_status"] == "pending"
        assert r["assessment_scope"] == "fictional-exercise"
        for suffix in ["budget-ceiling","capacity-audience","capacity-catering","capacity-wheelchair","capacity-quiet-room","programme","access-windows","safety"]:
            assert next(c for c in checks if c["requirement"] == suffix)["outcome"] == "pass"
        for feature in ["step-free-programme","step-free-restrooms","wheelchair-seating","live-captions","hearing-loop","quiet-room-availability","quiet-room-staffing"]:
            c=next(c for c in checks if c["requirement"] == "accessibility-"+feature)
            assert c["outcome"] == "pass" and c["inputs"]["live_provision_verified"] is None
        assert next(c for c in checks if c["requirement"] == "authorization")["hard_requirement"] is False
        assert next(c for c in checks if c["requirement"] == "live-verification")["hard_requirement"] is False
    assert matrices[0] == matrices[1]


def test_issues_approvals_and_early_screening_preserved(assessment):
    s=assessment; p=previous()
    inherited={r["id"]:r for r in p["unresolved"]}
    actual={r["id"]:r for r in s["unresolved"]}
    assert len(inherited)==79
    assert all(actual[k]==v for k,v in inherited.items())
    assert s["state"]["inherited_unresolved_ids"]==list(inherited)
    assert s["state"]["approval_requirements"]==p["state"]["approval_requirements"]
    assert len(s["state"]["approval_requirements"])==5 and all(g["status"]=="pending" for g in s["state"]["approval_requirements"])
    assert s["state"]["retained_early_screening"]==p["state"]["rejected_early"]
    audits=s["state"]["screening_checks"]
    assert len(audits)==4
    streams=[r for r in audits if r["id"].endswith("-stream")]
    assert {Decimal(r["inputs"]["planning_total"]) for r in streams}=={Decimal(549000),Decimal(567000)}
    assert all(r["outcome"]=="fail" for r in streams)
    assert all(r["inputs"]["conditions"][0]["values"]["satisfied"] is None for r in streams)
    assert s["status"]=="partial" and s["decisions"]==[]


@pytest.mark.parametrize("field",["option_results","unresolved_conditions"])
def test_required_arrays(project, assessment, field):
    s=deepcopy(assessment);del s["state"][field]
    with pytest.raises(ValidationError):validate_snapshot(s,project)


@pytest.mark.parametrize("mutation",["total","outcome","feasibility","witness","approval","issue","evidence","run","predecessor"])
def test_semantic_edits_rejected(project, assessment, mutation):
    s=deepcopy(assessment)
    if mutation=="total":s["state"]["option_results"][0]["reconstructed_costs"]["planning_total"]="1"
    elif mutation=="outcome":s["state"]["checks"][0]["outcome"]="fail"
    elif mutation=="feasibility":s["state"]["option_results"][0]["feasibility"]="feasible"
    elif mutation=="witness":s["state"]["schedule_witnesses"][0]["intervals"].pop()
    elif mutation=="approval":s["state"]["approval_requirements"][0]["status"]="approved"
    elif mutation=="issue":s["unresolved"].pop()
    elif mutation=="evidence":s["state"]["checks"][0]["evidence_ids"]=["missing"]
    elif mutation=="run":s["run_id"]="other-run"
    else:s["predecessor"]["sha256"]="sha256:"+"0"*64
    with pytest.raises(ValueError):validate_snapshot(s,project)


@pytest.mark.parametrize("path",[PREDECESSOR_PATH,"deliverables/snapshots/04-planning-baseline.json","evidence/originals/Project C — Vendor Quotes.xlsx","interviews/project-c-event-coordination-20261016-2056.md"])
def test_tampered_inputs(project,path):
    p=project/path;p.write_bytes(p.read_bytes()+b"\n")
    with pytest.raises(ValueError):build_snapshot(project)


def test_missing_evidence(project):
    (project/"evidence/originals/f1710485827023.pdf").unlink()
    with pytest.raises(FileNotFoundError):build_snapshot(project)


def test_exclusive_writer_only_in_temporary_root(project):
    target,digest=write_snapshot(project)
    content=target.read_bytes()
    assert hash_bytes(content)==digest
    validate_snapshot(json.loads(content),project)
    with pytest.raises(FileExistsError):write_snapshot(project)
    assert target.read_bytes()==content


@pytest.mark.parametrize("replacement", [0, 1])
def test_strict_types_reject_numbers_for_booleans(replacement):
    from event_coordination.stages.feasibility import validate_assessment_types
    for expected in (True, False):
        with pytest.raises(ValueError, match="type mismatch"):
            validate_assessment_types({"nested": [{"flag": replacement}]}, {"nested": [{"flag": expected}]})


@pytest.mark.parametrize("field", ["selected", "hard_requirement", "blocks_technical_assessment", "scope-exclusion", "scope-prerequisite", "scope-separation"])
def test_semantic_boolean_mutations_rejected(project, assessment, field):
    s = deepcopy(assessment)
    if field == "selected":
        target = s["state"]["option_results"][0]; key = "selected"
    elif field == "hard_requirement":
        target = s["state"]["checks"][0]; key = "hard_requirement"
    elif field == "blocks_technical_assessment":
        target = next(r for r in s["unresolved"] if r["id"].startswith("condition-")); key = "blocks_technical_assessment"
        # The canonical view is independently type-checked as well.
        s["state"]["unresolved_conditions"] = deepcopy(s["unresolved"])
    else:
        scope = next(c for c in s["state"]["checks"] if c["requirement"] == "scope-Q-005")["inputs"]
        if field == "scope-exclusion": target = scope["assessments"][0]; key = "explicit_exclusion"
        elif field == "scope-prerequisite": target = scope["prerequisite_context"]; key = "caption_adequacy"
        else: target = scope; key = "availability_assessed_separately"
    assert type(target[key]) is bool
    target[key] = int(target[key])
    with pytest.raises(ValueError, match="type mismatch"):
        validate_snapshot(s, project)


def test_false_positive_opening_from_audit_is_rejected():
    roster, calendar, windows = schedule_inputs()
    w = build_witness("synthetic", "2026-10-17", roster, calendar, windows)
    opening = next(i for i in w["intervals"] if i["kind"] == "opening")
    flex = next(i for i in w["intervals"] if i["kind"] == "flexible-programme-closing-allowance")
    opening.update(start_at="2026-10-17T15:06:00+08:00", end_at="2026-10-17T15:36:00+08:00")
    flex["start_at"] = "2026-10-17T15:36:00+08:00"
    with pytest.raises(ValueError, match="Opening must start"):
        validate_witness(w, roster, calendar, windows)


def test_half_open_boundaries_and_distinct_lanes_remain_valid():
    roster, calendar, windows = schedule_inputs()
    w = build_witness("synthetic", "2026-10-17", roster, calendar, windows)
    validate_witness(w, roster, calendar, windows)
    setup = next(i for i in w["intervals"] if i["kind"] == "setup-envelope")
    opening = next(i for i in w["intervals"] if i["kind"] == "opening")
    keynote = next(i for i in w["intervals"] if i["kind"] == "keynote")
    assert setup["end_at"] == opening["start_at"] == w["readiness_at"]
    assert opening["end_at"] == keynote["start_at"]
    assert setup["lane"] != opening["lane"]


@pytest.mark.parametrize("mutation", ["opening-gap", "setup-readiness", "programme-end"])
def test_connected_programme_boundaries_reject_gaps(mutation):
    roster, calendar, windows = schedule_inputs()
    w = build_witness("synthetic", "2026-10-17", roster, calendar, windows)
    if mutation == "opening-gap":
        next(i for i in w["intervals"] if i["kind"] == "opening")["end_at"] = "2026-10-17T09:59:00+08:00"
    elif mutation == "setup-readiness":
        windows["setup_end"] = "09:29"
        next(i for i in w["intervals"] if i["kind"] == "setup-envelope")["end_at"] = "2026-10-17T09:29:00+08:00"
    else:
        next(i for i in w["intervals"] if i["kind"] == "flexible-programme-closing-allowance")["end_at"] = "2026-10-17T16:59:00+08:00"
    with pytest.raises(ValueError):
        validate_witness(w, roster, calendar, windows)


def scope_fixture(qid):
    upstream = previous()
    quote = next(q for q in upstream["state"]["quote_evidence"] if q["values"]["quote_id"] == qid)
    return deepcopy(quote["source_fact"]["values"]), {
        "venue_allocation": True, "dietary_response": True, "allergy_contacts": True,
        "caption_adequacy": True, "loop_adequacy": True, "quiet_room_available": True,
        "network_test": None, "streaming_venue_confirmation": None,
    }


@pytest.mark.parametrize("qid,field,replacement,expected", [
    ("Q-001", "option", "4F Plenary Hall only", "unknown"),
    ("Q-003", "option", "Lunch only", "unknown"),
    ("Q-004", "notes", "Allergy process unspecified", "unknown"),
    ("Q-005", "notes", "Two captioners included; No live captions included", "fail"),
    ("Q-006", "notes", "No hearing loop included", "fail"),
    ("Q-009", "notes", "No first aid lead included", "fail"),
    ("Q-010", "option", "Room only; No quiet room staffing", "fail"),
])
def test_availability_unchanged_but_scope_loss_is_detected(qid, field, replacement, expected):
    from event_coordination.stages.feasibility import evaluate_quote_scope
    quote, context = scope_fixture(qid)
    assert evaluate_quote_scope(quote, context)["outcome"] == "pass"
    status = quote["status"]
    quote[field] = replacement
    assert quote["status"] == status
    result = evaluate_quote_scope(quote, context)
    assert result["outcome"] == expected
    assert result["availability_assessed_separately"] is True
    assert result["readiness_assessed_separately"] is True


@pytest.mark.parametrize("qid,key", [("Q-004", "allergy_contacts"), ("Q-010", "quiet_room_available")])
def test_scope_prerequisites_require_evidence(qid, key):
    from event_coordination.stages.feasibility import evaluate_quote_scope
    quote, context = scope_fixture(qid)
    context[key] = None
    assert evaluate_quote_scope(quote, context)["outcome"] == "conditional"
    context[key] = False
    assert evaluate_quote_scope(quote, context)["outcome"] == "fail"
    context[key] = 1
    with pytest.raises(ValueError):
        evaluate_quote_scope(quote, context)


def test_stream_scope_and_network_readiness_are_not_availability():
    from event_coordination.stages.feasibility import evaluate_quote_scope
    quote, context = scope_fixture("Q-008")
    quote["status"] = "available"
    assert evaluate_quote_scope(quote, context)["outcome"] == "conditional"
    context.update(network_test=True, streaming_venue_confirmation=True)
    assert evaluate_quote_scope(quote, context)["outcome"] == "pass"


def test_new_conditions_are_actionable_and_cite_supported_resolution_basis(assessment):
    inherited = {r["id"] for r in previous()["unresolved"]}
    conditions = [r for r in assessment["unresolved"] if r["id"] not in inherited]
    assert len(conditions) == 9
    for c in conditions:
        assert c["required_evidence"] != c["summary"]
        assert c["required_evidence"] and c["resolution_basis"]
        assert set(c["related_inherited_unresolved_ids"]) <= inherited
        if "allocation-policy-" in c["id"]:
            assert c["owner"] == "Operations"
            assert c["related_inherited_unresolved_ids"] == ["unknown-budget-reallocation"]
            assert c["resolution_deadline"] is None
        elif "walkthrough-prerequisite" in c["id"]:
            assert c["owner"] is None  # The source does not name a confirming owner.
            assert c["resolution_deadline"] == {"before": "2026-09-25T14:00:00+08:00", "timezone": "Asia/Taipei"}
            assert c["related_inherited_unresolved_ids"]
        elif "live-verification" in c["id"]:
            assert c["related_inherited_unresolved_ids"] == ["unknown-live-accessibility"]
            assert c["owner"] is None and c["resolution_deadline"] is None
        elif "authorization" in c["id"]:
            assert c["related_inherited_unresolved_ids"] == ["unknown-approvals"]
            assert {r["role"] for r in c["owner_roles"]} == {"Operations", "Category budget owners", "Programme"}
            assert c["resolution_deadline"] is None


@pytest.mark.parametrize("flag", [0, 1])
def test_aggregation_requires_actual_boolean_applicability(flag):
    with pytest.raises(ValueError, match="must be Boolean"):
        aggregate([{"outcome": "pass", "hard_requirement": flag}])
