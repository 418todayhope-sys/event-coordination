"""Synthetic isolation tests. No project writes, external endpoints or approvals."""

from copy import deepcopy
import ctypes
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time

import pytest

from event_coordination import automation as policy
from event_coordination import test_runner as runner

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".venv"


@pytest.fixture
def project(tmp_path):
    for directory in runner.COPY_DIRS:
        shutil.copytree(ROOT / directory, tmp_path / directory, ignore=shutil.ignore_patterns("__pycache__"))
    for name in runner.COPY_FILES:
        shutil.copyfile(ROOT / name, tmp_path / name)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git/config").write_text("synthetic fixture only")
    (tmp_path / ".entire/logs").mkdir(parents=True)
    (tmp_path / runner.LOG).write_bytes(b"synthetic old log\n")
    (tmp_path / ".entire/settings.local.json").write_text('{"strategy_options":{"push_sessions":false}}')
    return tmp_path


@pytest.mark.parametrize("authorization", [None, True, False, 1, 0, {}, {"approved": True}, "approved", object()])
def test_public_api_never_accepts_forged_authority(tmp_path, monkeypatch, authorization):
    monkeypatch.setattr(runner, "_preflight", lambda *args: None)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: pytest.fail("public API executed"))
    report = runner.review_batch(runner.example_plan(), tmp_path, authorization=authorization)
    assert report["state"] == "stopped" and report["authorization"] == "unverified"
    assert report["commands_executed"] == []
    assert all(t["status"] == "not-run" for t in report["tasks"])


@pytest.mark.parametrize("mutation", ["id", "shell", "extra-argument", "environment", "approval", "hash", "path", "duplicate"])
def test_malformed_scope_and_injection_fail(tmp_path, mutation):
    plan = runner.example_plan()
    secret = "SYNTHETIC-SECRET-NEVER-ECHO"
    if mutation == "id": plan["tasks"][0]["id"] = secret
    elif mutation == "shell": plan["tasks"][0]["argv"] = secret + "; git push"
    elif mutation == "extra-argument": plan["tasks"][0]["argv"].append(secret)
    elif mutation == "environment": plan["environment"] = {"LD_PRELOAD": secret}
    elif mutation == "approval": plan["authorization"] = {"approved": True, "token": secret}
    elif mutation == "hash": plan["inputs"][0]["sha256"] = secret
    elif mutation == "path": plan["inputs"][0]["path"] = "../" + secret
    else: plan["tasks"].append(deepcopy(plan["tasks"][0]))
    report = runner.review_batch(plan, tmp_path)
    assert report["state"] == "stopped" and not report["commands_executed"]
    assert secret not in json.dumps(report)


def test_real_preflight_remains_disabled(project):
    a = runner.review_batch(runner.example_plan(), project)
    b = runner.review_batch(runner.example_plan(), project)
    assert a == b
    assert a["checks"] == [{"id": "preflight", "status": "passed"},
                           {"id": "authorization", "status": "failed", "code": runner.AUTH_UNAVAILABLE}]


def test_append_only_log_exception_is_narrow(project):
    before = runner._snapshot(project)
    with (project / runner.LOG).open("ab") as f: f.write(b"synthetic concurrent append")
    changes, activity = runner._compare(project, before, runner._snapshot(project))
    assert changes == [] and activity[0]["kind"] == "unattributed-append-only-entire-log"
    (project / ".git/config").write_text("unauthorized")
    changes, _ = runner._compare(project, before, runner._snapshot(project))
    assert any(c["path"] == ".git/config" for c in changes)


