"""Stage 5 integration tests use preserved evidence in isolated temporary roots."""

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import shutil

from jsonschema import ValidationError
import pytest

from event_coordination.sources import hash_bytes
from event_coordination.stages.options import (
    OUTPUT, PACKAGES, PREDECESSOR_HASH, PREDECESSOR_PATH, RECORD_ARRAYS,
    build_snapshot, write_snapshot,
)
from event_coordination.validation import validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Stage 5 must not retrieve sources")
    monkeypatch.setattr("socket.socket.connect", deny)


@pytest.fixture
def project(tmp_path):
    for directory in ["interviews", "evidence/originals", "evidence/captures"]:
        shutil.copytree(ROOT / directory, tmp_path / directory)
    shutil.copyfile(ROOT / "snapshot.schema.json", tmp_path / "snapshot.schema.json")
    dest = tmp_path / "deliverables/snapshots"
    dest.mkdir(parents=True)
    for p in (ROOT / "deliverables/snapshots").glob("0[1-4]-*.json"):
        shutil.copyfile(p, dest / p.name)
    return tmp_path


def records(s):
    return {r["id"]: r for c in RECORD_ARRAYS for r in s["state"][c]}


def test_schema_chain_and_read_only_build(project):
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    s = build_snapshot(project)
    validate_snapshot(s, project)
    previous = json.loads((project / PREDECESSOR_PATH).read_bytes())
    assert s["run_id"] == previous["run_id"] == "988f5ccf-4aeb-44d7-984d-777b1a2412e1"
    assert s["predecessor"] == {"snapshot_id": previous["snapshot_id"], "path": PREDECESSOR_PATH, "sha256": PREDECESSOR_HASH}
    assert PREDECESSOR_HASH == hash_bytes(before[project / PREDECESSOR_PATH])
    assert s["snapshot_id"] != previous["snapshot_id"]
    assert s["stage"] == "option-generation" and s["sequence"] == 5
    assert datetime.fromisoformat(s["created_at"]).utcoffset().total_seconds() == 0
    assert s["created_at"] != s["state"]["business_clock"]
    assert s["state"]["business_clock"] == previous["state"]["business_clock"]
    produced = list(records(s)) + [r["id"] for r in s["unresolved"] + s["state"]["approval_requirements"]]
    assert set(produced) == set(s["produced_record_ids"])
    assert len(produced) == len(set(produced))
    assert not (project / OUTPUT).exists()
    assert all(p.read_bytes() == b for p, b in before.items())


def test_ancestor_ownership_original_values_and_source_hashes(project):
    s = build_snapshot(project)
    previous = json.loads((project / PREDECESSOR_PATH).read_bytes())
    rr = records(s)
    ancestor_ids = set()
    for ref in s["state"]["ancestor_references"]:
        path = project / ref["snapshot_path"]
        ancestor = json.loads(path.read_bytes())
        assert ref["snapshot_sha256"] == hash_bytes(path.read_bytes())
        assert ref["snapshot_id"] == ancestor["snapshot_id"]
        assert ref["record_id"] in ancestor["produced_record_ids"]
        assert ref["run_id"] == ancestor["run_id"] == s["run_id"]
        assert ref["stage"] in ("constraint-model", "source-capture")
        ancestor_ids.add(ref["record_id"])
    assert set(s["consumed_record_ids"]) <= set(previous["produced_record_ids"]) | ancestor_ids
    for r in rr.values():
        assert set(r["evidence_ids"]) <= set(s["produced_record_ids"]) | set(s["consumed_record_ids"])
    stage3 = json.loads((project / "deliverables/snapshots/03-constraint-model.json").read_bytes())
    facts = {r["id"]: r for r in stage3["state"]["source_facts"]}
    assert len(s["state"]["quote_evidence"]) == 10
    for q in s["state"]["quote_evidence"]:
        qid = q["values"]["quote_id"]
        assert q["source_fact"] == facts["fact-quote-" + qid]
        assert q["values"] == q["source_fact"]["values"]
        assert q["source_fact"]["source_values"][0]["original_cell_values"]
        assert q["source_observation"]["locator"] == q["source_fact"]["provenance"][0]["locator"]
        capture = q["capture_reference"]
        assert capture["sha256"] == hash_bytes((project / capture["path"]).read_bytes())
        assert capture["retrieval_status"] == "unverified"
        assert "fact-quote-" + qid not in previous["produced_record_ids"]
        assert q["capacity"]["source_unit"] is None


