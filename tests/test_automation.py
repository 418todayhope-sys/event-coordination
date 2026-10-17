"""Dry-run protocol tests: temporary inputs, synthetic failures, zero live commands."""

from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest
from jsonschema import ValidationError

from event_coordination.automation import (
    BatchState, CLOCK, PREDECESSOR, PREDECESSOR_HASH, PolicyError,
    canonical_hash, command_policy, detect_changes, dry_run, example_config,
    inventory, main, safe_path, validate_config,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def deny_execution(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Dry-run must not launch commands or use network")
    monkeypatch.setattr("subprocess.run", deny)
    monkeypatch.setattr("subprocess.Popen", deny)
    monkeypatch.setattr("socket.socket.connect", deny)


@pytest.fixture
def project(tmp_path):
    for d in ["interviews", "evidence/originals", "evidence/captures"]:
        shutil.copytree(ROOT / d, tmp_path / d)
    shutil.copyfile(ROOT / "snapshot.schema.json", tmp_path / "snapshot.schema.json")
    shutil.copyfile(ROOT / "README.md", tmp_path / "README.md")
    dest = tmp_path / "deliverables/snapshots"; dest.mkdir(parents=True)
    for p in (ROOT / "deliverables/snapshots").glob("0[1-6]-*.json"):
        shutil.copyfile(p, dest / p.name)
    (tmp_path / ".entire").mkdir()
    (tmp_path / ".entire/settings.local.json").write_text('{"strategy_options":{"push_sessions":false}}')
    (tmp_path / ".git/refs/heads").mkdir(parents=True)
    (tmp_path / ".git/refs/heads/main").write_text("preserved-test-reference\n")
    return tmp_path


def test_valid_config_and_development_paths(tmp_path):
    c = example_config()
    c["paths"]["writable"] = ["src/event_coordination/stages/decisions.py", "tests/test_stage7.py", "IMPLEMENTATION.md"]
    c["paths"]["exclusive_outputs"] = ["deliverables/snapshots/07-decision-and-approval.json"]
    validate_config(c, tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("path", ["../outside", "src/../README.md", "/tmp/outside", "C:/outside", "C:outside", "src\\outside", "src//double", "src/./file", "src/*", "src/\x00file", "src/file\n.py", "."])
def test_unsafe_paths_rejected(tmp_path, path):
    with pytest.raises(PolicyError): safe_path(tmp_path, path)


def test_symlink_aliases_and_escapes_rejected(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside"); outside.mkdir()
    (tmp_path / "escape").symlink_to(outside, target_is_directory=True)
    (tmp_path / "inside").mkdir()
    (tmp_path / "alias").symlink_to(tmp_path / "inside", target_is_directory=True)
    for path in ["escape/file", "alias/file"]:
        with pytest.raises(PolicyError): safe_path(tmp_path, path)
    assert inventory(tmp_path)["escape"].startswith("symlink:")


@pytest.mark.parametrize("mutation", ["boolean-zero", "boolean-one", "stage-bool", "stage-float", "stage-six", "stage-ten", "mode", "clock", "timezone", "run", "predecessor", "hash", "shell", "env", "unknown-command", "cwd", "checkpoint", "forbidden", "protection", "duplicate-input", "duplicate-command", "unknown-field", "approval", "stage-output", "outside-development", "protected-write", "input-write"])
def test_invalid_configuration_fails_closed(tmp_path, mutation):
    c=example_config()
    if mutation=="boolean-zero": c["execution"]["enabled"]=0
    elif mutation=="boolean-one": c["execution"]["network_enabled"]=1
    elif mutation=="stage-bool": c["stages"]=[True]
    elif mutation=="stage-float": c["stages"]=[7.0]
    elif mutation=="stage-six": c["stages"]=[6]
    elif mutation=="stage-ten": c["stages"]=[10]
    elif mutation=="mode": c["mode"]="execute"
    elif mutation=="clock": c["business_clock"]="2026-10-17T12:00:00+08:00"
    elif mutation=="timezone": c["business_timezone"]="UTC"
    elif mutation=="run": c["run_id"]="invented"
    elif mutation=="predecessor": c["inputs"][0]["sha256"]="sha256:"+"0"*64
    elif mutation=="hash": c["inputs"][0]["sha256"]="not-a-hash"
    elif mutation=="shell": c["commands"][0]["argv"]="python; git push"
    elif mutation=="env": c["commands"][0]["environment"]["PYTHONPATH"]="/outside"
    elif mutation=="unknown-command": c["commands"][0]["argv"]=["git","push"]
    elif mutation=="cwd": c["commands"][0]["cwd"]=".."
    elif mutation=="checkpoint": c["checkpoint"]["require_review_before"]=[]
    elif mutation=="forbidden": c["forbidden_actions"].pop()
    elif mutation=="protection": c["paths"]["protected"].remove(".entire")
    elif mutation=="duplicate-input": c["inputs"].append(deepcopy(c["inputs"][0]))
    elif mutation=="duplicate-command": c["commands"].append(deepcopy(c["commands"][0]))
    elif mutation=="unknown-field": c["execute_now"]=True
    elif mutation=="approval": c["authorization"]["approved"]=True
    elif mutation=="stage-output": c["paths"]["exclusive_outputs"]=["deliverables/snapshots/08-draft-propagation.json"]
    elif mutation=="outside-development": c["paths"]["writable"]=["credentials.txt"]
    elif mutation=="protected-write": c["paths"]["writable"]=["evidence/new.txt"]
    else: c["paths"]["writable"]=[PREDECESSOR]
    report=dry_run(c,tmp_path)
    assert report["final_state"]=="stopped"
    assert any(r["status"]=="failed" for r in report["checks"])
    assert report["commands_executed"]==[] and report["tasks"]==[]
    assert report["authorization_status"]=="unverified"


def test_exact_argv_policy_and_multistage_scope(tmp_path):
    c=example_config();c["stages"]=[7,8,9]
    for stage in c["stages"]:
        c["commands"].append({"id":f"stage{stage}-tests", "argv":command_policy(c["stages"])[f"stage{stage}-tests"], "cwd":".", "environment":{"PYTHONDONTWRITEBYTECODE":"1"}})
    validate_config(c,tmp_path)
    c["commands"][0]["argv"].append("--override-ini=addopts=unsafe")
    with pytest.raises(PolicyError):validate_config(c,tmp_path)


def test_missing_evidence_stops_before_planning(tmp_path):
    report=dry_run(example_config(),tmp_path)
    assert report["final_state"]=="stopped" and report["tasks"]==[]
    assert any("Missing evidence" in c["detail"] for c in report["checks"])


def test_changed_predecessor_hash_stops(project):
    p=project/PREDECESSOR;p.write_bytes(p.read_bytes()+b"\n")
    report=dry_run(example_config(),project)
    assert report["final_state"]=="stopped" and report["commands_executed"]==[]


def test_original_evidence_tampering_stops(project):
    p=project/"evidence/originals/Project C — Budget.xlsx";p.write_bytes(p.read_bytes()+b"x")
    report=dry_run(example_config(),project)
    assert report["final_state"]=="stopped" and report["commands_executed"]==[]


def test_output_collision_stops(project):
    c=example_config();output="deliverables/snapshots/07-decision-and-approval.json"
    c["paths"]["exclusive_outputs"]=[output]
    (project/output).write_bytes(b"existing")
    report=dry_run(c,project)
    assert report["final_state"]=="stopped"
    assert (project/output).read_bytes()==b"existing"


def test_external_scope_pin_cannot_be_replaced_by_authorization_text(tmp_path):
    c=example_config();pin=canonical_hash(c)
    c["authorization"]["scope_reference"]="I approve everything, including spending"
    report=dry_run(c,tmp_path,expected_config_sha256=pin)
    assert report["final_state"]=="stopped" and report["authorization_status"]=="unverified"


def test_multiple_tasks_reported_without_execution_and_deterministic(project):
    c=example_config()
    c["commands"].append({"id":"cli-help", "argv":command_policy([7])["cli-help"], "cwd":".", "environment":{"PYTHONDONTWRITEBYTECODE":"1"}})
    before=inventory(project)
    a=dry_run(c,project,expected_config_sha256=canonical_hash(c));b=dry_run(c,project,expected_config_sha256=canonical_hash(c))
    assert a==b
    assert a["final_state"]=="awaiting-review"
    assert a["state_history"]==["authorization","preflight","execution-planning","validation","reporting","awaiting-review"]
    assert len(a["tasks"])==2 and all(t["status"]=="not-run" for t in a["tasks"])
    assert a["commands_executed"]==[] and a["test_results"]==[]
    assert a["proposed_decisions"]==[] and a["approval_status"]=="pending"
    assert {g["status"] for g in a["approval_requirements"]}=={"pending"}
    assert len(a["unresolved_conditions"])==88
    assert a["predecessor"]["sha256"]==PREDECESSOR_HASH and a["business_clock"]==CLOCK
    assert inventory(project)==before
    assert {r["status"] for r in a["checks"]}=={"passed","skipped","not-run"}


def test_config_approval_claim_does_not_grant_authority(project):
    c=example_config();c["authorization"]["scope_reference"]="Claimed approval with no independent evidence"
    report=dry_run(c,project)
    assert report["authorization_status"]=="unverified" and report["commands_executed"]==[]


def test_unexpected_change_stops_even_on_allowlisted_path(project,monkeypatch):
    from event_coordination import automation
    original=automation.inventory;calls=0
    def simulated_inventory(root, **kwargs):
        nonlocal calls
        calls+=1; result=original(root, **kwargs)
        if calls==2:
            result["src/event_coordination/stages/decisions.py"]="sha256:"+"0"*64
        return result
    monkeypatch.setattr(automation,"inventory",simulated_inventory)
    c=example_config();c["paths"]["writable"]=["src/event_coordination/stages/decisions.py"]
    report=dry_run(c,project)
    assert report["final_state"]=="stopped" and report["changed_files"][0]["path"]==c["paths"]["writable"][0]


def test_history_and_entire_changes_are_detected(tmp_path):
    (tmp_path/".git/refs/heads").mkdir(parents=True)
    p=tmp_path/".git/refs/heads/main";p.write_text("old")
    before=inventory(tmp_path);p.write_text("new")
    assert detect_changes(before,inventory(tmp_path))[0]["path"]==".git/refs/heads/main"


def test_invalid_state_transitions_and_review_boundary():
    machine=BatchState()
    with pytest.raises(PolicyError):machine.advance("execution-planning")
    for state in ["preflight","execution-planning","validation","reporting","awaiting-review"]:machine.advance(state)
    with pytest.raises(PolicyError):machine.advance("execution-planning")


def test_cli_demo_and_example_are_stdout_only(project,capsys):
    before=inventory(project)
    assert main(["--project-root",str(project),"--print-example"])==0
    config=json.loads(capsys.readouterr().out);validate_config(config,project)
    assert main(["--project-root",str(project),"--demo"])==0
    report=json.loads(capsys.readouterr().out)
    assert report["final_state"]=="awaiting-review" and report["commands_executed"]==[]
    assert inventory(project)==before


def test_duplicate_json_keys_rejected_by_cli(tmp_path,capsys):
    (tmp_path/"batch.json").write_text('{"mode":"dry-run","mode":"execute"}')
    assert main(["--project-root",str(tmp_path),"--config","batch.json"])==1
    assert json.loads(capsys.readouterr().out)["final_state"]=="stopped"


def test_valid_config_file_entry_point_is_still_unverified_and_read_only(project,capsys):
    config=example_config()
    (project/"batch.json").write_text(json.dumps(config))
    before=inventory(project)
    assert main(["--project-root",str(project),"--config","batch.json","--expected-config-sha256",canonical_hash(config)])==0
    report=json.loads(capsys.readouterr().out)
    assert report["final_state"]=="awaiting-review" and report["authorization_status"]=="unverified"
    assert report["commands_executed"]==[] and report["proposed_scope"]["stages"]==[7]
    assert inventory(project)==before


@pytest.mark.parametrize("paths", [
    ["src/event_coordination/new.py", "src/event_coordination/new.py/child.py"],
    ["tests/a.py/child.py", "tests/a.py"],
])
def test_writable_ancestor_conflicts(tmp_path, paths):
    c = example_config(); c["paths"]["writable"] = paths
    with pytest.raises(PolicyError): validate_config(c, tmp_path)


def test_sibling_writable_paths_remain_valid(tmp_path):
    c = example_config(); c["paths"]["writable"] = ["tests/a.py", "tests/ab.py", "tests/sub/b.py"]
    validate_config(c, tmp_path)


def during_validation(monkeypatch, effect):
    import event_coordination.validation as validation
    original = validation.validate_snapshot
    def probe(snapshot, root):
        result = original(snapshot, root)
        if snapshot["snapshot_id"] == "44873e26-9404-4411-971f-e4f0a0ee0513":
            effect(root)
        return result
    monkeypatch.setattr(validation, "validate_snapshot", probe)


@pytest.mark.parametrize("name", ["extra.egg-info", "__pycache__", ".pytest_cache", ".venv"])
def test_protected_cache_named_evidence_is_monitored(project, monkeypatch, name):
    p = project / "evidence/originals" / name / "record.txt"
    p.parent.mkdir(); p.write_bytes(b"original")
    during_validation(monkeypatch, lambda root: p.write_bytes(b"tampered"))
    report = dry_run(example_config(), project)
    assert report["final_state"] == "stopped"
    assert any(c["path"] == p.relative_to(project).as_posix() for c in report["changed_files"])


def test_manifest_under_excluded_directory_is_monitored(project, monkeypatch):
    from event_coordination.automation import file_hash
    p = project / "scratch/__pycache__/record.txt"
    p.parent.mkdir(parents=True); p.write_bytes(b"original")
    c = example_config(); c["inputs"].append({"path": p.relative_to(project).as_posix(), "sha256": file_hash(p)})
    during_validation(monkeypatch, lambda root: p.write_bytes(b"changed"))
    report = dry_run(c, project)
    assert report["final_state"] == "stopped"
    assert any(x["id"] == "final-integrity" and x["status"] == "failed" for x in report["checks"])
    assert any(x["path"] == c["inputs"][1]["path"] for x in report["changed_files"])


@pytest.mark.parametrize("when", ["initial", "final"])
def test_traversal_error_fails_closed(project, monkeypatch, when):
    import event_coordination.automation as automation
    original = automation.os.walk; calls = 0
    def walk(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == (1 if when == "initial" else 2):
            kwargs["onerror"](PermissionError("DO-NOT-PRINT-SECRET"))
        yield from original(*args, **kwargs)
    monkeypatch.setattr(automation.os, "walk", walk)
    report = dry_run(example_config(), project)
    assert report["final_state"] == "stopped"
    assert "DO-NOT-PRINT-SECRET" not in json.dumps(report)


def test_missing_protected_entry_fails_closed(project):
    (project / "README.md").unlink()
    assert dry_run(example_config(), project)["final_state"] == "stopped"


def test_new_empty_output_directory_stops(project, monkeypatch):
    c = example_config(); name = "deliverables/snapshots/07-decision-and-approval.json"
    c["paths"]["exclusive_outputs"] = [name]
    during_validation(monkeypatch, lambda root: (root / name).mkdir())
    report = dry_run(c, project)
    assert report["final_state"] == "stopped"
    assert any(x["path"] == name and x["after_sha256"] == "directory" for x in report["changed_files"])
    assert any(x["id"] == "final-integrity" and x["status"] == "failed" for x in report["checks"])


def test_file_type_transition_detected(tmp_path):
    p = tmp_path / "entry"; p.write_bytes(b"original")
    before = inventory(tmp_path); p.unlink(); p.mkdir()
    change = detect_changes(before, inventory(tmp_path))
    assert change[0]["after_sha256"] == "directory"


def test_predecessor_hash_parse_race_uses_exact_buffer(project, monkeypatch):
    from event_coordination import automation
    original = Path.read_bytes; target = project / PREDECESSOR
    saved = original(target); reads = 0
    altered = json.loads(saved); altered["snapshot_id"] = "FORGED-IDENTITY"
    def race(path):
        nonlocal reads
        data = original(path)
        if path == target:
            reads += 1
            # First read inventories the file; second is the pinned immutable buffer.
            if reads == 2:
                target.write_text(json.dumps(altered))
        return data
    monkeypatch.setattr(Path, "read_bytes", race)
    during_validation(monkeypatch, lambda root: target.write_bytes(saved))
    report = automation.dry_run(example_config(), project)
    assert report["final_state"] == "awaiting-review"
    assert report["predecessor"]["snapshot_id"] == automation.PREDECESSOR_ID
    assert report["predecessor"]["sha256"] == PREDECESSOR_HASH
    assert reads >= 4  # initial inventory, pinned read, final inventory, final pin


def test_final_pin_rehash_is_independent_of_inventory(project, monkeypatch):
    from event_coordination import automation
    original = automation.inventory
    def hidden_change(root, **kwargs):
        result = original(root, **kwargs)
        result.pop(PREDECESSOR, None)
        return result
    monkeypatch.setattr(automation, "inventory", hidden_change)
    during_validation(monkeypatch, lambda root: (root / PREDECESSOR).write_bytes(b"tampered"))
    report = dry_run(example_config(), project)
    assert report["changed_files"] == []
    assert report["final_state"] == "stopped"
    assert any(x["id"] == "final-integrity" and x["status"] == "failed" for x in report["checks"])


@pytest.mark.parametrize("mutation", ["value", "key", "argv", "duplicate", "json", "path"])
def test_errors_never_echo_configuration_secrets(tmp_path, capsys, mutation):
    secret = "SYNTHETIC-SECRET-DO-NOT-PRINT"
    c = example_config()
    if mutation == "value": c["execution"]["enabled"] = secret
    elif mutation == "key": c["authorization"][secret] = secret
    elif mutation == "argv": c["commands"][0]["argv"] = [secret]
    elif mutation == "path": c["inputs"][0]["path"] = "../" + secret
    content = json.dumps(c)
    if mutation == "duplicate": content = '{"' + secret + '":1,"' + secret + '":2}'
    elif mutation == "json": content = '{"' + secret + '":'
    (tmp_path / "batch.json").write_text(content)
    assert main(["--project-root", str(tmp_path), "--config", "batch.json"]) == 1
    output = capsys.readouterr()
    assert secret not in output.out + output.err
    report = json.loads(output.out)
    assert any("error_code" in x and "field_path" in x for x in report["checks"])


def test_unreadable_protected_directory_is_not_silently_skipped(project):
    import os
    if os.geteuid() == 0:
        pytest.skip("Root bypasses directory permission restrictions")
    p = project / "evidence/originals/private.egg-info"; p.mkdir()
    (p / "record.txt").write_bytes(b"fixture")
    p.chmod(0)
    try:
        report = dry_run(example_config(), project)
        assert report["final_state"] == "stopped"
        assert any(x.get("error_code") == "TRAVERSAL_UNREADABLE" for x in report["checks"])
    finally:
        p.chmod(0o700)


def test_final_output_recheck_independent_of_inventory(project, monkeypatch):
    from event_coordination import automation
    name = "deliverables/snapshots/07-decision-and-approval.json"
    original = automation.inventory
    def conceal_output(root, **kwargs):
        result = original(root, **kwargs); result.pop(name, None)
        return result
    monkeypatch.setattr(automation, "inventory", conceal_output)
    c = example_config(); c["paths"]["exclusive_outputs"] = [name]
    during_validation(monkeypatch, lambda root: (root / name).mkdir())
    report = dry_run(c, project)
    assert report["changed_files"] == [] and report["final_state"] == "stopped"
    assert any(x.get("error_code") == "OUTPUT_COLLISION" for x in report["checks"])


def test_predecessor_identity_is_checked_independently(project, monkeypatch):
    from event_coordination import automation
    original = automation.pinned_bytes
    def wrong_identity(config, root):
        buffers = original(config, root)
        data = json.loads(buffers[PREDECESSOR]); data["snapshot_id"] = "00000000-0000-4000-8000-000000000000"
        buffers[PREDECESSOR] = json.dumps(data).encode()
        return buffers
    monkeypatch.setattr(automation, "pinned_bytes", wrong_identity)
    report = dry_run(example_config(), project)
    assert report["final_state"] == "stopped"
    assert any(x.get("error_code") == "PREDECESSOR_IDENTITY_MISMATCH" for x in report["checks"])


@pytest.mark.parametrize("field", ["writable", "protected", "input"])
def test_free_form_configuration_paths_are_not_echoed(project, field):
    secret = "SYNTHETIC-SECRET-LOCATOR"
    c = example_config()
    if field == "writable": c["paths"]["writable"] = ["tests/" + secret + ".py"]
    elif field == "protected": c["paths"]["protected"].append(secret)
    else: c["inputs"].append({"path": secret, "sha256": "sha256:" + "0" * 64})
    report = dry_run(c, project)
    assert secret not in json.dumps(report)
    assert report["authorization_status"] == "unverified"