@pytest.mark.parametrize("kind", ["truncate", "replace", "settings", "cache-evidence", "empty-directory", "mode"])
def test_unauthorized_changes_detected(project, kind):
    before = runner._snapshot(project)
    if kind == "truncate": (project / runner.LOG).write_bytes(b"")
    elif kind == "replace":
        p = project / runner.LOG; p.unlink(); p.write_bytes(b"replacement log")
    elif kind == "settings": (project / ".entire/settings.local.json").write_text("changed")
    elif kind == "cache-evidence":
        p = project / "evidence/__pycache__"; p.mkdir(); (p / "fixture").write_text("changed")
    elif kind == "empty-directory": (project / "unexpected").mkdir()
    else: (project / "README.md").chmod(0o600)
    changes, _ = runner._compare(project, before, runner._snapshot(project))
    assert changes


def test_copy_rejects_symlinks(project, tmp_path):
    (project / "src/escape.py").symlink_to("/etc/passwd")
    target = tmp_path / "copy"; target.mkdir()
    with pytest.raises(policy.PolicyError): runner._copy_project(project, target)


def test_copy_must_match_pinned_bytes(project, tmp_path):
    expected, _ = runner._snapshot(project)
    (project / "README.md").write_bytes(b"synthetic changed bytes")
    target = tmp_path / "copy"; target.mkdir()
    with pytest.raises(policy.PolicyError): runner._copy_project(project, target, expected)


def test_scope_change_skips_dependent_tasks(project, monkeypatch):
    plan = runner.example_plan()
    plan["tasks"].append({"id": "stage6-tests", "argv": list(runner.TASKS["stage6-tests"])})
    def simulated(*args, **kwargs):
        plan["business_clock"] = "changed"
        return runner._Outcome("automation-tests", "passed", 0, "PASSED", "hash", (), {"passed": 1})
    monkeypatch.setattr(runner, "_run_task", simulated)
    # No real runtime needed for this unit failure probe.
    runtime = project / "synthetic-runtime"; runtime.mkdir()
    report = runner._fixture_batch(plan, project, runtime)
    assert report["state"] == "stopped"
    assert report["tasks"][-1]["status"] == "skipped"


def test_post_task_tampering_stops(project, monkeypatch):
    def tamper(*args, **kwargs):
        (project / "README.md").write_text("synthetic tamper")
        return runner._Outcome("automation-tests", "passed", 0, "PASSED", "hash", (), {"passed": 1})
    monkeypatch.setattr(runner, "_run_task", tamper)
    runtime = project / "synthetic-runtime"; runtime.mkdir()
    report = runner._fixture_batch(runner.example_plan(), project, runtime)
    assert report["state"] == "stopped" and report["tasks"][0]["launched"]


def test_task_ids_and_timeout_bounds(tmp_path):
    for task, timeout in [("git push", 1), ("automation-tests", True), ("automation-tests", 601)]:
        with pytest.raises(policy.PolicyError): runner._run_task(task, tmp_path, RUNTIME, tmp_path / "out", timeout=timeout)


def test_valid_scope_mutation_after_last_task_is_rejected(project, monkeypatch):
    plan = runner.example_plan()
    def mutate(*args, **kwargs):
        plan["tasks"][0] = {"id": "stage6-tests", "argv": list(runner.TASKS["stage6-tests"])}
        return runner._Outcome("automation-tests", "passed", 0, "PASSED", "hash", ("actual-automation-launch",), {"passed": 1})
    monkeypatch.setattr(runner, "_run_task", mutate)
    runtime = project / "synthetic-runtime"; runtime.mkdir()
    report = runner._fixture_batch(plan, project, runtime)
    assert report["state"] == "stopped"
    assert report["tasks"][0]["id"] == "automation-tests"
    assert report["tasks"][0]["launch_argv"] == ["actual-automation-launch"]


@pytest.mark.parametrize("reason", ["TIMEOUT", "TASK_OR_ISOLATION_FAILED"])
def test_failure_stops_remaining_tasks(project, monkeypatch, reason):
    plan = runner.example_plan()
    plan["tasks"].append({"id": "stage6-tests", "argv": list(runner.TASKS["stage6-tests"])})
    calls = []
    def failed(task, *args, **kwargs):
        calls.append(task)
        return runner._Outcome(task, "failed", 125, reason, "hash", (), {})
    monkeypatch.setattr(runner, "_run_task", failed)
    runtime = project / "synthetic-runtime"; runtime.mkdir()
    report = runner._fixture_batch(plan, project, runtime)
    assert calls == ["automation-tests"]
    assert report["tasks"][1]["status"] == "skipped"


