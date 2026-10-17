"""Dry-run supervised batch planning. No subprocess, network or repository writes.

Configuration is a proposed scope, never proof of learner/business authorization.
This module is a policy/preflight foundation, not an execution security sandbox.
"""

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from jsonschema import Draft202012Validator, ValidationError

VERSION = "event-supervised-local/1"
CLOCK = "2026-08-26T12:00:00+08:00"
RUN_ID = "988f5ccf-4aeb-44d7-984d-777b1a2412e1"
PREDECESSOR = "deliverables/snapshots/06-feasibility-testing.json"
PREDECESSOR_HASH = "sha256:57b5be2bde9d3c5a66316b2b1e0239a8c55e39de5ff54b859bf644fe74542fe1"
PREDECESSOR_ID = "44873e26-9404-4411-971f-e4f0a0ee0513"
FORBIDDEN = ("network-access", "dependency-installation", "git-stage", "git-commit", "git-push",
             "checkpoint-management", "business-approval", "external-communication", "booking",
             "payment", "production-calendar-write", "publication", "live-command-execution")
PROTECTED = ("README.md", "snapshot.schema.json", "interviews", "evidence", ".git", ".entire",
             *(f"deliverables/snapshots/{name}" for name in (
                 "01-scope-and-approval-gates.json", "02-source-capture.json", "03-constraint-model.json",
                 "04-planning-baseline.json", "05-option-generation.json", "06-feasibility-testing.json")))
CHECKPOINTS = ("implementation", "focused-tests", "regression-tests", "audit")
REVIEW_BEFORE = ("real-snapshot-generation", "next-stage", "learner-decision", "business-approval", "external-action")
OUTPUT_NAMES = {7: "07-decision-and-approval.json", 8: "08-draft-propagation.json", 9: "09-publication-validation.json"}
ARTIFACTS = {"deliverables/vendor-comparison.csv", "deliverables/event-plan.md", "deliverables/event-calendar.ics", "deliverables/draft-communications.md"}
HASH = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
TEXT = {"type": "string", "minLength": 1}
STRINGS = {"type": "array", "items": TEXT, "uniqueItems": True}


def obj(properties):
    return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}


CONFIG_SCHEMA = obj({
    "protocol_version": {"const": VERSION}, "mode": {"const": "dry-run"},
    "authorization": obj({"scope_reference": TEXT}),
    "stages": {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "integer", "enum": [7, 8, 9]}},
    "business_clock": {"const": CLOCK}, "business_timezone": {"const": "Asia/Taipei"},
    "run_id": {"const": RUN_ID},
    "inputs": {"type": "array", "minItems": 1, "items": obj({"path": TEXT, "sha256": HASH})},
    "paths": obj({"writable": STRINGS, "exclusive_outputs": STRINGS, "protected": STRINGS}),
    "commands": {"type": "array", "minItems": 1, "items": obj({
        "id": TEXT, "argv": {"type": "array", "minItems": 1, "items": TEXT},
        "cwd": {"const": "."}, "environment": obj({"PYTHONDONTWRITEBYTECODE": {"const": "1"}})})},
    "checkpoint": obj({"after": STRINGS, "require_review_before": STRINGS}),
    "forbidden_actions": STRINGS,
    "execution": obj({"enabled": {"type": "boolean", "const": False},
                      "network_enabled": {"type": "boolean", "const": False}}),
})


class PolicyError(ValueError):
    """A proposed scope violates dry-run policy."""