def test_package_arithmetic_allowances_and_variances(project):
    s = build_snapshot(project); rr = records(s)
    for name, subtotal, total, margin in [("green-table", 429000, 494000, 15), ("city-pantry", 447000, 512000, 55)]:
        r = rr["option-oct17-" + name]
        assert r["component_quote_ids"] == list(PACKAGES[name])
        prices = [Decimal(rr["option-source-" + q]["values"]["quote_amount_twd"]) for q in PACKAGES[name]]
        assert sum(prices) == Decimal(r["quoted_subtotal"]) == subtotal
        assert sum(Decimal(v) for v in r["quoted_costs_by_category"].values()) == subtotal
        assert r["retained_allowances"] == {"communications": "25000.0", "contingency": "40000.0"}
        assert subtotal + sum(Decimal(v) for v in r["retained_allowances"].values()) == Decimal(r["planning_total"]) == total
        assert Decimal(r["difference_below_ceiling"]) == 520000-total
        assert Decimal(r["catering_capacity_margin"]["value"]) == margin
        quote = rr[r["catering_capacity_margin"]["capacity_record_id"]]
        assert Decimal(quote["values"]["capacity"]) - 245 == margin
        assert Decimal(r["allocation_variances"]["security"]["difference_from_allocation"]) == 3000
        assert Decimal(r["allocation_variances"]["security"]["approval_limit"]) == 35000
        assert all(Decimal(v["recorded_commitment"]) == 0 for v in r["allocation_variances"].values())
        assert Decimal(r["allocation_variances"]["catering"]["difference_from_allocation"]) == (-7000 if name == "green-table" else 11000)
        formula = r["cost_derivations"]["quoted_subtotal"]
        assert sum(Decimal(rr[i["record_id"]]["values"]["quote_amount_twd"]) for i in formula["inputs"]) == subtotal
    assert rr["option-policy-retained-allowances"]["basis"] == "planning-choice"
    assert rr["option-source-Q-008"]["capacity"]["interpretation"] == "livestream service capacity; not physical seating"
    assert rr["option-source-Q-010"]["capacity"]["interpretation"].startswith("quiet-room staffing scope")


def test_dates_expirations_exclusions_and_screening(project):
    s = build_snapshot(project); rr = records(s)
    for option in s["state"]["options"]:
        assert option["proposed_event_date"] == "2026-10-17"
        assert option["timezone"] == "Asia/Taipei"
        for qid in option["component_quote_ids"]:
            q = rr["option-source-" + qid]
            assert q["values"]["available_date"] == option["proposed_event_date"]
            assert q["values"]["valid_until"] > "2026-08-26"
            assert q["expiration_cutoff_time"] is None
            assert q["source_conditions"]["rule"]["expiry_cutoff_time"] is None
    assert rr["option-source-Q-001"]["values"]["status"] == "held"
    assert "no real reservation" in rr["option-source-Q-001"]["values"]["notes"]
    assert rr["option-source-Q-002"]["values"]["available_date"] == "2026-10-24"
    assert "No hearing loop" in rr["option-source-Q-007"]["values"]["notes"]
    assert rr["option-source-Q-008"]["values"]["status"] == "conditional"
    screens = s["state"]["rejected_early"]
    assert len(screens) == 4
    assert rr["screen-oct24-incomplete-package"]["missing_service_quotes"]
    assert rr["screen-oct17-q007-no-loop"]["reconsideration_requirements"]
    for name, total in [("green-table", 549000), ("city-pantry", 567000)]:
        r = rr["screen-oct17-" + name + "-stream"]
        assert Decimal(r["planning_total"]) == total
        assert Decimal(r["difference_above_ceiling"]) == total-520000
        assert r["conditions"][0]["values"]["satisfied"] is None
        assert r["conditions"][0]["values"]["applies_if"] == {"quote_proposed": "Q-008"}
        assert r["assessment_status"] == "screened-out-before-full-testing"