def test_missing_or_changed_pinned_evidence_never_launches(project, monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("launched with tampered evidence"))
    p = project / policy.PREDECESSOR
    p.write_bytes(p.read_bytes() + b"changed")
    report = runner.review_batch(runner.example_plan(), project)
    assert report["state"] == "stopped" and report["commands_executed"] == []


def test_setup_refuses_same_namespaces_before_mounting(tmp_path, monkeypatch):
    from event_coordination import isolated_runtime
    ns = {name: os.readlink(f"/proc/self/ns/{name}") for name in runner.NAMESPACES}
    monkeypatch.setattr(isolated_runtime.ctypes, "CDLL", lambda *a, **k: pytest.fail("mount setup reached"))
    with pytest.raises(ValueError, match="NAMESPACE_REQUIRED"):
        isolated_runtime.setup(str(tmp_path), str(tmp_path), str(RUNTIME), "automation-tests", json.dumps(ns), "3")


def test_setup_requires_private_ipc_even_if_other_ids_differ(tmp_path, monkeypatch):
    from event_coordination import isolated_runtime
    ns = {name: "synthetic-other-parent" for name in runner.NAMESPACES}
    ns["ipc"] = os.readlink("/proc/self/ns/ipc")
    monkeypatch.setattr(isolated_runtime.ctypes, "CDLL", lambda *a, **k: pytest.fail("mount reached without private IPC"))
    with pytest.raises(ValueError, match="NAMESPACE_REQUIRED"):
        isolated_runtime.setup(str(tmp_path), str(tmp_path), str(RUNTIME), "automation-tests", json.dumps(ns), "3")


def test_failed_namespace_launch_never_falls_back(tmp_path, monkeypatch):
    calls = []
    def denied(argv, **kwargs):
        calls.append(argv)
        raise PermissionError("synthetic unavailable isolation")
    monkeypatch.setattr(subprocess, "Popen", denied)
    outcome = runner._run_task("automation-tests", tmp_path, RUNTIME, tmp_path / "out")
    assert outcome.reason == "LAUNCH_FAILED" and not outcome.launched
    assert outcome.launch is None and outcome.exit_code is None
    assert len(calls) == 1 and calls[0][0] == "/usr/bin/unshare"


def test_cli_explains_disabled_mode(capsys, project):
    assert runner.main(["--project-root", str(project)]) == 1
    r = json.loads(capsys.readouterr().out)
    assert r["checks"][-1]["code"] == runner.AUTH_UNAVAILABLE


@pytest.fixture
def capability(tmp_path):
    """Explicit real namespace prerequisite. Never substitute an unrestricted run."""
    if not RUNTIME.exists() or not Path("/usr/bin/unshare").exists():
        pytest.skip("Required Linux runtime unavailable")
    p = subprocess.run(["/usr/bin/unshare", "--user", "--map-root-user", "--net", "--mount", "--pid", "--ipc", "--fork", "/usr/bin/true"],
                       capture_output=True, timeout=5)
    if p.returncode:
        pytest.skip("Mandatory namespaces unavailable; no fallback")


def synthetic_task(project, text, tmp_path, timeout=10):
    (project / "tests/test_automation.py").write_text(text)
    copy = tmp_path / "isolated-copy"; copy.mkdir()
    runner._copy_project(project, copy)
    before = runner._snapshot(copy)
    result = runner._run_task("automation-tests", copy, RUNTIME, tmp_path / "launch", timeout=timeout)
    assert runner._snapshot(copy) == before
    return result


