"""Stage 3 checks use preserved inputs copied into temporary project roots."""

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import shutil

from jsonschema import ValidationError
import pytest

from event_coordination.constraint_sources import validate_dependencies
from event_coordination.sources import hash_bytes
from event_coordination.stages.constraints import (
    CATEGORIES, OUTPUT, PREDECESSOR_HASH, PREDECESSOR_PATH, build_snapshot, write_snapshot,
)
from event_coordination.validation import validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Stage 3 must not retrieve sources")
    monkeypatch.setattr("socket.socket.connect", deny)


@pytest.fixture
def project(tmp_path):
    for directory in ["interviews", "evidence/originals", "evidence/captures"]:
        shutil.copytree(ROOT / directory, tmp_path / directory)
    shutil.copyfile(ROOT / "snapshot.schema.json", tmp_path / "snapshot.schema.json")
    destination = tmp_path / "deliverables/snapshots"
    destination.mkdir(parents=True)
    for name in ["01-scope-and-approval-gates.json", "02-source-capture.json"]:
        shutil.copyfile(ROOT / "deliverables/snapshots" / name, destination / name)
    return tmp_path


def index(snapshot):
    return {r["id"]: r for category in (*CATEGORIES, "source_facts", "approval_requirements")
            for r in snapshot["state"][category]}


def test_schema_chain_lineage_and_no_writes(project):
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    s = build_snapshot(project)
    validate_snapshot(s, project)
    previous = json.loads((project / PREDECESSOR_PATH).read_bytes())
    assert s["run_id"] == previous["run_id"] == "988f5ccf-4aeb-44d7-984d-777b1a2412e1"
    assert s["predecessor"]["snapshot_id"] == previous["snapshot_id"]
    assert s["predecessor"]["sha256"] == hash_bytes(before[project / PREDECESSOR_PATH]) == PREDECESSOR_HASH
    assert s["snapshot_id"] != previous["snapshot_id"]
    assert s["sequence"] == 3 and s["stage"] == "constraint-model"
    assert s["created_at"] != s["state"]["business_clock"]
    assert set(s["consumed_record_ids"]) <= set(previous["produced_record_ids"])
    assert set(s["produced_record_ids"]) == set(index(s))
    assert len(s["produced_record_ids"]) == len(set(s["produced_record_ids"]))
    for record in index(s).values():
        assert record["evidence_ids"]
        assert set(record["evidence_ids"]) <= set(s["consumed_record_ids"])
    assert all(p.read_bytes() == content for p, content in before.items())
    assert not (project / OUTPUT).exists()


def test_budget_fields_keep_distinct_meanings(project):
    records = index(build_snapshot(project))
    ceiling = records["hc-budget-total"]["rule"]
    assert ceiling["value"] == "520000" and ceiling["unit"] == "TWD"
    catering = records["fact-budget-catering"]
    assert catering["values"]["planned_amount_twd"] == "115000.0"
    assert catering["values"]["approval_limit_twd"] == "135000.0"
    assert catering["values"]["committed_amount_twd"] == "0.0"
    assert catering["source_values"][0]["original_cell_values"]["B3"] == "115000.0"
    assert catering["units"]["planned_amount_twd"] == "TWD"
    authorization = records["hc-budget-authorization-catering"]["rule"]
    assert authorization["authorization"] == "required-for-all-spending"
    assert authorization["approval_limit_role"] == "explicit-owner-exception-threshold"
    assert "hc-budget-total" in records["hc-budget-authorization-catering"]["depends_on_record_ids"]
    variance = records["conflict-allocation-Q-004"]
    price = Decimal(records["fact-quote-Q-004"]["values"]["quote_amount_twd"])
    assert Decimal(catering["values"]["planned_amount_twd"]) < price < Decimal(catering["values"]["approval_limit_twd"])
    assert variance["conflict_kind"] == "potential-allocation-variance"


def test_attendance_units_forecast_and_overlap_preserved(project):
    s = build_snapshot(project); records = index(s)
    forecast = records["fact-signal-SIG-005"]
    assert forecast["interpretation"] == "forecast-estimate"
    assert forecast["values"]["value"] == "35.0" and forecast["units"]["value"] == "people"
    assert forecast["values"]["confidence"] == "medium"
    assert forecast["values"]["observed_at"] == "2026-08-26"
    assert forecast["source_values"][0]["original_cell_values"]["G6"] == "46260.0"
    assert records["fact-signal-SIG-011"]["units"]["value"] == "meals"
    assert "hc-nonadditive-needs" in records["hc-response-SIG-013"]["depends_on_record_ids"]
    assert records["hc-response-SIG-013"]["rule"]["fulfilled"] is None
    assert records["hc-success-criteria"]["rule"]["headcount_discount_authorized"] is False
    assert s["state"]["assumptions"] == []
    assert all("final_headcount" not in r for r in records.values())


def test_timing_prerequisites_priorities_and_deadline(project):
    records = index(build_snapshot(project))
    walkthrough = records["hc-CAL-006"]
    assert walkthrough["rule"]["requires_before"] == {
        "record_id": "gate-venue-confirmation", "before": "2026-09-25T14:00:00+08:00"}
    assert "gate-venue-confirmation" in walkthrough["depends_on_record_ids"]
    assert records["gate-operations"]["deadline"] == "2026-09-04T17:00:00+08:00"
    assert records["fact-operations-deadline"]["source_values"][0]["line_start"] == 790
    assert records["hc-CAL-001"]["rule"]["source_priority"] == "hard"
    assert records["pref-CAL-002"]["rule"]["source_priority"] == "soft"
    assert records["pref-CAL-007"]["rule"]["notes"] == "Remote backup acceptable"
    assert records["hc-setup-teardown"]["rule"]["mandatory_extra_buffer"] is None
    assert records["hc-setup-teardown"]["rule"]["individual_vendor_durations"] is None


