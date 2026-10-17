"""Offline Stage 2 integration tests; snapshot writes occur only under tmp_path."""

from copy import deepcopy
import json
from pathlib import Path
import shutil

from jsonschema import ValidationError
import pytest

from event_coordination.source_inventory import load_inventory
from event_coordination.sources import hash_bytes
from event_coordination.stages.capture import (
    OUTPUT, PREDECESSOR_HASH, PREDECESSOR_PATH, build_snapshot, write_snapshot,
)
from event_coordination.validation import validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Stage 2 assembly must not access the network")
    monkeypatch.setattr("socket.socket.connect", deny)


@pytest.fixture
def project(tmp_path):
    for directory in ["interviews", "evidence/originals", "evidence/captures"]:
        shutil.copytree(ROOT / directory, tmp_path / directory)
    shutil.copyfile(ROOT / "snapshot.schema.json", tmp_path / "snapshot.schema.json")
    target = tmp_path / PREDECESSOR_PATH
    target.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / PREDECESSOR_PATH, target)
    return tmp_path


def capture_path(project, identity):
    return next(p for p in sorted((project / "evidence/captures").glob("*.json"))
                if json.loads(p.read_bytes())["source_identity"] == identity)


def test_assembly_validates_actual_inventory_and_preserves_every_observation(project):
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    snapshot = build_snapshot(project)
    validate_snapshot(snapshot, project)
    captures, manifest = load_inventory(project)
    assert snapshot["state"]["sources"] == captures
    assert snapshot["state"]["capture_manifest"] == manifest
    assert snapshot["state"]["inventory_counts"] == {
        "source_identities": 7, "capture_attempts": 9, "evidence_files": 8, "observations": 55,
    }
    upstream = json.loads((project / PREDECESSOR_PATH).read_bytes())
    assert snapshot["run_id"] == upstream["run_id"] == "988f5ccf-4aeb-44d7-984d-777b1a2412e1"
    assert snapshot["predecessor"]["sha256"] == hash_bytes(before[project / PREDECESSOR_PATH]) == PREDECESSOR_HASH
    assert set(snapshot["consumed_record_ids"]).issubset(upstream["produced_record_ids"])
    assert snapshot["snapshot_id"] != upstream["snapshot_id"]
    produced = snapshot["produced_record_ids"]
    assert len(produced) == len(set(produced))
    for capture in captures:
        assert capture["id"] in produced
        assert all(o["id"] in produced for o in capture["observations"])
    groups = {r["source_identity"]: r for r in snapshot["state"]["source_inventory"]}
    assert len(groups["event-brief"]["capture_ids"]) == 2
    assert len(groups["official-floor-plan"]["capture_ids"]) == 2
    assert all(p.read_bytes() == b for p, b in before.items())
    assert not (project / OUTPUT).exists()  # builder and validation are read-only


def test_uncertainty_is_explicit_and_not_resolved(project):
    snapshot = build_snapshot(project)
    gaps = snapshot["unresolved"]
    categories = {r["category"] for r in gaps}
    assert {"inherited", "completeness", "historical-retrieval-time", "online_equivalence",
            "conditions", "possible_interpretations_not_resolutions", "privacy"} <= categories
    assert snapshot["status"] == "partial"
    assert snapshot["decisions"] == []
    assert snapshot["state"]["audience"] == "internal-evidence-review"
    assert snapshot["created_at"] != snapshot["state"]["business_clock"]
    assert any("Network test required" in r["summary"] or "network test required" in r["summary"]
               for r in gaps)
    assert any("programme" in r["summary"].lower() and "absent" in r["summary"].lower() for r in gaps)
    assert any(r["category"] == "inherited" and r["evidence_ids"] == ["unknown-category-owner-identities"] for r in gaps)
    failed = next(c for c in snapshot["state"]["sources"] if c["retrieval_status"] == "unavailable")
    assert failed["content_hash"] is None and failed["local_reference"] is None
    assert failed["version_metadata"]["reason"] == "ConnectError"
    assert not any(p.name in ["event-plan.md", "draft-communications.md"] for p in project.rglob("*"))


@pytest.mark.parametrize("action", ["missing", "tampered"])
def test_evidence_missing_or_tampered_prevents_assembly(project, action):
    record = json.loads(capture_path(project, "budget-allocations").read_bytes())
    evidence = project / record["local_reference"]
    if action == "missing":
        evidence.unlink()
        error = FileNotFoundError
    else:
        evidence.write_bytes(evidence.read_bytes() + b"synthetic test mutation")
        error = ValueError
    with pytest.raises(error):
        build_snapshot(project)


def test_missing_source_capture_prevents_seven_source_claim(project):
    capture_path(project, "budget-allocations").unlink()
    with pytest.raises(ValueError, match="all seven"):
        build_snapshot(project)


def test_tampered_predecessor_prevents_chain(project):
    path = project / PREDECESSOR_PATH
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="predecessor hash"):
        build_snapshot(project)


def test_metadata_bytes_are_part_of_lineage(project):
    snapshot = build_snapshot(project)
    path = capture_path(project, "budget-allocations")
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="state"):
        validate_snapshot(snapshot, project)


@pytest.mark.parametrize("field", ["consumed_record_ids", "produced_record_ids", "run_id", "unresolved", "status"])
def test_forged_lineage_and_cleared_uncertainty_rejected(project, field):
    snapshot = build_snapshot(project)
    snapshot[field] = "complete" if field == "status" else "different-run" if field == "run_id" else []
    with pytest.raises((ValueError, ValidationError)):
        validate_snapshot(snapshot, project)


def test_observations_cannot_be_rewritten_or_verification_upgraded(project):
    snapshot = build_snapshot(project)
    altered = deepcopy(snapshot)
    altered["state"]["sources"][0]["observations"][0]["id"] = "invented-observation"
    with pytest.raises(ValueError, match="state"):
        validate_snapshot(altered, project)
    altered = deepcopy(snapshot)
    altered["state"]["sources"][0]["retrieval_status"] = "retrieved"
    with pytest.raises(ValueError, match="state"):
        validate_snapshot(altered, project)


def test_duplicate_observation_ids_rejected(project):
    path = capture_path(project, "attendee-signals")
    record = json.loads(path.read_bytes())
    record["observations"][1]["id"] = record["observations"][0]["id"]
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="Duplicate"):
        build_snapshot(project)


@pytest.mark.parametrize("mutation", ["url", "role", "path", "schema", "missing-hash"])
def test_invalid_capture_records_rejected(project, mutation):
    path = capture_path(project, "budget-allocations")
    record = json.loads(path.read_bytes())
    if mutation == "url":
        record["locator"] = "https://example.invalid/unrelated"
    elif mutation == "role":
        record["source_role"] = "other"
    elif mutation == "path":
        record["local_reference"] = "../outside-evidence"
    elif mutation == "schema":
        record["retrieved_at"] = "unknown"
    else:
        record["content_hash"] = None
    path.write_text(json.dumps(record))
    with pytest.raises((ValueError, ValidationError)):
        build_snapshot(project)


def test_writer_only_in_temp_refuses_overwrite(project):
    path, digest = write_snapshot(project)
    content = path.read_bytes()
    assert digest == hash_bytes(content)
    validate_snapshot(json.loads(content), project)
    with pytest.raises(FileExistsError):
        write_snapshot(project)
    assert path.read_bytes() == content