def test_real_isolation_runtime_and_hidden_files(project, tmp_path, capability):
    marker = tmp_path / "host-secret"; marker.write_bytes(b"synthetic secret")
    text = '''import errno,os,resource
from pathlib import Path
import pytest
def test_boundary():
 import httpx,icalendar,jinja2,jsonschema,tzdata
 from event_coordination import automation
 assert automation.RUN_ID=="988f5ccf-4aeb-44d7-984d-777b1a2412e1"
 for p in ["/home/maxg/.ssh","/home/maxg/.aws","/home/maxg/.codex","/home/maxg/event-coordination/.git","/home/maxg/event-coordination/.entire",MARKER]:
  assert not Path(p).exists()
 for p in ["README.md","src/event_coordination/automation.py",".venv/pyvenv.cfg","/usr/bin/python3.12","/new-file"]:
  with pytest.raises(OSError):
   fd=os.open(p,os.O_WRONLY|os.O_CREAT);os.close(fd)
 Path("/scratch/allowed").write_text("synthetic")
 Path("/tmp/allowed").write_text("synthetic")
 status=Path("/proc/self/status").read_text()
 assert "CapEff:\\t0000000000000000" in status
 assert "NoNewPrivs:\\t1" in status
 assert resource.getrlimit(resource.RLIMIT_NPROC)==(64,64)
'''.replace("MARKER", repr(str(marker)))
    result = synthetic_task(project, text, tmp_path)
    assert result.status == "passed", result.reason
    assert result.counts == {"passed": 1}
    assert marker.read_bytes() == b"synthetic secret"


def test_real_network_denial(project, tmp_path, capability):
    try:
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0)); listener.listen(4)
    except PermissionError:
        if "listener" in locals(): listener.close()
        pytest.skip("Outer sandbox denies loopback control; approved-environment probe required")
    port = listener.getsockname()[1]
    try:
        control = socket.create_connection(("127.0.0.1", port), timeout=1); control.close()
        text = '''import socket,pytest
def test_network():
 s=socket.socket();s.settimeout(.5)
 try:
  with pytest.raises(OSError):s.connect(("127.0.0.1",PORT))
 finally:s.close()
'''.replace("PORT", str(port))
        assert synthetic_task(project, text, tmp_path).status == "passed"
    finally:
        listener.close()


def test_real_timeout_no_fallback(project, tmp_path, capability, monkeypatch):
    text = '''import os,subprocess,sys,time
def test_wait():
 child=subprocess.Popen([sys.executable,'-c','import os,time;os.setsid();time.sleep(60)'])
 os.write(1,b'SYNTHETIC_TIMEOUT_STARTED\\n')
 time.sleep(60)
'''
    original = subprocess.Popen
    seen, escaped_sessions, stop = set(), set(), threading.Event()
    threads = []
    def observe(*args, **kwargs):
        process = original(*args, **kwargs)
        seen.add(process.pid)
        def monitor():
            while not stop.is_set():
                for pid in list(seen):
                    try:
                        seen.update(int(s) for s in Path(f"/proc/{pid}/task/{pid}/children").read_text().split())
                        if pid != process.pid and os.getsid(pid) == pid:
                            escaped_sessions.add(pid)
                    except OSError:
                        pass
                stop.wait(.02)
        thread = threading.Thread(target=monitor, daemon=True); thread.start(); threads.append(thread)
        return process
    monkeypatch.setattr(subprocess, "Popen", observe)
    try:
        result = synthetic_task(project, text, tmp_path, timeout=3)
    finally:
        stop.set()
        for thread in threads: thread.join(timeout=1)
    assert result.status == "failed" and result.reason == "TIMEOUT"
    assert result.exit_code != 0
    assert "SYNTHETIC_TIMEOUT_STARTED" in (tmp_path / "launch/stdout").read_text()
    assert len(seen) >= 3
    assert escaped_sessions, "Descendant did not demonstrably enter a separate session"
    deadline = time.monotonic() + 2
    while True:
        running = []
        for pid in seen:
            try:
                if Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z": running.append(pid)
            except OSError:
                pass
        if not running or time.monotonic() >= deadline: break
        time.sleep(.02)
    assert not running


