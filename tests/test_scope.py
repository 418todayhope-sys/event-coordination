"""Focused Stage 1 tests; generated files remain in pytest temporary directories."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from jsonschema import ValidationError

from event_coordination.sources import hash_bytes
from event_coordination.stages.scope import (
    BRIEF, DEADLINE, FOLLOWUP, ORIGINAL, OUTPUT, build_snapshot, write_snapshot,
)
from event_coordination.validation import validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def project(tmp_path):
    for relative in ["snapshot.schema.json", BRIEF, ORIGINAL, FOLLOWUP]:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path


def test_real_evidence_builds_valid_partial_snapshot(project):
    snapshot = build_snapshot(project, "test-run")
    validate_snapshot(snapshot, project)
    assert snapshot["run_id"] == "test-run"
    assert snapshot["status"] == "partial"
    assert snapshot["unresolved"][0]["owner"] is None
    assert snapshot["state"]["decision_deadline"] == DEADLINE
    assert snapshot["created_at"] != snapshot["state"]["business_clock"]
    deadline_evidence = next(r for r in snapshot["state"]["evidence_records"] if r["id"] == "ev-deadline")
    assert deadline_evidence["path"] == FOLLOWUP
    assert deadline_evidence["line_start"] == 790
    assert all(a["status"] == "pending" for a in snapshot["state"]["approval_requirements"])


@pytest.mark.parametrize("deadline", [None, "", "unknown", "2026-09-04", "2026-09-04T17:00:00"])
def test_format_checker_rejects_invalid_deadlines_even_when_blocked(project, deadline):
    snapshot = build_snapshot(project)
    snapshot["status"] = "blocked"
    snapshot["state"]["decision_deadline"] = deadline
    with pytest.raises(ValidationError):
        validate_snapshot(snapshot, project)


def test_missing_deadline_rejected(project):
    snapshot = build_snapshot(project)
    del snapshot["state"]["decision_deadline"]
    with pytest.raises(ValidationError):
        validate_snapshot(snapshot, project)


def test_business_clock_cannot_substitute_for_deadline(project):
    snapshot = build_snapshot(project)
    snapshot["state"]["decision_deadline"] = snapshot["state"]["business_clock"]
    with pytest.raises(ValueError, match="Unsupported Operations deadline"):
        validate_snapshot(snapshot, project)


def test_altered_original_bytes_invalidate_provenance(project):
    snapshot = build_snapshot(project)
    with (project / BRIEF).open("ab") as stream:
        stream.write(b"\n")
    with pytest.raises(ValueError, match="Evidence hash"):
        validate_snapshot(snapshot, project)


def test_changed_deadline_source_prevents_generation(project):
    path = project / FOLLOWUP
    path.write_text(path.read_text().replace("September 4, 2026", "September 5, 2026"))
    with pytest.raises(ValueError, match="Evidence no longer matches"):
        write_snapshot(project)
    assert not (project / OUTPUT).exists()


@pytest.mark.parametrize("mutation", ["reference", "produced", "approval", "scope", "owners"])
def test_semantic_validation_rejects_corrupt_records(project, mutation):
    snapshot = deepcopy(build_snapshot(project))
    if mutation == "reference":
        snapshot["unresolved"][0]["evidence_ids"] = ["nonexistent"]
    elif mutation == "produced":
        snapshot["produced_record_ids"].pop()
    elif mutation == "approval":
        snapshot["state"]["approval_requirements"][0]["status"] = "approved"
    elif mutation == "scope":
        snapshot["state"]["scope_records"][1]["evidence_ids"] = ["ev-objective"]
    else:
        snapshot["state"]["owners"] = ["Invented owner"]
        snapshot["state"]["scope_records"][2]["value"] = ["Invented owner"]
    with pytest.raises(ValueError):
        validate_snapshot(snapshot, project)


def test_write_round_trip_hash_and_refuse_overwrite(project):
    path, digest = write_snapshot(project, "retained-run")
    content = path.read_bytes()
    assert digest == hash_bytes(content)
    saved = json.loads(content)
    validate_snapshot(saved, project)
    assert saved["predecessor"] is None
    assert saved["consumed_record_ids"] == []
    assert saved["run_id"] == "retained-run"
    with pytest.raises(FileExistsError):
        write_snapshot(project)
    assert path.read_bytes() == content


def test_cli_generation_and_overwrite_failure(project):
    command = [sys.executable, "-B", "-m", "event_coordination.cli", "stage1",
               "--project-root", str(project), "--run-id", "cli-run"]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "Validated Stage 1 draft" in result.stdout
    assert json.loads((project / OUTPUT).read_text())["run_id"] == "cli-run"
    again = subprocess.run(command, capture_output=True, text=True)
    assert again.returncode == 1
    assert "Stage 1 failed" in again.stderr
