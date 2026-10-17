"""Stage 4 regression and evidence checks; writes are confined to temporary roots."""

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import shutil

from jsonschema import ValidationError
import pytest

from event_coordination.constraint_sources import validate_dependencies
from event_coordination.sources import hash_bytes
from event_coordination.stages.baseline import (
    CATEGORIES, OUTPUT, PREDECESSOR_HASH, PREDECESSOR_PATH, UPSTREAM_CATEGORIES,
    build_snapshot, write_snapshot,
)
from event_coordination.validation import validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Stage 4 must not retrieve sources")
    monkeypatch.setattr("socket.socket.connect", deny)


@pytest.fixture
def project(tmp_path):
    for directory in ["interviews", "evidence/originals", "evidence/captures"]:
        shutil.copytree(ROOT / directory, tmp_path / directory)
    shutil.copyfile(ROOT / "snapshot.schema.json", tmp_path / "snapshot.schema.json")
    destination = tmp_path / "deliverables/snapshots"
    destination.mkdir(parents=True)
    for name in ["01-scope-and-approval-gates.json", "02-source-capture.json", "03-constraint-model.json"]:
        shutil.copyfile(ROOT / "deliverables/snapshots" / name, destination / name)
    return tmp_path


def index(snapshot):
    return {r["id"]: r for c in CATEGORIES for r in snapshot["state"][c]}


def previous(project):
    return json.loads((project / PREDECESSOR_PATH).read_bytes())


def test_schema_lineage_provenance_and_no_writes(project):
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    s = build_snapshot(project)
    validate_snapshot(s, project)
    p = previous(project)
    upstream = {r["id"]: r for c in UPSTREAM_CATEGORIES for r in p["state"][c]}
    assert s["run_id"] == p["run_id"] == "988f5ccf-4aeb-44d7-984d-777b1a2412e1"
    assert s["predecessor"] == {"path": PREDECESSOR_PATH, "snapshot_id": p["snapshot_id"], "sha256": PREDECESSOR_HASH}
    assert PREDECESSOR_HASH == hash_bytes(before[project / PREDECESSOR_PATH])
    assert s["snapshot_id"] != p["snapshot_id"] and s["sequence"] == 4
    assert datetime.fromisoformat(s["created_at"]).utcoffset().total_seconds() == 0
    assert s["created_at"] != s["state"]["business_clock"]
    assert s["state"]["business_clock"] == p["state"]["business_clock"]
    consumed = set(s["consumed_record_ids"])
    assert consumed <= set(p["produced_record_ids"])
    for r in index(s).values():
        assert r["evidence_ids"] and set(r["evidence_ids"]) <= consumed
        assert r["source_records"] == [upstream[e] for e in r["evidence_ids"]]
    produced = list(index(s)) + [r["id"] for r in s["unresolved"] + s["state"]["approval_requirements"]]
    assert set(s["produced_record_ids"]) == set(produced)
    assert len(produced) == len(set(produced))
    assert all(p.read_bytes() == b for p, b in before.items())
    assert not (project / OUTPUT).exists()


def test_attendance_components_uncertainty_and_nonadditive_needs(project):
    records = index(build_snapshot(project))
    for name, value in [("registered", 180), ("required-onsite", 30), ("core", 210), ("planning-demand", 245)]:
        assert Decimal(records["baseline-headcount-" + name]["values"]["value"]) == value
    forecast = records["baseline-headcount-forecast"]
    assert Decimal(forecast["values"]["value"]) == 35
    assert forecast["interpretation"] == "forecast-estimate"
    assert forecast["values"]["confidence"] == "medium"
    assert forecast["values"]["observed_at"] == "2026-08-26"
    overlap = records["baseline-headcount-overlap"]
    assert overlap["values"]["additional_people"] == 0
    for n in range(6, 14):
        need = records[f"baseline-needs-SIG-{n:03}"]
        assert need["adds_people"] is False and need["fulfillment"] == "not-evaluated"
    assert records["baseline-needs-SIG-011"]["units"]["value"] == "meals"
    target = records["baseline-headcount-success-target"]
    assert target["values"]["check_in_target"] == "80"
    assert target["source_records"][1]["rule"]["headcount_discount_authorized"] is False


