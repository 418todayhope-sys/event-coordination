"""Execute the real CLI and real stage writers, exclusively in temporary roots."""

import csv
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import UUID

from icalendar import Calendar
from jsonschema import Draft202012Validator, FormatChecker
import pytest

from event_coordination import pipeline
from event_coordination.run_contract import (
    InputSpec, RunSession, activate_run, current_run, new_run_metadata, pin_inputs,
    read_predecessor, LEGACY_RUN_ID,
)
from event_coordination.sources import hash_bytes
from event_coordination.stages import scope, drafts
from event_coordination.validation import validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


def cli(source, destination):
    return subprocess.run([
        sys.executable, "-B", "-m", "event_coordination.cli", "run-stages",
        "--source-root", str(source), "--workspace", str(destination), "--through-stage", "8"],
        cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True, capture_output=True, timeout=180)


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    root = tmp_path_factory.mktemp("real-cli-pipeline") / "run"
    before = pipeline._inputs(ROOT)
    process = cli(ROOT, root)
    assert process.returncode == 0, process.stderr
    assert process.stderr == ""
    report = json.loads(process.stdout)
    assert pipeline._inputs(ROOT) == before
    return root, report


def test_real_cli_creates_new_eight_stage_chain_and_four_drafts(generated):
    root, report = generated
    assert report["scope"] == "stages-01-through-08" and report["validation_status"] == "valid"
    assert report["status"] == "partial" and UUID(report["run_id"]).version == 4
    assert report["run_id"] != LEGACY_RUN_ID and len(report["snapshots"]) == 8
    assert len({s["snapshot_id"] for s in report["snapshots"]}) == 8
    schema = json.loads((ROOT / "snapshot.schema.json").read_bytes())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    previous = None
    old_ids = {json.loads((ROOT / m.OUTPUT).read_bytes())["snapshot_id"] for m in pipeline.STAGE_MODULES}
    for sequence, entry in enumerate(report["snapshots"], 1):
        data = (root / entry["path"]).read_bytes()
        snapshot = json.loads(data)
        validator.validate(snapshot)
        assert entry["sha256"] == hash_bytes(data)
        assert snapshot["run_id"] == report["run_id"] and snapshot["sequence"] == sequence
        assert snapshot["snapshot_id"] == entry["snapshot_id"] and snapshot["snapshot_id"] not in old_ids
        if previous is None:
            assert snapshot["predecessor"] is None and snapshot["consumed_record_ids"] == []
            assert snapshot["state"]["run_metadata"]["run_id"] == report["run_id"]
        else:
            assert snapshot["predecessor"] == {k: previous[k] for k in ("path", "sha256", "snapshot_id")}
        previous = entry
    assert len(report["artifacts"]) == 4
    for entry in report["artifacts"]:
        assert hash_bytes((root / entry["path"]).read_bytes()) == entry["sha256"]
    assert not (root / ".git").exists() and not (root / ".entire").exists()
    assert not (root / "deliverables/snapshots/09-publication-validation.json").exists()
    assert not (root / "deliverables/history").exists()


def test_generated_contents_preserve_evidence_and_assignment_boundaries(generated):
    root, report = generated
    s2 = json.loads((root / pipeline.capture.OUTPUT).read_bytes())
    old2 = json.loads((ROOT / pipeline.capture.OUTPUT).read_bytes())
    assert s2["state"]["sources"] == old2["state"]["sources"]
    assert s2["state"]["inventory_counts"] == {"source_identities": 7, "capture_attempts": 9,
                                               "evidence_files": 8, "observations": 55}
    s8 = json.loads((root / drafts.OUTPUT).read_bytes())
    old8 = json.loads((ROOT / drafts.OUTPUT).read_bytes())
    assert s8["unresolved"] == old8["unresolved"] and report["unresolved_count"] == 88
    assert s8["state"]["approval_requirements"] == old8["state"]["approval_requirements"]
    assert s8["state"]["retained_early_screening"] == old8["state"]["retained_early_screening"]
    assert report["pending_approval_count"] == 5 and report["retained_screening_count"] == 4
    assert s8["state"]["draft_contract_version"] == "assignment-drafts/1"
    assert s8["state"]["external_actions_authorized"] is report["external_actions_authorized"] is False
    assert s8["state"]["learner_decisions"] == []
    reader = csv.DictReader(io.StringIO((root / drafts.ARTIFACT_PATHS[0]).read_text()))
    assert {"option_id", "quote_ids", "planning_people", "cost_twd", "currency", "feasibility",
            "availability_status", "evidence_ids", "tradeoffs", "unresolved", "approval_status"} <= set(reader.fieldnames)
    candidates = [r for r in reader if r["row_type"] == "candidate"]
    assert [r["cost_twd"] for r in candidates] == ["494000", "512000"]
    assert all(r["feasibility"] == "conditional" and r["approval_status"] == "pending" for r in candidates)
    calendar = Calendar.from_ical((root / drafts.ARTIFACT_PATHS[2]).read_bytes())
    assert str(calendar["METHOD"]) == "PUBLISH" and len(calendar.walk("VEVENT")) == 35
    assert all(str(e["STATUS"]) == "TENTATIVE" and e.get("ATTENDEE") is None for e in calendar.walk("VEVENT"))
    old_events = Calendar.from_ical((ROOT / drafts.ARTIFACT_PATHS[2]).read_bytes()).walk("VEVENT")
    assert {str(e["UID"]) for e in old_events}.isdisjoint({str(e["UID"]) for e in calendar.walk("VEVENT")})
    assert (root / drafts.ARTIFACT_PATHS[3]).read_text().count("UNSENT DRAFT") == 5