def test_real_test_failure_is_failure(project, tmp_path, capability):
    result = synthetic_task(project, 'def test_fail():\n assert False\n', tmp_path)
    assert result.status == "failed" and result.exit_code == 1 and result.counts.get("failed") == 1


def xml_result(passed=1, skipped=0, failed=0, errors=0, **overrides):
    from xml.etree import ElementTree as ET
    root = ET.Element("testsuites")
    attributes = {"tests": str(passed+skipped+failed+errors), "failures": str(failed), "errors": str(errors), "skipped": str(skipped)}
    attributes.update(overrides)
    suite = ET.SubElement(root, "testsuite", attributes)
    for status, count in [(None, passed), ("skipped", skipped), ("failure", failed), ("error", errors)]:
        for index in range(count):
            case = ET.SubElement(suite, "testcase", name=f"test_{status}_{index}", classname="synthetic")
            if status: ET.SubElement(case, status)
    return ET.tostring(root)


@pytest.mark.parametrize("summary,xml", [
    ("1 failed, 1 passed in 0.1s", xml_result(passed=1, failed=1)),
    ("1 error, 1 passed in 0.1s", xml_result(passed=1, errors=1)),
    ("2 passed in 0.1s", xml_result(passed=1)),
    ("1 passed in 0.1s", xml_result(passed=2)),
    ("1 passed in 0.1s", xml_result(passed=1, tests="99")),
    ("1 passed in 0.1s", b""),
    ("", xml_result()),
    ("1 passed in 0.1s\n1 passed in 0.2s", xml_result()),
    ("1 skipped in 0.1s", xml_result(passed=0, skipped=1)),
    ("1 passed, 1 xpassed in 0.1s", xml_result(passed=2)),
    ("1 passed in 0.1s", b"<!DOCTYPE forbidden><testsuites/>"),
    ("1 passed in 0.1s", b"not xml"),
    ("1 passed, 1 passed in 0.1s", xml_result(passed=2)),
])
def test_pytest_results_reject_missing_inconsistent_and_failure(summary, xml):
    _, reason = runner._pytest_results(summary, xml)
    assert reason != "PASSED"


@pytest.mark.parametrize("summary,xml", [
    ("1 passed in 0.01s", xml_result()),
    ("2 passed, 1 skipped in 1.2s", xml_result(passed=2, skipped=1)),
])
def test_pytest_result_consistency_positive(summary, xml):
    counts, reason = runner._pytest_results(summary, xml)
    assert reason == "PASSED" and counts["passed"] > 0


@pytest.mark.parametrize("kind", ["failed", "error", "missing-xml", "inconsistent"])
def test_real_zero_exit_does_not_hide_bad_results(project, tmp_path, capability, kind):
    tests = 'def test_pass():\n assert True\n'
    hook = 'def pytest_sessionfinish(session,exitstatus):\n session.exitstatus=0\n'
    if kind == "failed": tests += 'def test_fail():\n assert False\n'
    elif kind == "error": tests += 'def test_error(missing_fixture):\n pass\n'
    elif kind == "missing-xml":
        # Truncate the dedicated result descriptor after pytest writes its artifact.
        hook = '''import os,pytest
@pytest.hookimpl(hookwrapper=True)
def pytest_sessionfinish(session,exitstatus):
 yield
 os.ftruncate(3,0)
 session.exitstatus=0
'''
    else:
        # Two real cases, but falsify only the terminal statistics.
        tests += 'def test_pass2():\n assert True\n'
        hook += '''def pytest_terminal_summary(terminalreporter):
 terminalreporter.stats['passed']=terminalreporter.stats['passed'][:1]
'''
    (project / "tests/conftest.py").write_text(hook)
    result = synthetic_task(project, tests, tmp_path)
    assert result.exit_code == 0 and result.status == "failed"
    assert result.reason != "PASSED"