def test_budget_meanings_and_derivations(project):
    records = index(build_snapshot(project))
    expected = {"venue": (155000, 180000), "catering": (115000, 135000),
                "accessibility": (65000, 80000), "production": (85000, 100000),
                "communications": (25000, 30000), "security": (25000, 35000), "contingency": (40000, 50000)}
    for category, (planned, limit) in expected.items():
        r = records["baseline-budget-category-" + category]
        assert Decimal(r["values"]["planned_amount_twd"]) == planned
        assert Decimal(r["values"]["approval_limit_twd"]) == limit
        assert Decimal(r["values"]["committed_amount_twd"]) == 0
        assert r["authorization_status"] == "pending"
        assert r["source_records"][0]["source_values"][0]["original_cell_values"]
    for name, value in [("ceiling", 520000), ("planned-total", 510000), ("committed-total", 0),
                        ("unallocated", 10000), ("ceiling-less-commitments", 520000)]:
        assert Decimal(records["baseline-budget-" + name]["values"]["value"]) == value
    assert records["baseline-budget-authorization"]["values"] == {"authorization_status": "pending", "authorized_amount": None}
    # Independently evaluate every weighted formula against its preserved inputs.
    for r in records.values():
        if r.get("derivation", {}).get("operation") != "weighted-sum":
            continue
        upstream = {v["id"]: v for v in r["source_records"]}
        result = sum(Decimal(upstream[i["record_id"]]["values"][i["field"].split(".")[1]]) * i["coefficient"]
                     for i in r["derivation"]["inputs"])
        assert result == Decimal(r["values"]["value"])


def test_calendar_programme_and_unknown_durations(project):
    s = build_snapshot(project); records = index(s)
    for n in range(1, 9):
        r = records[f"baseline-schedule-CAL-{n:03}"]
        assert r["values"] == r["source_records"][0]["values"]
        assert datetime.fromisoformat(r["values"]["start_at"]).utcoffset().total_seconds() == 8 * 3600
        assert r["timezone"] == "Asia/Taipei"
    assert records["baseline-schedule-CAL-001"]["values"]["priority"] == "hard"
    assert records["baseline-schedule-CAL-002"]["values"]["priority"] == "soft"
    walkthrough = records["baseline-schedule-CAL-006"]
    assert walkthrough["prerequisites"] == {"record_id": "gate-venue-confirmation", "before": "2026-09-25T14:00:00+08:00"}
    assert records["baseline-schedule-CAL-005"]["temporal_kind"] == "deadline-instant"
    opening = records["baseline-schedule-CAL-001"]
    assert opening["prerequisites"]["required_by"] == opening["values"]["start_at"]
    assert opening["prerequisites"]["applicability"] == "specified-base-bundles-on-2026-10-17"
    assert opening["depends_on_record_ids"] == ["baseline-schedule-readiness"]
    assert records["baseline-schedule-readiness"]["depends_on_record_ids"] == ["baseline-schedule-access-windows"]
    deadline = records["baseline-schedule-operations-deadline"]
    assert deadline["values"]["value"] == "2026-09-04T17:00:00+08:00"
    assert deadline["source_records"][0]["source_values"][0]["line_start"] == 790
    windows = records["baseline-schedule-access-windows"]["values"]
    assert windows["mandatory_extra_buffer"] is None and windows["individual_vendor_durations"] is None
    assert records["baseline-schedule-readiness"]["values"]["applies_on"] == "2026-10-17"
    roster = records["baseline-programme-demos"]["values"]
    assert roster["demo_ids"] == [f"DEMO-{n:02}" for n in range(1, 13)]
    assert roster["attendance_effect"] == "no-additional-people"
    duration = records["baseline-programme-duration"]["values"]
    assert duration == {"presentation": "120", "changeover": "36", "total": "156"}