def test_saved_cli_run_semantics_revalidate_using_reported_pins(generated):
    root, report = generated
    first = json.loads((root / scope.OUTPUT).read_bytes())
    schema_pin = pin_inputs(root, (InputSpec("run-schema", "snapshot.schema.json", "schema", drafts.SCHEMA_HASH),))[0]
    session = RunSession(root, first["state"]["run_metadata"], schema_pin)
    with activate_run(session):
        for entry in report["snapshots"]:
            assert session.register(entry["path"], entry["sha256"])["snapshot_id"] == entry["snapshot_id"]
    assert current_run(root) is None
    # Outside a deliberate run context the original historical pin still applies.
    with pytest.raises(ValueError, match="predecessor hash"):
        validate_snapshot(json.loads((root / pipeline.capture.OUTPUT).read_bytes()), root)


def test_second_actual_cli_execution_has_distinct_run_and_snapshot_ids(generated, tmp_path):
    _, first = generated
    result = cli(ROOT, tmp_path / "second")
    assert result.returncode == 0, result.stderr
    second = json.loads(result.stdout)
    assert first["run_id"] != second["run_id"]
    assert {s["snapshot_id"] for s in first["snapshots"]}.isdisjoint({s["snapshot_id"] for s in second["snapshots"]})


def test_cli_refuses_existing_workspace_without_changing_it(generated):
    root, _ = generated
    before = {str(p.relative_to(root)): hash_bytes(p.read_bytes()) for p in root.rglob("*") if p.is_file()}
    result = cli(ROOT, root)
    assert result.returncode != 0 and not result.stdout
    assert before == {str(p.relative_to(root)): hash_bytes(p.read_bytes()) for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def source_copy(tmp_path):
    root = tmp_path / "source"; root.mkdir()
    for directory in ("evidence", "interviews"):
        shutil.copytree(ROOT / directory, root / directory)
    shutil.copyfile(ROOT / "snapshot.schema.json", root / "snapshot.schema.json")
    return root


@pytest.mark.parametrize("problem", ["missing", "tampered", "symlink", "schema"])
def test_bad_sources_fail_before_workspace_creation(source_copy, tmp_path, problem):
    original = source_copy / "evidence/originals/Project C — Vendor Quotes.xlsx"
    if problem == "missing": original.unlink()
    if problem == "tampered": original.write_bytes(b"synthetic invalid bytes")
    if problem == "symlink":
        original.unlink(); original.symlink_to(ROOT / "evidence/originals/Project C — Vendor Quotes.xlsx")
    if problem == "schema": (source_copy / "snapshot.schema.json").write_bytes(b"{}")
    result = cli(source_copy, tmp_path / "run")
    assert result.returncode != 0 and result.stdout == ""
    assert not (tmp_path / "run").exists()


def test_late_source_change_stops_and_retains_partial_run(source_copy, tmp_path, monkeypatch):
    original = scope.write_snapshot
    def changed(root):
        result = original(root)
        with (source_copy / "interviews/project-c-event-coordination-20261016-2056.md").open("ab") as stream:
            stream.write(b"\nsynthetic late mutation")
        return result
    monkeypatch.setattr(scope, "write_snapshot", changed)
    with pytest.raises(ValueError): pipeline.run_stages(source_copy, tmp_path / "run")
    assert (tmp_path / "run" / scope.OUTPUT).exists()
    assert not (tmp_path / "run" / pipeline.capture.OUTPUT).exists()
    assert current_run(tmp_path / "run") is None


def test_run_context_refuses_unregistered_and_tampered_predecessors(source_copy):
    (source_copy / "deliverables/snapshots").mkdir(parents=True)
    schema = pin_inputs(source_copy, (InputSpec("run-schema", "snapshot.schema.json", "schema", drafts.SCHEMA_HASH),))[0]
    session = RunSession(source_copy, new_run_metadata(), schema)
    reached_final = False
    with pytest.raises(ValueError, match="input_changed"):
        with activate_run(session):
            with pytest.raises(ValueError, match="unregistered"):
                read_predecessor(source_copy, scope.OUTPUT, "sha256:" + "0" * 64)
            path, digest = scope.write_snapshot(source_copy)
            session.register(scope.OUTPUT, digest)
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            with pytest.raises(ValueError): read_predecessor(source_copy, scope.OUTPUT, digest)
            path.write_bytes(original)
            with pytest.raises(ValueError): session.verify()
            reached_final = True  # Final verification must fail too, never repin.
    assert reached_final and current_run(source_copy) is None


def test_workspace_must_be_separate_and_parents_must_be_safe(source_copy, tmp_path):
    with pytest.raises(ValueError): pipeline.run_stages(source_copy, source_copy / "new-run")
    assert not (source_copy / "new-run").exists()
    alias = tmp_path / "alias"; alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError): pipeline.run_stages(source_copy, alias / "escaped-run")
    assert not (tmp_path / "escaped-run").exists()