@pytest.mark.parametrize("kind", ["replace", "symlink", "truncate"])
def test_log_late_mutation_is_rejected(project, kind):
    before = runner._snapshot(project)
    log = project / runner.LOG
    old = log.read_bytes()
    with log.open("ab") as stream: stream.write(b"legitimate append")
    after = runner._snapshot(project)
    if kind == "replace":
        replacement = log.with_name("replacement"); replacement.write_bytes(old+b"replacement")
        os.replace(replacement, log)
    elif kind == "symlink":
        other = project / "synthetic-secret"; other.write_bytes(old+b"secret")
        log.unlink(); log.symlink_to(other)
    else: log.write_bytes(old[:2])
    with pytest.raises((OSError, runner.policy.PolicyError)):
        runner._compare(project, before, after)


@pytest.mark.parametrize("mutation", ["append", "replace", "parent-replace", "truncate"])
def test_log_unstable_observation_fails(project, monkeypatch, mutation):
    original = os.read; changed = False
    log = project / runner.LOG
    def racy_read(fd, size):
        nonlocal changed
        data = original(fd, size)
        if not changed:
            changed = True
            if mutation == "append":
                with log.open("ab") as stream: stream.write(b"late append")
            elif mutation == "replace":
                other = log.with_name("replacement"); other.write_bytes(data)
                os.replace(other, log)
            elif mutation == "parent-replace":
                log.parent.rename(log.parent.with_name("old-logs"))
                log.parent.mkdir(); log.write_bytes(data)
            else: log.write_bytes(b"")
        return data
    monkeypatch.setattr(os, "read", racy_read)
    with pytest.raises(runner.policy.PolicyError): runner._observe_log(project)


@pytest.mark.parametrize("call", [3, 4])
def test_late_post_preflight_scope_change_stops(project, monkeypatch, call):
    plan = runner.example_plan(); original = runner._preflight; calls = 0
    def late(candidate, root):
        nonlocal calls
        original(candidate, root); calls += 1
        if calls == call:
            candidate["tasks"][0] = {"id": "stage6-tests", "argv": list(runner.TASKS["stage6-tests"])}
    monkeypatch.setattr(runner, "_preflight", late)
    monkeypatch.setattr(runner, "_run_task", lambda *a, **k: runner._Outcome("automation-tests", "passed", 0, "PASSED", "hash", (), {"passed": 1}))
    runtime = project / "synthetic-runtime"; runtime.mkdir()
    report = runner._fixture_batch(plan, project, runtime)
    assert report["state"] == "stopped"


def test_pinned_proposal_is_immutable_and_independent(project):
    from dataclasses import FrozenInstanceError
    plan = runner.example_plan(); pinned = runner._Proposal.pin(plan, project)
    original = pinned.encoded
    decoded = pinned.decode(); decoded["inputs"].clear(); decoded["tasks"].clear()
    assert pinned.encoded == original and pinned.decode() == plan
    with pytest.raises(FrozenInstanceError): pinned.encoded = b"forged"
    plan["tasks"].clear()
    with pytest.raises(runner.policy.PolicyError): pinned.check_live(plan)


