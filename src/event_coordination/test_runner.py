"""Fail-closed supervised test runner foundation.

Operational execution is disabled: no trusted human-authorization issuer is
integrated. Private backend functions are exercised only by authorized fixture
tests. They are not an authenticated API or a security boundary against callers
who already control the parent Python process.
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import tempfile
from xml.etree import ElementTree

from jsonschema import Draft202012Validator, ValidationError

from event_coordination import automation as policy
from event_coordination.isolated_runtime import NAMESPACES, TASKS

VERSION = "isolated-tests/1"
HELPER_BYTES = Path(__file__).with_name("isolated_runtime.py").read_bytes()
HELPER_SHA256 = "sha256:" + hashlib.sha256(HELPER_BYTES).hexdigest()
AUTH_UNAVAILABLE = "AUTHORIZATION_PROVIDER_UNAVAILABLE"
LOG = ".entire/logs/entire.log"
COPY_DIRS = ("src", "tests", "interviews", "evidence", "deliverables/snapshots")
COPY_FILES = ("README.md", "snapshot.schema.json", "pyproject.toml")
PLAN_SCHEMA = policy.obj({
    "version": {"const": VERSION},
    "business_clock": {"const": policy.CLOCK},
    "run_id": {"const": policy.RUN_ID},
    "tasks": {"type": "array", "minItems": 1, "maxItems": 3, "items": policy.obj({
        "id": {"enum": list(TASKS)}, "argv": {"type": "array", "items": {"type": "string"}}})},
    "inputs": {"type": "array", "minItems": 1, "items": policy.obj({"path": policy.TEXT, "sha256": policy.HASH})},
})


def example_plan():
    return {"version": VERSION, "business_clock": policy.CLOCK, "run_id": policy.RUN_ID,
            "tasks": [{"id": "automation-tests", "argv": list(TASKS["automation-tests"])}],
            "inputs": [{"path": policy.PREDECESSOR, "sha256": policy.PREDECESSOR_HASH}]}


def validate_plan(plan, root):
    Draft202012Validator(PLAN_SCHEMA).validate(plan)
    if len({t["id"] for t in plan["tasks"]}) != len(plan["tasks"]):
        raise policy.PolicyError("DUPLICATE_TASK")
    for task in plan["tasks"]:
        if task["argv"] != list(TASKS[task["id"]]):
            raise policy.PolicyError("COMMAND_POLICY_MISMATCH")
    if {"path": policy.PREDECESSOR, "sha256": policy.PREDECESSOR_HASH} not in plan["inputs"]:
        raise policy.PolicyError("PREDECESSOR_REQUIRED")
    if len({i["path"] for i in plan["inputs"]}) != len(plan["inputs"]):
        raise policy.PolicyError("DUPLICATE_INPUT")
    for entry in plan["inputs"]:
        policy.safe_path(root, entry["path"])


@dataclass(frozen=True)
class _Log:
    identity: tuple
    sha256: str
    prefix_sha256: str
    tail_sha256: str

    @property
    def size(self):
        return self.identity[2]


def _log_identity(st):
    return (st.st_dev, st.st_ino, st.st_size, stat.S_IMODE(st.st_mode),
            st.st_mtime_ns, st.st_ctime_ns, st.st_nlink)


def _observe_log(root, prefix_size=0):
    """No-follow directory/file descriptors; one stable, bounded-length observation."""
    descriptors = []
    links = []
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        descriptors.append(directory)
        try:
            for part in LOG.split("/")[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                                dir_fd=directory)
                descriptors.append(child)
                links.append((directory, part, child))
                directory = child
            fd = os.open(LOG.split("/")[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory)
        except FileNotFoundError:
            return None
        descriptors.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or prefix_size > before.st_size:
            raise policy.PolicyError("INVALID_LOG_ENTRY")
        full, prefix, tail = hashlib.sha256(), hashlib.sha256(), hashlib.sha256()
        position = 0
        while position < before.st_size:
            block = os.read(fd, min(65536, before.st_size - position))
            if not block:
                raise policy.PolicyError("UNSTABLE_LOG_OBSERVATION")
            full.update(block)
            split = min(len(block), max(0, prefix_size - position))
            prefix.update(block[:split]); tail.update(block[split:])
            position += len(block)
        after = os.fstat(fd)
        named = os.stat(LOG.split("/")[-1], dir_fd=directory, follow_symlinks=False)
        if _log_identity(before) != _log_identity(after) or _log_identity(after) != _log_identity(named):
            raise policy.PolicyError("UNSTABLE_LOG_OBSERVATION")
        for parent, name, child in links:
            a, b = os.fstat(child), os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (a.st_dev, a.st_ino, a.st_mode) != (b.st_dev, b.st_ino, b.st_mode):
                raise policy.PolicyError("UNSTABLE_LOG_DIRECTORY")
        return _Log(_log_identity(after), "sha256:" + full.hexdigest(),
                    "sha256:" + prefix.hexdigest(), "sha256:" + tail.hexdigest())
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def _snapshot(root, inputs=()):
    """Monitor protected bytes/types/modes, observing the log only through safe FDs."""
    root = root.resolve(strict=True)
    required = tuple(policy.PROTECTED) + tuple(inputs)
    tree = {}
    def traversal_error(error):
        raise error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=traversal_error):
        keep = []
        for name in sorted(dirs):
            rel = (Path(directory) / name).relative_to(root).as_posix()
            protected = any(rel == p or rel.startswith(p + "/") or p.startswith(rel + "/") for p in required)
            excluded = name in (".venv", "__pycache__", ".pytest_cache") or name.endswith(".egg-info")
            if protected or not excluded:
                keep.append(name)
        dirs[:] = keep
        for name in sorted(dirs + files):
            rel = (Path(directory) / name).relative_to(root).as_posix()
            if rel == LOG:
                continue
            p = policy.safe_path(root, rel)
            st = p.lstat()
            if stat.S_ISDIR(st.st_mode):
                value = "directory"
            elif stat.S_ISREG(st.st_mode):
                value = policy.file_hash(p)
            else:
                raise policy.PolicyError("UNSAFE_MONITORED_ENTRY")
            tree[rel] = value + ":mode=" + oct(stat.S_IMODE(st.st_mode))
    log = _observe_log(root)
    if log:
        tree[LOG] = log.sha256 + ":mode=" + oct(log.identity[3])
    return dict(sorted(tree.items())), log


def _compare(root, before, after):
    old, oldlog = before
    new, newlog = after
    changes = policy.detect_changes(old, new)
    activity = []
    if oldlog or newlog:
        prefix_size = min(oldlog.size, newlog.size) if oldlog and newlog else 0
        current = _observe_log(root, prefix_size)
        if ((current is None) != (newlog is None) or
                (current is not None and (current.identity != newlog.identity or current.sha256 != newlog.sha256))):
            raise policy.PolicyError("LOG_CHANGED_AFTER_SNAPSHOT")
        same_file = oldlog and newlog and oldlog.identity[:2] == newlog.identity[:2]
        if (same_file and newlog.size >= oldlog.size and oldlog.identity[3] == newlog.identity[3]
                and oldlog.identity[6] == newlog.identity[6] and current.prefix_sha256 == oldlog.sha256):
            if newlog.size > oldlog.size:
                changes = [c for c in changes if c["path"] != LOG]
                activity.append({"kind": "unattributed-append-only-entire-log", "bytes": newlog.size - oldlog.size,
                                 "sha256": current.tail_sha256})
        elif oldlog != newlog and not any(c["path"] == LOG for c in changes):
            changes.append({"path": LOG, "before_sha256": oldlog.sha256 if oldlog else None,
                            "after_sha256": newlog.sha256 if newlog else None})
    return changes, activity


def _preflight(plan, root):
    validate_plan(plan, root)
    config = policy.example_config()
    config["inputs"] = plan["inputs"]
    policy.protected_entries(config, root)
    data = policy.pinned_bytes(config, root)
    predecessor = json.loads(data[policy.PREDECESSOR])
    if (predecessor["snapshot_id"] != policy.PREDECESSOR_ID or predecessor["run_id"] != policy.RUN_ID
            or predecessor["state"]["business_clock"] != policy.CLOCK):
        raise policy.PolicyError("PREDECESSOR_MISMATCH")
    from event_coordination.validation import validate_snapshot
    validate_snapshot(predecessor, root)


def review_batch(plan, root, *, authorization=None):
    """Public entry point: no config, token, object or argument grants authority."""
    report = {"version": VERSION, "state": "stopped", "authorization": "unverified",
              "commands_executed": [], "tasks": [], "checks": [], "business_clock": policy.CLOCK}
    try:
        validate_plan(plan, root)
        report["scope_sha256"] = policy.canonical_hash(plan)
        report["tasks"] = [{"id": t["id"], "status": "not-run"} for t in plan["tasks"]]
        if authorization is not None:
            raise policy.PolicyError("UNTRUSTED_AUTHORIZATION")
        _preflight(plan, root)
        report["checks"].append({"id": "preflight", "status": "passed"})
        report["checks"].append({"id": "authorization", "status": "failed", "code": AUTH_UNAVAILABLE})
    except (ValueError, OSError, KeyError, TypeError, ValidationError) as error:
        report["checks"].append({"id": "policy", "status": "failed", **policy.safe_error(error)})
    return report


def _copy_project(source, destination, expected=None):
    """Copy only reviewed project areas; never metadata, credentials, or links."""
    names = []
    for directory in COPY_DIRS:
        p = policy.safe_path(source, directory)
        if not p.is_dir():
            raise policy.PolicyError("COPY_INPUT_MISSING")
        for current, dirs, files in os.walk(p, followlinks=False, onerror=lambda e: (_ for _ in ()).throw(e)):
            # Generated caches are not executable project inputs.
            dirs[:] = sorted(d for d in dirs if not (directory in ("src", "tests") and
                             (d in ("__pycache__", ".pytest_cache") or d.endswith(".egg-info"))))
            for name in dirs + files:
                entry = Path(current) / name
                if entry.is_symlink() or not (entry.is_dir() or entry.is_file()):
                    raise policy.PolicyError("COPY_UNSAFE_ENTRY")
            names.extend((Path(current) / f).relative_to(source).as_posix() for f in sorted(files))
    names.extend(COPY_FILES)
    for name in sorted(names):
        src = policy.safe_path(source, name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        if expected is not None and expected.get(name, "").split(":mode=")[0] != "sha256:" + hashlib.sha256(data).hexdigest():
            raise policy.PolicyError("COPY_INPUT_CHANGED")
        with target.open("xb") as stream:
            stream.write(data)
        if policy.file_hash(target) != "sha256:" + hashlib.sha256(data).hexdigest():
            raise policy.PolicyError("COPY_HASH_MISMATCH")
    (destination / ".venv").mkdir()


def _runtime_tree(runtime):
    # Pin all runtime files/links, even generated cache names. Do not follow links.
    result = {}
    for current, dirs, files in os.walk(runtime, followlinks=False, onerror=lambda e: (_ for _ in ()).throw(e)):
        for name in sorted(dirs + files):
            p = Path(current) / name
            rel = p.relative_to(runtime).as_posix()
            if p.is_symlink():
                target = p.resolve(strict=True)
                if not (target.is_relative_to(runtime) or target.is_relative_to(Path("/usr"))):
                    raise policy.PolicyError("RUNTIME_LINK_ESCAPE")
                result[rel] = policy.canonical_hash(os.readlink(p))
            elif p.is_file():
                result[rel] = policy.file_hash(p)
            elif p.is_dir():
                result[rel] = "directory"
            else:
                raise policy.PolicyError("RUNTIME_UNSAFE_ENTRY")
            result[rel] += ":mode=" + oct(stat.S_IMODE(p.lstat().st_mode))
    return result


@dataclass(frozen=True)
class _Proposal:
    """The only execution proposal is canonical immutable bytes, never live config."""
    encoded: bytes
    sha256: str

    @classmethod
    def pin(cls, plan, root):
        encoded = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        frozen = json.loads(encoded)
        validate_plan(frozen, root)
        result = cls(encoded, policy.canonical_hash(frozen))
        result.check_live(plan)
        return result

    def decode(self):
        return json.loads(self.encoded)

    def check_live(self, plan):
        if policy.canonical_hash(plan) != self.sha256:
            raise policy.PolicyError("SCOPE_CHANGED")

    def preflight(self, live, root):
        self.check_live(live)
        isolated = self.decode()
        _preflight(isolated, root)
        # Detect changes made during preflight, including mutation of its local view.
        self.check_live(isolated)
        self.check_live(live)


def _pytest_results(stdout, xml):
    """Cross-check the terminal summary, actual JUnit cases and suite counters.

    These are consistency checks, not attestation against malicious test code.
    """
    counts = {}
    summary = re.compile(r"^\s*(?:=+\s*)?(?P<items>\d+ (?:passed|failed|skipped|errors?|xfailed|xpassed|deselected)"
                         r"(?:, \d+ (?:passed|failed|skipped|errors?|xfailed|xpassed|deselected))*)"
                         r"(?:, \d+ warnings?)? in \d+(?:\.\d+)?s(?: \([^\n]*\))?\s*(?:=+)?\s*$")
    matches = [match for line in stdout.splitlines() if (match := summary.fullmatch(line))]
    if len(matches) != 1:
        return counts, "PYTEST_SUMMARY_MISSING_OR_INCONSISTENT"
    for number, name in re.findall(r"(\d+) (\w+)", matches[0]["items"]):
        name = "errors" if name == "error" else name
        if name in counts or int(number) <= 0:
            return counts, "PYTEST_SUMMARY_INCONSISTENT"
        counts[name] = int(number)
    reported_failure = bool(counts.get("failed") or counts.get("errors") or counts.get("xpassed"))
    if not xml or len(xml) > 2 * 1024**2 or b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        return counts, "PYTEST_RESULTS_MISSING_OR_INVALID"
    try:
        root = ElementTree.fromstring(xml.decode("utf-8"))
        # Never ignore a reported failure, even in an unsupported location.
        if any(node.tag in ("failure", "error") for node in root.iter()):
            return counts, "PYTEST_REPORTED_FAILURE"

        def children(node, allowed, repeatable=()):
            if node.text and node.text.strip():
                raise ValueError
            seen = set()
            for child in node:
                if child.tag not in allowed or (child.tag in seen and child.tag not in repeatable):
                    raise ValueError
                if child.tail and child.tail.strip():
                    raise ValueError
                seen.add(child.tag)
                if child.tag in ("system-out", "system-err", "skipped", "property") and len(child):
                    raise ValueError
                if child.tag == "properties":
                    children(child, {"property"}, {"property"})

        if root.tag != "testsuites":
            raise ValueError
        children(root, {"testsuite"})
        suites = list(root)
        if len(suites) != 1:
            raise ValueError
        suite = suites[0]
        children(suite, {"testcase", "properties", "system-out", "system-err"}, {"testcase"})
        cases = suite.findall("testcase")
        for case in cases:
            children(case, {"skipped", "properties", "system-out", "system-err"})
        skipped = sum(len(c.findall("skipped")) for c in cases)
        expected = {"tests": len(cases), "failures": 0, "errors": 0, "skipped": skipped}
        if not cases or any(not c.get("name") or not c.get("classname") for c in cases):
            raise ValueError
        for key, number in expected.items():
            value = suite.get(key, "")
            if not re.fullmatch(r"[0-9]+", value) or int(value) != number:
                raise ValueError
            if key in root.attrib and (not re.fullmatch(r"[0-9]+", root.get(key)) or int(root.get(key)) != number):
                raise ValueError
        if (counts.get("passed", 0) + counts.get("xpassed", 0) != len(cases) - skipped
                or counts.get("skipped", 0) + counts.get("xfailed", 0) != skipped
                or counts.get("deselected", 0)):
            raise ValueError
    except (ElementTree.ParseError, ValueError, TypeError, UnicodeError):
        return counts, "PYTEST_RESULTS_INCONSISTENT"
    if reported_failure:
        return counts, "PYTEST_REPORTED_FAILURE"
    if not counts.get("passed"):
        return counts, "NO_PASSING_TESTS_REPORTED"
    return counts, "PASSED"


@dataclass(frozen=True)
class _Launch:
    task: str
    argv: tuple
    launch_argv: tuple
    pid: int
    started_at: str


@dataclass(frozen=True)
class _Outcome:
    task: str
    status: str
    exit_code: int | None
    reason: str
    output_sha256: str | None
    launch_argv: tuple
    counts: dict
    started_at: str | None = None
    finished_at: str | None = None
    launched: bool = True
    launch: _Launch | None = None
    failures: tuple = ()


def _run_task(task, copy, runtime, storage, *, timeout=600):
    """Private fixture-tested backend. Calling Python code is trusted, not authorized by config."""
    if task not in TASKS or type(timeout) not in (int, float) or not 0 < timeout <= 600:
        raise policy.PolicyError("INVALID_TASK_OR_TIMEOUT")
    launch = None
    process = None
    failures = []
    counts = {}
    output_hash = None
    argv = ()
    phase = "LAUNCH_FAILED"
    try:
        storage.mkdir()
        root = storage / "root"
        root.mkdir()
        script = storage / "setup.py"
        script.write_bytes(HELPER_BYTES)
        namespaces = {name: os.readlink(f"/proc/self/ns/{name}") for name in NAMESPACES}
        with (storage / "stdout").open("wb") as out, (storage / "stderr").open("wb") as err, (storage / "results.xml").open("w+b") as result:
            argv = ("/usr/bin/unshare", "--user", "--map-root-user", "--mount", "--pid", "--net", "--ipc", "--fork",
                    "--kill-child=KILL", "/usr/bin/python3", "-I", str(script), str(root), str(copy),
                    str(runtime), task, json.dumps(namespaces, sort_keys=True), str(result.fileno()))
            process = subprocess.Popen(argv, cwd=storage, env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
                                       stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                       shell=False, close_fds=True, pass_fds=(result.fileno(),), start_new_session=True)
            # Pin successful creation before waiting, cleanup, or artifact access.
            launch = _Launch(task, tuple(TASKS[task]), argv, process.pid, datetime.now(timezone.utc).isoformat())
            phase = "EXECUTION_FAILED"
            try:
                process.wait(timeout=timeout)
                if process.returncode != 0:
                    failures.append("TASK_OR_ISOLATION_FAILED")
            except subprocess.TimeoutExpired:
                failures.append("TIMEOUT")
            except (OSError, ValueError, subprocess.SubprocessError):
                failures.append("EXECUTION_FAILED")
            finally:
                phase = "CLEANUP_FAILED"
                try:
                    os.killpg(launch.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except (OSError, ValueError):
                    failures.append("CLEANUP_FAILED")
                try:
                    process.wait(timeout=5)
                except (OSError, ValueError, subprocess.SubprocessError):
                    failures.append("CLEANUP_FAILED")
        phase = "RESULT_READING_FAILED"
        xml = (storage / "results.xml").read_bytes()
        stdout = (storage / "stdout").read_bytes()
        stderr = (storage / "stderr").read_bytes()
        output_hash = "sha256:" + hashlib.sha256(stdout + b"\0" + stderr + b"\0" + xml).hexdigest()
        counts, validation = _pytest_results(stdout.decode(errors="replace"), xml)
        if validation != "PASSED":
            failures.append(validation)
    except (OSError, ValueError, subprocess.SubprocessError):
        failures.append(phase)
    reason = failures[0] if failures else "PASSED"
    return _Outcome(task, "failed" if failures else "passed", process.returncode if process else None,
                    reason, output_hash, launch.launch_argv if launch else argv, counts,
                    launch.started_at if launch else None, datetime.now(timezone.utc).isoformat(),
                    launch is not None, launch, tuple(dict.fromkeys(failures)))


def _fixture_batch(plan, root, runtime, *, timeout=600):
    """Backend integration harness; NOT public authorization ingestion.

    Used by synthetic tests only. Operational CLI never calls this function.
    """
    proposal = _Proposal.pin(plan, root)
    proposal.preflight(plan, root)
    scope = proposal.sha256
    frozen = proposal.decode()
    tasks = frozen["tasks"]
    inputs = tuple(i["path"] for i in frozen["inputs"])
    before = _snapshot(root, inputs)
    runtime_before = _runtime_tree(runtime)
    report = {"scope_sha256": scope, "tasks": [], "state": "validating", "activity": [],
              "authorization": "fixture-only-not-operational", "business_clock": policy.CLOCK,
              "run_id": policy.RUN_ID, "helper_sha256": HELPER_SHA256}
    report["execution_scope_sha256"] = policy.canonical_hash({"plan": scope, "project": before[0],
                                                             "runtime": runtime_before, "helper": HELPER_SHA256})
    with tempfile.TemporaryDirectory(prefix="event-isolated-tests-") as temp:
        storage = Path(temp)
        copy = storage / "project"
        copy.mkdir()
        _copy_project(root, copy, before[0])
        copy_before = _snapshot(copy)

        def integrity():
            proposal.preflight(plan, root)
            changes, activity = _compare(root, before, _snapshot(root, inputs))
            if changes or _runtime_tree(runtime) != runtime_before or _snapshot(copy) != copy_before:
                raise policy.PolicyError("UNEXPECTED_CHANGE")
            proposal.check_live(plan)
            return activity

        for index, task in enumerate(tasks):
            outcome = None
            try:
                integrity()
                outcome = _run_task(task["id"], copy, runtime, storage / str(index), timeout=timeout)
                report["activity"] = integrity()
                entry = {"id": task["id"], "status": outcome.status, "exit_code": outcome.exit_code,
                         "reason": outcome.reason, "output_sha256": outcome.output_sha256,
                         "argv": list(outcome.launch.argv if outcome.launch else TASKS[outcome.task]), "launch_argv": list(outcome.launch_argv),
                         "test_counts": outcome.counts, "launched": outcome.launched,
                         "failure_codes": list(outcome.failures),
                         "pid": outcome.launch.pid if outcome.launch else None,
                         "started_at": outcome.started_at, "finished_at": outcome.finished_at}
            except (ValueError, OSError, KeyError, TypeError, ValidationError):
                entry = {"id": task["id"], "status": "failed", "reason": "PREFLIGHT_OR_INTEGRITY_FAILED",
                         "launched": outcome.launched if outcome else False, "exit_code": outcome.exit_code if outcome else None}
                if outcome is not None:
                    entry.update(argv=list(outcome.launch.argv if outcome.launch else TASKS[outcome.task]), launch_argv=list(outcome.launch_argv),
                                 failure_codes=list(outcome.failures), pid=outcome.launch.pid if outcome.launch else None,
                                 output_sha256=outcome.output_sha256, test_counts=outcome.counts,
                                 started_at=outcome.started_at, finished_at=outcome.finished_at)
            report["tasks"].append(entry)
            if entry["status"] != "passed":
                report["state"] = "stopped"
                report["tasks"].extend({"id": t["id"], "status": "skipped", "launched": False}
                                       for t in tasks[index + 1:])
                break
        if report["state"] != "stopped":
            try:
                report["activity"] = integrity()
                proposal.check_live(plan)
                report["final_validation"] = "passed"
                report["state"] = "awaiting-review"
            except (ValueError, OSError, KeyError, TypeError, ValidationError):
                report["final_validation"] = "failed"
                report["stop_reason"] = "FINAL_SCOPE_OR_INTEGRITY_FAILED"
                report["state"] = "stopped"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Isolated test-runner preflight. Operational execution is disabled: no trusted authorization provider.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--print-example", action="store_true")
    parser.add_argument("--config", help="Repository-relative bounded batch proposal; never authorization")
    args = parser.parse_args(argv)
    if args.print_example:
        print(json.dumps(example_plan(), sort_keys=True, indent=2))
        return 0
    try:
        root = args.project_root.resolve(strict=True)
        plan = example_plan() if not args.config else json.loads(policy.safe_path(root, args.config).read_bytes(), object_pairs_hook=policy._unique_object)
        report = review_batch(plan, root)
    except (ValueError, OSError, TypeError, ValidationError) as error:
        report = {"state": "stopped", "commands_executed": [], "checks": [policy.safe_error(error)]}
    print(json.dumps(report, sort_keys=True, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