def test_uncertainty_pending_gates_conditions_and_stable_ids(project):
    a, b = build_snapshot(project), build_snapshot(project)
    p = previous(project)
    assert a["state"] == b["state"] and a["produced_record_ids"] == b["produced_record_ids"]
    assert a["snapshot_id"] != b["snapshot_id"]
    assert a["unresolved"] == p["unresolved"] and len(a["unresolved"]) == 79
    gates = a["state"]["approval_requirements"]
    assert gates == p["state"]["approval_requirements"] and len(gates) == 5
    assert all(r["status"] == "pending" for r in gates)
    assert a["status"] == "partial" and a["decisions"] == []
    assert a["state"]["assumptions"] == a["state"]["planning_choices"] == []
    assert a["state"]["output_status"] == "draft"
    records = index(a)
    mandatory = [r for r in records.values() if r["id"].startswith("baseline-accessibility-")
                 and r.get("basis") == "stakeholder-rule"]
    assert len(mandatory) == 5
    for qid in ("Q-004", "Q-008", "Q-010"):
        r = records["baseline-service-condition-" + qid]
        assert r["values"]["applies_if"] == {"quote_proposed": qid}
        assert r["values"]["satisfied"] is None
    assert all(r["verification"] == "inherits-upstream-limitations" for r in records.values())
    graph = {r["id"]: r for c in UPSTREAM_CATEGORIES for r in p["state"][c]}
    graph.update(records)
    validate_dependencies(list(graph.values()))


@pytest.mark.parametrize("category", CATEGORIES)
def test_required_arrays_enforced(project, category):
    s = build_snapshot(project)
    del s["state"][category]
    with pytest.raises(ValidationError):
        validate_snapshot(s, project)


@pytest.mark.parametrize("mutation", ["arithmetic", "evidence", "dependency", "forecast", "approval", "unknown", "date", "selection", "fulfillment", "predecessor", "run"])
def test_unsupported_changes_rejected(project, mutation):
    s = deepcopy(build_snapshot(project)); records = index(s)
    if mutation == "arithmetic":
        records["baseline-headcount-planning-demand"]["values"]["value"] = "300"
    elif mutation == "evidence":
        records["baseline-budget-ceiling"]["evidence_ids"] = ["missing"]
    elif mutation == "dependency":
        records["baseline-programme-demos"]["depends_on_record_ids"] = ["baseline-programme-duration"]
    elif mutation == "forecast":
        records["baseline-headcount-forecast"]["interpretation"] = "confirmed"
    elif mutation == "approval":
        s["state"]["approval_requirements"][0]["status"] = "approved"
    elif mutation == "unknown":
        s["unresolved"].pop()
    elif mutation == "date":
        s["state"]["selected_date"] = "2026-10-17"
    elif mutation == "selection":
        s["state"]["selected_vendor"] = "Q-003"
    elif mutation == "fulfillment":
        records["baseline-needs-SIG-013"]["fulfillment"] = "verified"
    elif mutation == "predecessor":
        s["predecessor"]["sha256"] = "sha256:" + "0" * 64
    else:
        s["run_id"] = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(ValueError):
        validate_snapshot(s, project)


@pytest.mark.parametrize("path", [PREDECESSOR_PATH, "evidence/originals/Project C — Attendee Signals.xlsx",
                                 "interviews/project-c-event-coordination-20261016-2056.md"])
def test_tampered_inputs_rejected(project, path):
    p = project / path
    p.write_bytes(p.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        build_snapshot(project)


def test_missing_evidence_rejected(project):
    (project / "evidence/originals/Project C — Budget.xlsx").unlink()
    with pytest.raises(FileNotFoundError):
        build_snapshot(project)


def test_writer_roundtrip_and_refusal_in_temporary_root(project):
    target, digest = write_snapshot(project)
    content = target.read_bytes()
    assert digest == hash_bytes(content)
    validate_snapshot(json.loads(content), project)
    with pytest.raises(FileExistsError):
        write_snapshot(project)
    assert target.read_bytes() == content