def test_host_sysv_ipc_is_hidden(project, tmp_path, capability):
    libc = ctypes.CDLL(None, use_errno=True)
    libc.shmat.restype = ctypes.c_void_p
    shmid = libc.shmget(0,4096,0o1000|0o600)
    msgid = libc.msgget(0,0o1000|0o600)
    semid = libc.semget(0,1,0o1000|0o600)
    ptr = libc.shmat(shmid,None,0) if shmid >= 0 else ctypes.c_void_p(-1).value
    payload = b"SYNTHETIC-HOST-IPC"
    class Message(ctypes.Structure):
        _fields_ = [("kind",ctypes.c_long),("data",ctypes.c_char*32)]
    message=Message(1,payload)
    try:
        assert min(shmid,msgid,semid) >= 0
        assert ptr != ctypes.c_void_p(-1).value
        ctypes.memmove(ptr,payload,len(payload))
        assert libc.msgsnd(msgid,ctypes.byref(message),len(payload),0)==0
        assert libc.semctl(semid,0,16,7)==0  # SETVAL
        text = '''import ctypes,errno,os
from pathlib import Path
def test_host_ipc_denied():
 assert os.readlink('/proc/self/ns/ipc')!=PARENT_IPC
 libc=ctypes.CDLL(None,use_errno=True);libc.shmat.restype=ctypes.c_void_p
 ptr=libc.shmat(SHMID,None,0)
 assert ptr==ctypes.c_void_p(-1).value
 assert ctypes.get_errno() in (errno.EINVAL,errno.EACCES,errno.EPERM,errno.EIDRM)
 class Message(ctypes.Structure):
  _fields_=[('kind',ctypes.c_long),('data',ctypes.c_char*32)]
 msg=Message()
 assert libc.msgrcv(MSGID,ctypes.byref(msg),32,0,0o4000)==-1
 assert ctypes.get_errno() in (errno.EINVAL,errno.EACCES,errno.EPERM,errno.EIDRM)
 msg.kind=1
 assert libc.msgsnd(MSGID,ctypes.byref(msg),1,0o4000)==-1
 assert ctypes.get_errno() in (errno.EINVAL,errno.EACCES,errno.EPERM,errno.EIDRM)
 assert libc.semctl(SEMID,0,12)==-1
 assert ctypes.get_errno() in (errno.EINVAL,errno.EACCES,errno.EPERM,errno.EIDRM)
 assert libc.semctl(SEMID,0,16,99)==-1
 assert ctypes.get_errno() in (errno.EINVAL,errno.EACCES,errno.EPERM,errno.EIDRM)
'''.replace('PARENT_IPC',repr(os.readlink('/proc/self/ns/ipc'))).replace('SHMID',str(shmid)).replace('MSGID',str(msgid)).replace('SEMID',str(semid))
        result = synthetic_task(project, text, tmp_path)
        assert result.status == "passed", result.reason
        assert ctypes.string_at(ptr,len(payload))==payload
        received=Message()
        assert libc.msgrcv(msgid,ctypes.byref(received),32,0,0o4000)==len(payload)
        assert bytes(received.data)==payload
        assert libc.semctl(semid,0,12)==7  # GETVAL
    finally:
        if ptr != ctypes.c_void_p(-1).value: libc.shmdt(ctypes.c_void_p(ptr))
        if shmid >= 0: libc.shmctl(shmid,0,None)
        if msgid >= 0: libc.msgctl(msgid,0,None)
        if semid >= 0: libc.semctl(semid,0,0)


@pytest.mark.parametrize("body", [
    '<testcase classname="synthetic" name="pass"/><error message="synthetic error"/>',
    '<testcase classname="synthetic" name="pass"/><testsuite tests="1" failures="1"><testcase classname="synthetic" name="fail"><failure/></testcase></testsuite>',
    '<testcase classname="synthetic" name="pass"/><testsuite tests="0"/>',
    '<testcase classname="synthetic" name="pass"><unknown/></testcase>',
    '<testcase classname="synthetic" name="pass"><system-out><error/></system-out></testcase>',
    '<testcase classname="synthetic" name="pass"><properties><unknown/></properties></testcase>',
    '<testcase classname="synthetic" name="pass"><system-out/><system-out/></testcase>',
    '<testcase classname="synthetic" name="pass"/>unexpected text',
])
def test_reject_unexpected_junit_structure_and_hidden_failures(body):
    xml = ('<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0">'
           + body + '</testsuite></testsuites>').encode()
    assert runner._pytest_results('1 passed in 0.01s', xml)[1] != "PASSED"


