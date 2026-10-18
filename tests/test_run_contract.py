"""Temporary-fixture contracts: no real archives, artifacts, or snapshot writers."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from uuid import UUID, uuid4

import pytest

from event_coordination import run_contract as rc

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_external_actions(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("run contracts must not execute commands or contact services")
    monkeypatch.setattr("subprocess.Popen", deny)
    monkeypatch.setattr("socket.socket.connect", deny)


def put(root, path, data):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def pin(root, path="evidence/originals/source.txt", data=b"synthetic", kind="source", id="source-a"):
    put(root, path, data)
    return rc.pin_inputs(root, (rc.InputSpec(id, path, kind),))[0]


def reason(kind="source", id="source-a"):
    return {"kind": kind, "id": id, "reason": "Synthetic fixture changed", "evidence_ids": ["fixture-observation"]}


def supersession(**kwargs):
    return rc.new_run_metadata(supersedes_run_id=str(uuid4()), changed_source_ids=("source-a",),
                               change_reasons=(reason(),), **kwargs)


def test_fresh_ids_and_no_authority():
    a, b = rc.new_run_metadata(), rc.new_run_metadata()
    assert a["run_id"] != b["run_id"]
    assert UUID(a["run_id"]).version == 4
    assert a["supersedes_run_id"] is None and a["change_reasons"] == []
    ids = [rc.new_snapshot_id() for _ in range(20)]
    assert len(set(ids)) == 20 and all(UUID(i).version == 4 for i in ids)
    assert "authorized" not in a and "approval" not in a


@pytest.mark.parametrize("field,value", [
    ("run_contract_version", True), ("run_contract_version", "1"), ("run_contract_version", 2),
    ("run_id", "bad"), ("run_id", False), ("business_clock", "2026-08-26T12:00:00Z"),
    ("supersedes_run_id", "bad"), ("changed_source_ids", True),
    ("changed_source_ids", [1]), ("changed_source_ids", ["source-a", "source-a"]),
    ("changed_decision_ids", "decision-a"), ("change_reasons", {}),
])
def test_strict_metadata(field, value):
    data = supersession()
    data[field] = value
    with pytest.raises(rc.ContractError):
        rc.validate_run_metadata(data)


def test_self_supersession_and_forged_approval():
    data = supersession()
    data["supersedes_run_id"] = data["run_id"]
    with pytest.raises(rc.ContractError, match="self_supersession"):
        rc.validate_run_metadata(data)
    data = rc.new_run_metadata()
    data["approved"] = True
    with pytest.raises(rc.ContractError, match="invalid_run_metadata"):
        rc.validate_run_metadata(data)


@pytest.mark.parametrize("mutation", ["no-reason", "no-evidence", "wrong-id", "no-parent", "extra-field", "duplicate-reason"])
def test_supersession_requires_supported_explanation(mutation):
    data = supersession()
    if mutation == "no-reason": data["change_reasons"] = []
    if mutation == "no-evidence": data["change_reasons"][0]["evidence_ids"] = []
    if mutation == "wrong-id": data["change_reasons"][0]["id"] = "wrong"
    if mutation == "no-parent": data["supersedes_run_id"] = None
    if mutation == "extra-field": data["change_reasons"][0]["approved"] = True
    if mutation == "duplicate-reason": data["change_reasons"] *= 2
    with pytest.raises(rc.ContractError): rc.validate_run_metadata(data)


def test_unchanged_input_recovery_reason():
    data = rc.new_run_metadata(supersedes_run_id=str(uuid4()),
                               change_reasons=(reason("recovery", "attempt-interrupted"),))
    rc.validate_run_metadata(data, previous=(), current=())
    assert data["changed_source_ids"] == data["changed_decision_ids"] == []


@pytest.mark.parametrize("path", ["/tmp/out", "../out", "evidence/../out", "./out", "a//b", "a/", "a\\b", "C:out", "a\x00b", "", ".git/config", ".entire/settings.json", "evidence/.aws/key"])
def test_unsafe_paths_rejected(path):
    with pytest.raises(rc.ContractError): rc.relative_path(path)


def test_manifest_changes_and_source_identity(tmp_path):
    a = pin(tmp_path)
    b = pin(tmp_path, data=b"revision")
    extra = pin(tmp_path, "evidence/decision.txt", b"synthetic statement", "decision", "decision-a")
    changes = rc.compare_manifests((a,), (b, extra))
    assert [(r["id"], r["change"]) for r in changes] == [("decision-a", "added"), ("source-a", "changed")]
    assert rc.compare_manifests((a,), ()) == [{"id": "source-a", "kind": "source", "change": "removed",
                                               "source_id": "source-a",
                                               "previous_sha256": a.sha256, "current_sha256": None}]
    data = supersession()
    rc.validate_run_metadata(data, previous=(a,), current=(b,))
    with pytest.raises(rc.ContractError, match="unsupported_changed_ids"):
        rc.validate_run_metadata(data, previous=(a,), current=(a,))
    with pytest.raises(rc.ContractError, match="manifest_pair_required"):
        rc.validate_run_metadata(data, previous=(a,))


@pytest.mark.parametrize("mutation", ["bytes", "replace-same-bytes", "missing", "symlink", "directory"])
def test_revalidation_rejects_mutations(tmp_path, mutation):
    p = pin(tmp_path)
    target = tmp_path / p.spec.path
    if mutation == "bytes": target.write_bytes(b"changed")
    elif mutation == "replace-same-bytes":
        replacement = put(tmp_path, "replacement", target.read_bytes())
        replacement.replace(target)
    elif mutation == "missing": target.unlink()
    elif mutation == "symlink":
        target.unlink(); target.symlink_to(put(tmp_path, "other", b"synthetic"))
    elif mutation == "directory":
        target.unlink(); target.mkdir()
    with pytest.raises(rc.ContractError): rc.verify_inputs(tmp_path, (p,))


def test_symlinked_parent_and_root_rejected(tmp_path):
    actual = tmp_path / "actual"; actual.mkdir()
    pin(actual)
    (tmp_path / "alias").symlink_to(actual, target_is_directory=True)
    spec = rc.InputSpec("s", "evidence/originals/source.txt", "source")
    with pytest.raises(rc.ContractError): rc.pin_inputs(tmp_path / "alias", (spec,))
    (tmp_path / "evidence").symlink_to(actual / "evidence", target_is_directory=True)
    with pytest.raises(rc.ContractError): rc.pin_inputs(tmp_path, (spec,))


def test_hash_pins_duplicates_and_ambiguous_identity(tmp_path):
    p = pin(tmp_path)
    with pytest.raises(rc.ContractError, match="input_hash_mismatch"):
        rc.pin_inputs(tmp_path, (rc.InputSpec("s", p.spec.path, "source", "sha256:" + "0" * 64),))
    with pytest.raises(rc.ContractError, match="duplicate_input"):
        rc.pin_inputs(tmp_path, (p.spec, p.spec))
    alternate = rc.InputPin(rc.InputSpec(p.spec.id, p.spec.path, "decision"), p.sha256, p.identity)
    with pytest.raises(rc.ContractError, match="input_identity_ambiguous"):
        rc.compare_manifests((p,), (alternate,))


def test_multiple_representations_share_one_changed_source(tmp_path):
    put(tmp_path, "evidence/brief.pdf", b"synthetic pdf")
    put(tmp_path, "evidence/brief.txt", b"synthetic manual copy")
    specs = tuple(rc.InputSpec(name, f"evidence/brief.{suffix}", "source", source_id="event-brief")
                  for name, suffix in (("brief-pdf", "pdf"), ("brief-text", "txt")))
    old = rc.pin_inputs(tmp_path, specs)
    put(tmp_path, "evidence/brief.txt", b"changed synthetic copy")
    new = rc.pin_inputs(tmp_path, specs)
    data = rc.new_run_metadata(supersedes_run_id=str(uuid4()), changed_source_ids=("event-brief",),
                               change_reasons=(reason(id="event-brief"),))
    rc.validate_run_metadata(data, previous=old, current=new)
    assert [r["source_id"] for r in rc.compare_manifests(old, new)] == ["event-brief"]


@pytest.mark.parametrize("mutation", ["missing", "wrong-run", "forged-approval"])
def test_new_stage1_requires_strict_run_metadata(chain, mutation):
    root, schema, expected, inspected, _ = chain
    data = json.loads(inspected.data)
    if mutation == "missing": del data["state"]["run_metadata"]
    elif mutation == "wrong-run": data["state"]["run_metadata"]["run_id"] = str(uuid4())
    else: data["state"]["run_metadata"]["approved"] = True
    p = pin(root, expected.pin.spec.path, json.dumps(data).encode(), "snapshot", "first")
    e = rc.SnapshotExpectation(expected.run_id, expected.snapshot_id, 1, p)
    with pytest.raises(rc.ContractError): rc.inspect_predecessor(root, e, schema)


def test_late_archive_collision_is_detected(tmp_path, monkeypatch):
    p = pin(tmp_path)
    run = str(uuid4())
    original = rc.verify_inputs
    calls = 0
    def mutate(root, pins):
        nonlocal calls
        original(root, pins)
        calls += 1
        if calls == 2:
            (tmp_path / "deliverables/history" / run).mkdir(parents=True)
    monkeypatch.setattr(rc, "verify_inputs", mutate)
    with pytest.raises(rc.ContractError, match="archive_collision"):
        rc.plan_archive(tmp_path, run, (p,))


def test_unreadable_input_fails_safely(tmp_path, monkeypatch):
    p = pin(tmp_path)
    original = rc.os.open
    def denied(path, *args, **kwargs):
        if path == "originals": raise PermissionError("synthetic-secret")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(rc.os, "open", denied)
    with pytest.raises(rc.ContractError) as caught: rc.verify_inputs(tmp_path, (p,))
    assert "synthetic-secret" not in str(caught.value)


def test_manifest_order_does_not_imply_source_change(tmp_path):
    a = pin(tmp_path)
    b = pin(tmp_path, "evidence/second", b"second", id="source-b")
    assert rc.compare_manifests((a, b), (b, a)) == []


@pytest.fixture
def chain(tmp_path):
    schema = pin(tmp_path, "snapshot.schema.json", (ROOT / "snapshot.schema.json").read_bytes(), "schema", "schema")
    run = str(uuid4())
    first = json.loads((ROOT / "deliverables/snapshots/01-scope-and-approval-gates.json").read_bytes())
    first.update(run_id=run, snapshot_id=rc.new_snapshot_id())
    first["state"]["run_metadata"] = rc.new_run_metadata()
    first["state"]["run_metadata"]["run_id"] = run
    first_pin = pin(tmp_path, "deliverables/snapshots/01.json", json.dumps(first).encode(), "snapshot", "first")
    expected = rc.SnapshotExpectation(run, first["snapshot_id"], 1, first_pin)
    inspected = rc.inspect_predecessor(tmp_path, expected, schema)
    second = json.loads((ROOT / "deliverables/snapshots/02-source-capture.json").read_bytes())
    second.update(run_id=run, snapshot_id=rc.new_snapshot_id(), predecessor=inspected.reference)
    return tmp_path, schema, expected, inspected, second


def inspect_second(chain, second=None, parent=True):
    root, schema, first, inspected, original = chain
    second = original if second is None else second
    p = pin(root, "deliverables/snapshots/02.json", json.dumps(second).encode(), "snapshot", "second")
    expected = rc.SnapshotExpectation(first.run_id, second["snapshot_id"], 2, p)
    return rc.inspect_predecessor(root, expected, schema, predecessor=inspected if parent else None)


def test_dynamic_chain_uses_fresh_ids_and_actual_bytes(chain):
    result = inspect_second(chain)
    assert result.expectation.run_id != rc.LEGACY_RUN_ID
    assert result.reference["sha256"] == "sha256:" + hashlib.sha256(result.data).hexdigest()
    first = json.loads(chain[3].data)
    rc.validate_run_metadata(first["state"]["run_metadata"])
    assert first["predecessor"] is None and first["consumed_record_ids"] == []


@pytest.mark.parametrize("mutation", ["wrong-run", "wrong-sequence", "wrong-stage", "hash", "parent-id", "clock", "boolean-sequence", "invalid-date"])
def test_chain_rejects_tampering(chain, mutation):
    second = deepcopy(chain[4])
    if mutation == "wrong-run": second["run_id"] = str(uuid4())
    if mutation == "wrong-sequence": second["sequence"] = 3
    if mutation == "wrong-stage": second["stage"] = "constraint-model"
    if mutation == "hash": second["predecessor"]["sha256"] = "sha256:" + "0" * 64
    if mutation == "parent-id": second["predecessor"]["snapshot_id"] = str(uuid4())
    if mutation == "clock": second["state"]["business_clock"] = "2026-01-01T00:00:00Z"
    if mutation == "boolean-sequence": second["sequence"] = True
    if mutation == "invalid-date": second["created_at"] = "invalid"
    with pytest.raises(rc.ContractError): inspect_second(chain, second)


def test_parent_required_and_late_parent_mutation(chain):
    with pytest.raises(rc.ContractError, match="verified_predecessor_required"):
        inspect_second(chain, parent=False)
    put(chain[0], chain[2].pin.spec.path, b"tampered")
    with pytest.raises(rc.ContractError): inspect_second(chain)


@pytest.mark.parametrize("target", ["snapshot", "schema"])
def test_hash_parse_race_and_final_revalidation(chain, monkeypatch, target):
    root, schema, expected, _, _ = chain
    original = rc._json
    changed = False
    def mutate(data):
        nonlocal changed
        if not changed:
            changed = True
            path = expected.pin.spec.path if target == "snapshot" else schema.spec.path
            put(root, path, b"late mutation")
        return original(data)
    monkeypatch.setattr(rc, "_json", mutate)
    with pytest.raises(rc.ContractError): rc.inspect_predecessor(root, expected, schema)


def test_hash_and_parse_exact_buffer(chain, monkeypatch):
    root, schema, expected, inspected, _ = chain
    received = []
    original = rc._json
    def observe(data):
        received.append(data)
        return original(data)
    monkeypatch.setattr(rc, "_json", observe)
    result = rc.inspect_predecessor(root, expected, schema)
    assert received[0] is result.data
    assert result.data == inspected.data


def test_duplicate_json_keys_rejected(chain):
    root, schema, expected, _, _ = chain
    data = (root / expected.pin.spec.path).read_bytes()
    duplicate = data[:-1] + b',"run_id":"forged"}'
    p = pin(root, expected.pin.spec.path, duplicate, "snapshot", "first")
    e = rc.SnapshotExpectation(expected.run_id, expected.snapshot_id, 1, p)
    with pytest.raises(rc.ContractError, match="invalid_json"): rc.inspect_predecessor(root, e, schema)


def test_archive_is_read_only_and_mirrors_paths(tmp_path):
    p = pin(tmp_path)
    run = str(uuid4())
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    result = rc.plan_archive(tmp_path, run, (p,))
    assert result["destination"] == f"deliverables/history/{run}"
    assert result["files"][0]["destination"] == f"deliverables/history/{run}/{p.spec.path}"
    assert before == sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))


@pytest.mark.parametrize("collision", ["empty-directory", "file", "dangling-symlink", "parent-symlink", "parent-file"])
def test_archive_collisions(tmp_path, collision):
    p = pin(tmp_path)
    run = str(uuid4())
    target = tmp_path / "deliverables/history" / run
    target.parent.mkdir(parents=True)
    if collision == "empty-directory": target.mkdir()
    elif collision == "file": target.write_bytes(b"existing")
    elif collision == "dangling-symlink": target.symlink_to(tmp_path / "missing")
    elif collision == "parent-symlink":
        target.parent.rmdir(); target.parent.symlink_to(tmp_path, target_is_directory=True)
    else:
        target.parent.rmdir(); target.parent.write_bytes(b"not a directory")
    with pytest.raises(rc.ContractError): rc.plan_archive(tmp_path, run, (p,))


@pytest.mark.parametrize("path", ["secrets.txt", "src/helper.py", "deliverables/history/old/file"])
def test_archive_scope(tmp_path, path):
    p = pin(tmp_path, path)
    with pytest.raises(rc.ContractError): rc.plan_archive(tmp_path, str(uuid4()), (p,))


def test_failure_description_does_not_write_or_invent_hash(tmp_path):
    data = rc.describe_failure(run_id=str(uuid4()), attempt_id=str(uuid4()), stage=9,
                              last_validated_stage=8, code="output_missing",
                              occurred_at=datetime(2026, 10, 17, tzinfo=timezone.utc),
                              affected_paths=("deliverables/event-plan.md",))
    assert data["status"] == "failed"
    assert data["observed_sha256"] is data["expected_sha256"] is None
    assert data["occurred_at"] != data["business_clock"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("change", [{"stage": True}, {"last_validated_stage": 9},
                                   {"code": "secret-token-fixture"}, {"observed_sha256": "bad"},
                                   {"occurred_at": datetime(2026, 1, 1)}])
def test_failure_description_strict_and_safe(change):
    kwargs = dict(run_id=str(uuid4()), attempt_id=str(uuid4()), stage=9, last_validated_stage=8,
                  code="validation_failed", occurred_at=datetime.now(timezone.utc))
    kwargs.update(change)
    with pytest.raises(rc.ContractError) as caught: rc.describe_failure(**kwargs)
    assert "secret-token-fixture" not in str(caught.value)


def test_explicit_legacy_byte_compatibility_in_temporary_copy(tmp_path):
    for directory in ("evidence", "interviews", "deliverables"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    shutil.copyfile(ROOT / "snapshot.schema.json", tmp_path / "snapshot.schema.json")
    results = rc.inspect_legacy_run(tmp_path)
    assert len(results) == 8 and all(r.expectation.run_id == rc.LEGACY_RUN_ID for r in results)
    assert [r.reference["sha256"] for r in results] == ["sha256:" + h for h in rc.LEGACY_HASHES]
    assert not (tmp_path / "deliverables/snapshots/09-publication-validation.json").exists()
    put(tmp_path, results[-1].expectation.pin.spec.path, b"tampered")
    with pytest.raises(rc.ContractError): rc.inspect_legacy_run(tmp_path)