def test_programme_accessibility_and_conditional_quotes(project):
    s = build_snapshot(project); records = index(s)
    demos = records["hc-programme-demos"]["rule"]
    assert demos["demo_ids"] == [f"DEMO-{i:02}" for i in range(1, 13)]
    assert demos["presentation_minutes"] == "10" and demos["changeover_minutes"] == "3"
    assert demos["attendance_effect"] == "no-additional-people"
    assert len([r for r in s["state"]["hard_constraints"] if r["id"].startswith("hc-accessibility-")]) == 5
    assert records["fact-quote-Q-008"]["values"]["status"] == "conditional"
    assert records["hc-quote-prerequisites-Q-008"]["rule"]["applies_if"] == {"quote_proposed": "Q-008"}
    assert records["hc-quote-prerequisites-Q-008"]["rule"]["satisfied"] is None
    assert records["conflict-Q007-hearing-loop"]["conflict_kind"] == "conditional"
    assert records["fact-quote-Q-001"]["values"]["valid_until"] == "2026-09-05"
    assert records["fact-quote-Q-001"]["source_values"][0]["original_cell_values"]["H2"] == "46270.0"
    assert records["hc-quote-Q-001"]["rule"]["expiry_cutoff_time"] is None
    assert records["hc-security-readiness"]["rule"]["selected_vendor"] is None


def test_every_observation_and_inherited_issue_remains_traceable(project):
    s = build_snapshot(project); previous = json.loads((project / PREDECESSOR_PATH).read_bytes())
    records = index(s)
    for capture in previous["state"]["sources"]:
        for observation in capture["observations"]:
            fact = records["fact-evidence-" + observation["id"]]
            assert fact["source_values"] == [observation]
            assert fact["provenance"][0]["sha256"] == capture["content_hash"]
            assert fact["provenance"][0]["retrieval_status"] == capture["retrieval_status"]
    for issue in previous["unresolved"]:
        carried = records["unknown-inherited-" + issue["id"]]
        assert carried["original_detail"] == issue
        assert carried["evidence_ids"] == [issue["id"]]
        assert carried["resolution"] == "unresolved"
    assert s["unresolved"] == s["state"]["unknowns"] + s["state"]["conflicts"]
    assert s["status"] == "partial" and s["decisions"] == []
    assert all(g["status"] == "pending" for g in s["state"]["approval_requirements"])
    assert s["state"]["audience"] == "internal-evidence-review"
    assert "hc-privacy" in records


def test_stable_semantic_ids_and_dependencies(project):
    a, b = build_snapshot(project), build_snapshot(project)
    assert a["snapshot_id"] != b["snapshot_id"]
    assert a["produced_record_ids"] == b["produced_record_ids"]
    assert a["state"] == b["state"]
    validate_dependencies(list(index(a).values()))
    assert all(a["state"]["coverage"].values())


@pytest.mark.parametrize("dependencies", [["missing"], ["self"]])
def test_dependency_validator_rejects_missing_and_cyclic_links(dependencies):
    with pytest.raises(ValueError):
        validate_dependencies([{"id": "self", "depends_on_record_ids": dependencies}])


@pytest.mark.parametrize("mutation", ["evidence", "approval", "forecast", "dependency", "assumption", "unknown", "selection"])
def test_unsupported_semantic_changes_rejected(project, mutation):
    s = deepcopy(build_snapshot(project))
    if mutation == "evidence":
        s["state"]["hard_constraints"][0]["evidence_ids"] = ["nonexistent"]
    elif mutation == "approval":
        s["state"]["approval_requirements"][0]["status"] = "approved"
    elif mutation == "forecast":
        record = next(r for r in s["state"]["source_facts"] if r["id"] == "fact-signal-SIG-005")
        record["values"]["confidence"] = "0.8"
    elif mutation == "dependency":
        s["state"]["hard_constraints"][0]["depends_on_record_ids"] = ["missing"]
    elif mutation == "assumption":
        s["state"]["assumptions"] = [{"id": "invented", "summary": "Assume free tax", "evidence_ids": []}]
    elif mutation == "unknown":
        s["state"]["unknowns"] = []
    else:
        s["state"]["selected_vendor"] = "invented"
    with pytest.raises(ValueError):
        validate_snapshot(s, project)


@pytest.mark.parametrize("field", ["hard_constraints", "preferences", "assumptions", "unknowns", "conflicts"])
def test_required_categories_enforced_by_unchanged_schema(project, field):
    s = build_snapshot(project)
    del s["state"][field]
    with pytest.raises(ValidationError):
        validate_snapshot(s, project)


@pytest.mark.parametrize("path", [PREDECESSOR_PATH, "evidence/originals/Project C — Budget.xlsx",
                                 "interviews/project-c-event-coordination-20261016-1954.md"])
def test_tampered_inputs_rejected(project, path):
    target = project / path
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        build_snapshot(project)


def test_missing_evidence_rejected(project):
    (project / "evidence/originals/Project C — Attendee Signals.xlsx").unlink()
    with pytest.raises(FileNotFoundError):
        build_snapshot(project)


def test_writer_roundtrip_and_overwrite_refusal_only_in_temporary_project(project):
    target, digest = write_snapshot(project)
    content = target.read_bytes()
    assert digest == hash_bytes(content)
    validate_snapshot(json.loads(content), project)
    with pytest.raises(FileExistsError):
        write_snapshot(project)
    assert target.read_bytes() == content