@pytest.mark.parametrize("xml", [
    b'<testsuites><testsuite tests="1" failures="0" errors="0"><testcase classname="c" name="n"/></testsuite></testsuites>',
    b'<testsuites tests="2"><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase classname="c" name="n"/></testsuite></testsuites>',
    b'<testsuites><testsuite tests="+1" failures="0" errors="0" skipped="0"><testcase classname="c" name="n"/></testsuite></testsuites>',
    b'<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase classname="c" name="n"><skipped/><skipped/></testcase></testsuite></testsuites>',
])
def test_reject_incomplete_or_contradictory_junit(xml):
    assert runner._pytest_results('1 passed in 0.01s', xml)[1] != "PASSED"


def test_junit_supported_metadata():
    xml = b'<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"><properties><property name="a" value="b"/></properties><testcase classname="c" name="n"><system-out>synthetic output</system-out></testcase></testsuite></testsuites>'
    assert runner._pytest_results('1 passed in 0.01s', xml)[1] == "PASSED"


@pytest.mark.parametrize("failure,expected", [
    ("launch", "LAUNCH_FAILED"),
    ("execution", "EXECUTION_FAILED"),
    ("cleanup", "CLEANUP_FAILED"),
    ("cleanup_wait", "CLEANUP_FAILED"),
    ("result", "RESULT_READING_FAILED"),
])
def test_launch_metadata_survives_later_failures(project, tmp_path, monkeypatch, failure, expected):
    from dataclasses import FrozenInstanceError
    plan = runner.example_plan()
    plan["tasks"].append({"id": "stage6-tests", "argv": list(runner.TASKS["stage6-tests"])})
    runtime = tmp_path / 'runtime'; runtime.mkdir()
    calls = []
    observations = []
    original_read = Path.read_bytes
    original_run = runner._run_task

    class Process:
        pid = 987654321
        returncode = 0
        waits = 0
        def wait(self, timeout=None):
            self.waits += 1
            if (failure == "execution" and self.waits == 1) or (failure == "cleanup_wait" and self.waits == 2):
                raise OSError("synthetic wait failure")
            return self.returncode

    def launch(argv, **kwargs):
        calls.append(tuple(argv))
        if failure == "launch":
            raise PermissionError("synthetic launch failure")
        kwargs['stdout'].write(b'1 passed in 0.01s\n'); kwargs['stdout'].flush()
        # Popen would inherit this same dedicated regular result descriptor.
        os.write(kwargs['pass_fds'][0], xml_result())
        return Process()

    def kill(pid, sig):
        if failure == "cleanup":
            raise PermissionError("synthetic post-launch cleanup failure")

    def read(path):
        if failure == "result" and path.name == 'results.xml':
            raise OSError("synthetic result read failure")
        return original_read(path)

    def capture(*args, **kwargs):
        outcome = original_run(*args, **kwargs)
        observations.append(outcome)
        return outcome

    monkeypatch.setattr(subprocess, 'Popen', launch)
    monkeypatch.setattr(os, 'killpg', kill)
    monkeypatch.setattr(Path, 'read_bytes', read)
    monkeypatch.setattr(runner, '_run_task', capture)
    report = runner._fixture_batch(plan, project, runtime)
    entry = report['tasks'][0]
    assert report['state'] == 'stopped' and len(calls) == 1
    assert report['tasks'][1]['status'] == 'skipped'
    assert entry['reason'] == expected and expected in entry['failure_codes']
    assert entry['status'] == 'failed' and entry['launched'] is (failure != 'launch')
    assert entry['launch_argv'] == list(calls[0])
    if failure != 'launch':
        launch_record = observations[0].launch
        assert entry['pid'] == launch_record.pid == Process.pid
        assert entry['started_at'] == launch_record.started_at
        assert entry['argv'] == list(launch_record.argv) == list(runner.TASKS['automation-tests'])
        assert launch_record.task == 'automation-tests'
        with pytest.raises(FrozenInstanceError):
            launch_record.task = 'forged'