def test_uncertainty_no_selection_and_stability(project):
    a,b = build_snapshot(project),build_snapshot(project)
    previous = json.loads((project / PREDECESSOR_PATH).read_bytes())
    assert a["state"] == b["state"] and a["produced_record_ids"] == b["produced_record_ids"]
    assert a["snapshot_id"] != b["snapshot_id"]
    assert a["unresolved"] == previous["unresolved"] and len(a["unresolved"]) == 79
    assert a["state"]["approval_requirements"] == previous["state"]["approval_requirements"]
    assert len(a["state"]["approval_requirements"]) == 5
    assert all(g["status"] == "pending" for g in a["state"]["approval_requirements"])
    assert a["status"] == "partial" and a["decisions"] == []
    for r in a["state"]["options"]:
        assert r["selected"] is False and r["assessment_status"] == "not-yet-tested"
        assert r["authorization_status"] == "pending" and "feasibility" not in r
        assert set(r["unresolved_ids"]) == {u["id"] for u in a["unresolved"]}
        for c in r["conditions"]:
            assert c["values"]["satisfied"] is None


@pytest.mark.parametrize("field", ["options", "rejected_early"])
def test_schema_requires_arrays(project, field):
    s = build_snapshot(project); del s["state"][field]
    with pytest.raises(ValidationError):
        validate_snapshot(s, project)


@pytest.mark.parametrize("mutation", ["total", "allowance", "ancestor-owner", "ancestor-hash", "observation", "quote-date", "quote-notes", "condition", "approval", "unresolved", "winner", "feasibility", "run", "predecessor"])
def test_semantic_tampering_rejected(project, mutation):
    s = deepcopy(build_snapshot(project)); state=s["state"]
    if mutation == "total": state["options"][0]["planning_total"] = "429000"
    elif mutation == "allowance": state["options"][0]["retained_allowances"]["contingency"] = "0"
    elif mutation == "ancestor-owner": state["ancestor_references"][0]["snapshot_path"] = PREDECESSOR_PATH
    elif mutation == "ancestor-hash": state["ancestor_references"][0]["snapshot_sha256"] = "sha256:" + "0"*64
    elif mutation == "observation": state["quote_evidence"][0]["source_observation"]["locator"]["value"] = "invented"
    elif mutation == "quote-date": state["quote_evidence"][0]["values"]["available_date"] = "2026-10-24"
    elif mutation == "quote-notes": state["quote_evidence"][6]["values"]["notes"] = "hearing loop included"
    elif mutation == "condition": state["rejected_early"][2]["conditions"][0]["values"]["satisfied"] = True
    elif mutation == "approval": state["approval_requirements"][0]["status"] = "approved"
    elif mutation == "unresolved": s["unresolved"].pop()
    elif mutation == "winner": state["options"][0]["selected"] = True
    elif mutation == "feasibility": state["options"][0]["feasibility"] = "feasible"
    elif mutation == "run": s["run_id"] = "other-run"
    else: s["predecessor"]["sha256"] = "sha256:" + "0"*64
    with pytest.raises(ValueError):
        validate_snapshot(s, project)


@pytest.mark.parametrize("path", [PREDECESSOR_PATH, "deliverables/snapshots/03-constraint-model.json", "deliverables/snapshots/02-source-capture.json", "evidence/originals/Project C — Vendor Quotes.xlsx", "interviews/project-c-event-coordination-20261016-1954.md"])
def test_tampered_inputs_rejected(project, path):
    p=project/path; p.write_bytes(p.read_bytes()+b"\n")
    with pytest.raises(ValueError):
        build_snapshot(project)


def test_missing_source_rejected(project):
    (project/"evidence/originals/Project C — Vendor Quotes.xlsx").unlink()
    with pytest.raises(FileNotFoundError):
        build_snapshot(project)


def test_exclusive_writer_only_in_temporary_project(project):
    target,digest = write_snapshot(project)
    content=target.read_bytes()
    assert digest == hash_bytes(content)
    validate_snapshot(json.loads(content), project)
    with pytest.raises(FileExistsError):
        write_snapshot(project)
    assert target.read_bytes() == content