def safe_error(error):
    """No exception values, filenames, unknown keys or configuration instances."""
    code, field = "POLICY_REJECTED", "$"
    if isinstance(error, ValidationError):
        code = "CONFIG_SCHEMA_INVALID"
        allowed = {"authorization", "scope_reference", "stages", "inputs", "path", "sha256",
                   "paths", "writable", "exclusive_outputs", "protected", "commands", "id",
                   "argv", "cwd", "environment", "execution", "enabled", "network_enabled",
                   "checkpoint", "after", "require_review_before", "business_clock",
                   "business_timezone", "run_id", "mode", "protocol_version", "forbidden_actions"}
        for part in error.absolute_path:
            if type(part) is int:
                field += "[]"
            elif part in allowed:
                field += "." + part
            else:
                break
    elif isinstance(error, PolicyError):
        code = {
            "Pinned input integrity mismatch": "INPUT_HASH_MISMATCH",
            "Missing pinned input": "INPUT_MISSING",
            "Missing protected entry": "PROTECTED_ENTRY_MISSING",
            "Unreadable repository traversal": "TRAVERSAL_UNREADABLE",
            "Exclusive output collision": "OUTPUT_COLLISION",
            "Predecessor run/clock mismatch": "PREDECESSOR_IDENTITY_MISMATCH",
            "Writable/output paths must not overlap": "WRITABLE_PATH_OVERLAP",
            "Duplicate JSON key": "DUPLICATE_JSON_KEY",
        }.get(str(error), "POLICY_REJECTED")
    elif isinstance(error, OSError):
        code = "FILESYSTEM_UNAVAILABLE"
    elif isinstance(error, json.JSONDecodeError):
        code = "INVALID_JSON"
    return {"error_code": code, "field_path": field,
            "detail": "Missing evidence, invalid configuration, changed integrity, or unsafe filesystem state; review required."}


def canonical_hash(value) -> str:
    content = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    return "sha256:" + hashlib.sha256(content).hexdigest()


def file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(root: Path, value: str, *, allow_root=False) -> Path:
    """Only canonical relative POSIX paths; reject traversal and symlink aliases."""
    if allow_root and value == ".":
        return root.resolve(strict=True)
    if (not isinstance(value, str) or not value or "\\" in value or "\x00" in value
            or any(ord(c) < 32 for c in value) or value.startswith("/")
            or re.match(r"^[A-Za-z]:", value) or any(c in value for c in "*?[]")
            or any(p in ("", ".", "..") for p in value.split("/"))):
        raise PolicyError("Path must be a canonical repository-relative path")
    base = root.resolve(strict=True)
    path = base
    for part in value.split("/"):
        path = path / part
        if path.is_symlink():
            raise PolicyError("Symlink paths are not allowed")
    if not path.resolve().is_relative_to(base):
        raise PolicyError("Path escapes repository root")
    return path


def command_policy(stages) -> dict:
    commands = {"regression-tests": [".venv/bin/python", "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                "cli-help": [".venv/bin/python", "-m", "event_coordination.cli", "--help"]}
    commands.update({f"stage{s}-tests": [".venv/bin/python", "-m", "pytest", f"tests/test_stage{s}.py", "-q", "-p", "no:cacheprovider"] for s in stages})
    return commands


def validate_config(config: dict, root: Path) -> None:
    Draft202012Validator(CONFIG_SCHEMA).validate(config)
    if any(type(s) is not int for s in config["stages"]):
        raise PolicyError("Stage numbers must be integers, not booleans/floats")
    for v in config["execution"].values():
        if type(v) is not bool or v is not False:
            raise PolicyError("Execution flags must be actual false booleans")
    if config["stages"] != sorted(config["stages"]):
        raise PolicyError("Stages must be ordered")
    if tuple(config["checkpoint"]["after"]) != CHECKPOINTS or tuple(config["checkpoint"]["require_review_before"]) != REVIEW_BEFORE:
        raise PolicyError("Required checkpoint boundaries cannot be weakened")
    if set(config["forbidden_actions"]) != set(FORBIDDEN):
        raise PolicyError("Forbidden-action policy cannot be changed")
    paths = config["paths"]
    if not set(PROTECTED) <= set(paths["protected"]):
        raise PolicyError("Required evidence/history protections cannot be removed")
    for p in paths["protected"]:
        safe_path(root, p)
    inputs = config["inputs"]
    if len({i["path"] for i in inputs}) != len(inputs):
        raise PolicyError("Duplicate input paths")
    if {"path": PREDECESSOR, "sha256": PREDECESSOR_HASH} not in inputs:
        raise PolicyError("Exact Stage 6 predecessor is required")
    for i in inputs:
        safe_path(root, i["path"])
    combined = paths["writable"] + paths["exclusive_outputs"]
    if any(a == b or a.startswith(b + "/") or b.startswith(a + "/")
           for n, a in enumerate(combined) for b in combined[n + 1:]):
        raise PolicyError("Writable/output paths must not overlap")
    for p in combined:
        target = safe_path(root, p)
        if any(p == protected or p.startswith(protected + "/") or protected.startswith(p + "/") for protected in paths["protected"]):
            raise PolicyError("Protected path declared writable")
        if any(p == i["path"] or p.startswith(i["path"] + "/") or i["path"].startswith(p + "/") for i in inputs):
            raise PolicyError("Input declared writable")
        if target.is_dir():
            raise PolicyError("Write scope must name files, not directories")
        if p in paths["writable"]:
            permitted = p in ("IMPLEMENTATION.md", "event-planning-coordination-brief/SKILL.md") or (
                p.startswith(("src/event_coordination/", "tests/")) and p.endswith(".py")) or (
                p.startswith("event-planning-coordination-brief/references/") and p.endswith(".md"))
            if not permitted or any(part.startswith(".") for part in p.split("/")):
                raise PolicyError("Path outside local development scope")
        else:
            permitted = {"deliverables/snapshots/" + OUTPUT_NAMES[s] for s in config["stages"]}
            if 8 in config["stages"]:
                permitted |= ARTIFACTS
            if p not in permitted:
                raise PolicyError("Output outside declared stage scope")
    policies = command_policy(config["stages"])
    if len({c["id"] for c in config["commands"]}) != len(config["commands"]):
        raise PolicyError("Duplicate command IDs")
    for c in config["commands"]:
        if policies.get(c["id"]) != c["argv"]:
            raise PolicyError("Command does not exactly match policy")


def inventory(root: Path, *, include_paths=()) -> dict:
    """Monitor bytes and entry types; protected and pinned paths override exclusions."""
    root = root.resolve(strict=True)
    required = tuple(PROTECTED) + tuple(include_paths)
    result = {}

    def traversal_error(error):
        raise PolicyError("Unreadable repository traversal") from None

    for directory, dirs, files in os.walk(root, followlinks=False, onerror=traversal_error):
        kept = []
        for name in sorted(dirs):
            rel = (Path(directory) / name).relative_to(root).as_posix()
            protected = any(rel == p or rel.startswith(p + "/") or p.startswith(rel + "/") for p in required)
            excluded = name in (".venv", "__pycache__", ".pytest_cache") or name.endswith(".egg-info")
            if protected or not excluded:
                kept.append(name)
        dirs[:] = kept
        for name in sorted(dirs + files):
            p = Path(directory) / name
            rel = p.relative_to(root).as_posix()
            mode = p.lstat().st_mode
            if stat.S_ISLNK(mode):
                result[rel] = "symlink:" + canonical_hash(os.readlink(p))
            elif stat.S_ISREG(mode):
                result[rel] = file_hash(p)
            elif stat.S_ISDIR(mode):
                result[rel] = "directory"
            else:
                raise PolicyError("Unsupported filesystem entry type")
    return dict(sorted(result.items()))


def protected_entries(config, root):
    for name in config["paths"]["protected"]:
        p = safe_path(root, name)
        if not p.exists() or not (p.is_file() or p.is_dir()):
            raise PolicyError("Missing protected entry")


def pinned_bytes(config, root):
    """Hash the exact immutable bytes callers parse; re-read at final validation."""
    buffers = {}
    for entry in sorted(config["inputs"], key=lambda x: x["path"]):
        p = safe_path(root, entry["path"])
        if not p.is_file():
            raise PolicyError("Missing pinned input")
        data = p.read_bytes()
        if "sha256:" + hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise PolicyError("Pinned input integrity mismatch")
        buffers[entry["path"]] = data
    return buffers


def exclusive_outputs(config, root):
    for name in config["paths"]["exclusive_outputs"]:
        p = safe_path(root, name)
        if p.exists() or p.is_symlink():
            raise PolicyError("Exclusive output collision")


def detect_changes(before: dict, after: dict) -> list[dict]:
    return [{"path": p, "before_sha256": before.get(p), "after_sha256": after.get(p)}
            for p in sorted(before.keys() | after.keys()) if before.get(p) != after.get(p)]


def _check(identifier, status, detail):
    return {"id": identifier, "status": status, "detail": detail}


class BatchState:
    """A planning-only state machine; no state grants actual authorization."""
    transitions = {
        "authorization": {"preflight", "stopped"},
        "preflight": {"execution-planning", "stopped"},
        "execution-planning": {"validation", "stopped"},
        "validation": {"reporting", "stopped"},
        "stopped": {"reporting"},
        "reporting": {"awaiting-review", "stopped"},
        "awaiting-review": set(),
    }

    def __init__(self):
        self.state = "authorization"
        self.history = [self.state]

    def advance(self, state):
        if state not in self.transitions[self.state]:
            raise PolicyError("Invalid simulated batch transition")
        self.state = state
        self.history.append(state)


def dry_run(config: dict, root: Path, *, expected_config_sha256=None) -> dict:
    """Validate and plan only. No command runner or authorization-granting path."""
    machine = BatchState()
    history = machine.history
    checks = []
    tasks = []
    report = {"report_version": VERSION, "mode": "dry-run", "authorization_status": "unverified",
              "authorization_notice": "Configuration is proposed scope, not proof of human authorization.",
              "approval_status": "pending", "commands_executed": [], "test_results": [],
              "proposed_decisions": [], "changed_files": [], "checks": checks, "tasks": tasks,
              "state_history": history, "source_references": [], "unresolved_conditions": [],
              "execution_timestamps": None, "checkpoint": "No live execution, decisions, snapshot generation or next-stage advancement authorized."}
    before = None
    monitoring = ()
    try:
        digest = canonical_hash(config)
        report["config_sha256"] = digest
        validate_config(config, root)
        report["proposed_scope"] = {"stages": deepcopy(config["stages"]), "paths": {kind: [{"path_sha256": canonical_hash(path)} for path in paths]
                                              for kind, paths in config["paths"].items()},
                                    "checkpoint": deepcopy(config["checkpoint"])}
        checks.append(_check("configuration", "passed", "Strict dry-run configuration and command policy validated."))
        if expected_config_sha256 is not None and digest != expected_config_sha256:
            raise PolicyError("Configuration differs from externally supplied scope hash")
        checks.append(_check("scope-pin", "passed" if expected_config_sha256 else "not-run", "External scope hash matched." if expected_config_sha256 else "No external scope pin supplied; proposal only."))
        machine.advance("preflight")
        protected_entries(config, root)
        monitoring = tuple(config["paths"]["protected"]) + tuple(e["path"] for e in config["inputs"])
        before = inventory(root, include_paths=monitoring)
        buffers = pinned_bytes(config, root)
        report["source_references"] = [{"path_sha256": canonical_hash(e["path"]), "sha256": e["sha256"]}
                                       for e in sorted(config["inputs"], key=lambda x: x["path"])]
        exclusive_outputs(config, root)
        from event_coordination.validation import validate_snapshot
        predecessor = json.loads(buffers[PREDECESSOR])
        validate_snapshot(predecessor, root)
        if (predecessor["snapshot_id"] != PREDECESSOR_ID or predecessor["run_id"] != RUN_ID
                or predecessor["state"]["business_clock"] != CLOCK):
            raise PolicyError("Predecessor run/clock mismatch")
        report["predecessor"] = {"snapshot_id": predecessor["snapshot_id"], "path": PREDECESSOR, "sha256": PREDECESSOR_HASH}
        report["run_id"] = RUN_ID
        report["business_clock"] = CLOCK
        report["unresolved_conditions"] = [{"id": r["id"], "summary": r["summary"]} for r in sorted(predecessor["unresolved"], key=lambda r: r["id"])]
        report["approval_requirements"] = [{"id": g["id"], "status": g["status"]} for g in predecessor["state"]["approval_requirements"]]
        checks.append(_check("input-manifest", "passed", "Pinned predecessor and recursively verified evidence validated."))
        machine.advance("execution-planning")
        for c in config["commands"]:
            tasks.append({"id": c["id"], "argv": deepcopy(c["argv"]), "status": "not-run", "reason": "Dry-run only; no command executor exists."})
        machine.advance("validation")
        checks.append(_check("live-execution", "skipped", "Intentionally disabled in this milestone."))
        checks.append(_check("development-tests", "not-run", "Planned test commands were not executed by this dry-run."))
    except (ValueError, OSError, KeyError, TypeError, StopIteration, ValidationError) as error:
        checks.append({"id": "batch-policy", "status": "failed", **safe_error(error)})
        checks.append(_check("dependent-tasks", "skipped", "Stopped before dependent execution planning."))
    finally:
        if before is None:
            checks.append(_check("repository-unchanged", "not-run", "Preflight monitoring did not start."))
        else:
            try:
                changes = detect_changes(before, inventory(root, include_paths=monitoring))
                report["changed_files"] = changes
                checks.append(_check("repository-unchanged", "failed" if changes else "passed", "Unexpected changes detected." if changes else "Monitored repository bytes and entry types unchanged."))
                protected_entries(config, root)
                pinned_bytes(config, root)
                exclusive_outputs(config, root)
                checks.append(_check("final-integrity", "passed", "Pinned inputs, protections and exclusive outputs rechecked."))
            except (ValueError, OSError, KeyError, TypeError) as error:
                checks.append({"id": "final-integrity", "status": "failed", **safe_error(error)})
    failed = any(c["status"] == "failed" for c in checks)
    if failed:
        machine.advance("stopped")
    machine.advance("reporting")
    report["final_state"] = "stopped" if failed else "awaiting-review"
    machine.advance(report["final_state"])
    report["checks"] = sorted(checks, key=lambda c: c["id"])
    report["tasks"] = sorted(tasks, key=lambda c: c["id"])
    return report


def example_config() -> dict:
    """A scope proposal only; no claim of authorization and no writable outputs."""
    return {"protocol_version": VERSION, "mode": "dry-run", "authorization": {"scope_reference": "Demo proposal; no authorization asserted"},
            "stages": [7], "business_clock": CLOCK, "business_timezone": "Asia/Taipei", "run_id": RUN_ID,
            "inputs": [{"path": PREDECESSOR, "sha256": PREDECESSOR_HASH}],
            "paths": {"writable": [], "exclusive_outputs": [], "protected": list(PROTECTED)},
            "commands": [{"id": "regression-tests", "argv": command_policy([7])["regression-tests"], "cwd": ".", "environment": {"PYTHONDONTWRITEBYTECODE": "1"}}],
            "checkpoint": {"after": list(CHECKPOINTS), "require_review_before": list(REVIEW_BEFORE)},
            "forbidden_actions": list(FORBIDDEN), "execution": {"enabled": False, "network_enabled": False}}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError("Duplicate JSON key")
        result[key] = value
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run supervised local batch planning; never executes configured commands.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--config", help="Repository-relative JSON configuration path")
    group.add_argument("--demo", action="store_true", help="Plan a built-in example scope, without creating configuration files")
    group.add_argument("--print-example", action="store_true", help="Print the versioned example JSON configuration to stdout")
    parser.add_argument("--expected-config-sha256", help="External scope pin; never interpreted as human approval")
    args = parser.parse_args(argv)
    if args.print_example:
        print(json.dumps(example_config(), sort_keys=True, indent=2))
        return 0
    try:
        root = args.project_root.resolve(strict=True)
        config = example_config() if args.demo else json.loads(safe_path(root, args.config).read_bytes(), object_pairs_hook=_unique_object)
        report = dry_run(config, root, expected_config_sha256=args.expected_config_sha256)
    except (ValueError, OSError, TypeError) as error:
        print(json.dumps({"final_state": "stopped", "checks": [{"id": "configuration-load", "status": "failed", **safe_error(error)}]}, sort_keys=True, indent=2))
        return 1
    print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))
    return 1 if report["final_state"] == "stopped" else 0


if __name__ == "__main__":
    raise SystemExit(main())
