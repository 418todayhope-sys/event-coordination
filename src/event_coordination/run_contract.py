"""Read-only contracts for future runs; no execution, authorization, or file writers.

Pins prove local byte integrity, never remote retrieval or business approval.
Scoped new-run bindings admit only saved snapshots registered by the coordinator.
"""

from dataclasses import dataclass
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from uuid import UUID, uuid4

from jsonschema import Draft202012Validator, FormatChecker

BUSINESS_CLOCK = "2026-08-26T12:00:00+08:00"
LEGACY_RUN_ID = "988f5ccf-4aeb-44d7-984d-777b1a2412e1"
STAGES = ("scope-and-approval-gates", "source-capture", "constraint-model",
          "planning-baseline", "option-generation", "feasibility-testing",
          "decision-and-approval", "draft-propagation", "publication-validation")
KINDS = frozenset({"source", "decision", "capture", "interview", "schema", "snapshot", "media"})
LEGACY_HASHES = (
    "6579a81d06ac405d3e612dbe7ad4d354b9373ff5840168af0981d961186fde7d",
    "abe8ff40d45da1e8ba8c45f35b715db99b17bd40fe66d5e5adc331334d00fe70",
    "0b346b83d170f871b4ad22d13c951baabb9a437ecd1beaf3c9e75bee14f3ea37",
    "321e45c0ce912ca95223f0ed72f627e19d539c40bf71c4f97a12bc691db25098",
    "e0454834f384615926edbf2cc8130ea4c0f0a3ae1e8c942a8010f9fad92dc65d",
    "57b5be2bde9d3c5a66316b2b1e0239a8c55e39de5ff54b859bf644fe74542fe1",
    "ffe4619118b95982c0a53c9d7b1b02e66360a99e4bb402b9e50a1090c0353ad8",
    "a96c01eb2fdcfbad709445918142a888c0b018ef1b6b6e6df9e748f36413d0a6",
)
LEGACY_SCHEMA_HASH = "sha256:787e6ac3e2008458b311c2ab2e287a3cafb68aaa82d49a489775864ba32221ee"


class ContractError(ValueError):
    """Controlled codes only: do not echo untrusted paths, JSON, or exceptions."""


def _require(condition, code):
    if not condition:
        raise ContractError(code)


def _uuid(value):
    try:
        _require(type(value) is str and str(UUID(value)) == value, "invalid_uuid")
    except (ValueError, TypeError, AttributeError):
        raise ContractError("invalid_uuid") from None
    return value


def _digest(value):
    _require(type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None,
             "invalid_hash")
    return value


def _identifier(value):
    _require(type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}", value) is not None,
             "invalid_identifier")
    return value


def relative_path(value):
    """Canonical POSIX repository-relative paths; no aliases or platform escapes."""
    _require(type(value) is str and value and "\\" not in value and "\x00" not in value
             and ":" not in value, "unsafe_path")
    parts = value.split("/")
    _require(all(p not in ("", ".", "..") for p in parts)
             and not PurePosixPath(value).is_absolute(), "unsafe_path")
    _require(not any(p in {".git", ".entire", ".aws", ".ssh", ".venv"} for p in parts),
             "protected_path")
    return value


def _identity(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns,
            st.st_ctime_ns, st.st_nlink)


class _Directory:
    """No-follow root-prefix and parent traversal, with named-identity rechecks."""

    def __init__(self, root, parts=()):
        self.fds = []
        self.edges = []
        try:
            root = Path(root)
            _require(root.is_absolute() and str(root) == os.path.normpath(str(root)), "unsafe_root")
            fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            self.fds.append(fd)
            for name in (*root.parts[1:], *parts):
                new = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                              dir_fd=fd)
                self.fds.append(new)
                self.edges.append((fd, name, new))
                fd = new
            self.fd = fd
            self.verify()
        except (OSError, ValueError):
            self.close()
            raise ContractError("unsafe_or_missing_directory") from None

    def verify(self):
        for parent, name, fd in self.edges:
            a = os.stat(name, dir_fd=parent, follow_symlinks=False)
            b = os.fstat(fd)
            _require(stat.S_ISDIR(a.st_mode) and (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino),
                     "directory_changed")

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds = []


def _read(root, path):
    parts = relative_path(path).split("/")
    directory = _Directory(root, parts[:-1])
    fd = None
    try:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                     dir_fd=directory.fd)
        before = os.fstat(fd)
        _require(stat.S_ISREG(before.st_mode), "not_regular_file")
        chunks = []
        while chunk := os.read(fd, 1024 * 1024):
            chunks.append(chunk)
        data = b"".join(chunks)
        named = os.stat(parts[-1], dir_fd=directory.fd, follow_symlinks=False)
        _require(_identity(before) == _identity(os.fstat(fd)) == _identity(named)
                 and len(data) == before.st_size, "input_changed")
        directory.verify()
        return data, _identity(before)
    except OSError:
        raise ContractError("input_unavailable") from None
    finally:
        if fd is not None:
            os.close(fd)
        directory.close()


@dataclass(frozen=True)
class InputSpec:
    id: str
    path: str
    kind: str
    expected_sha256: str | None = None
    source_id: str | None = None

    def __post_init__(self):
        _identifier(self.id)
        relative_path(self.path)
        _require(type(self.kind) is str and self.kind in KINDS, "invalid_input_kind")
        if self.expected_sha256 is not None:
            _digest(self.expected_sha256)
        if self.source_id is not None:
            _identifier(self.source_id)
            _require(self.kind in {"source", "capture", "media"}, "invalid_source_association")

    @property
    def source_identity(self):
        return self.source_id or (self.id if self.kind == "source" else None)


@dataclass(frozen=True)
class InputPin:
    spec: InputSpec
    sha256: str
    identity: tuple


def pin_inputs(root, specs):
    """Pin explicitly enumerated local files; not discovery or source verification."""
    _require(type(specs) is tuple and all(type(s) is InputSpec for s in specs), "invalid_manifest")
    _require(len({s.id for s in specs}) == len(specs)
             and len({s.path for s in specs}) == len(specs), "duplicate_input")
    pins = []
    for spec in specs:
        data, identity = _read(root, spec.path)
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        _require(spec.expected_sha256 is None or digest == spec.expected_sha256, "input_hash_mismatch")
        pins.append(InputPin(spec, digest, identity))
    result = tuple(sorted(pins, key=lambda p: p.spec.id))
    verify_inputs(root, result)
    return result


def _pins(pins):
    _require(type(pins) is tuple and all(type(p) is InputPin and type(p.spec) is InputSpec for p in pins),
             "invalid_manifest")
    _require(len({p.spec.id for p in pins}) == len(pins)
             and len({p.spec.path for p in pins}) == len(pins), "duplicate_input")
    for pin in pins:
        _digest(pin.sha256)
        _require(type(pin.identity) is tuple and len(pin.identity) == 7
                 and all(type(v) is int for v in pin.identity), "invalid_identity")
    return {p.spec.id: p for p in pins}


def verify_inputs(root, pins):
    """Rehash independently, rejecting replacement even when bytes are unchanged."""
    for pin in _pins(pins).values():
        data, identity = _read(root, pin.spec.path)
        _require(identity == pin.identity and "sha256:" + hashlib.sha256(data).hexdigest() == pin.sha256,
                 "input_changed")


def compare_manifests(previous, current):
    """Deterministic added/removed/changed IDs; stat identity is not a source version."""
    old, new = _pins(previous), _pins(current)
    result = []
    for key in sorted(old.keys() | new.keys()):
        a, b = old.get(key), new.get(key)
        _require(a is None or b is None or (a.spec.kind, a.spec.source_identity)
                 == (b.spec.kind, b.spec.source_identity), "input_identity_ambiguous")
        if a is None or b is None or (a.sha256, a.spec.path) != (b.sha256, b.spec.path):
            result.append({"id": key, "kind": (b or a).spec.kind,
                           "source_id": (b or a).spec.source_identity,
                           "change": "added" if a is None else "removed" if b is None else "changed",
                           "previous_sha256": a.sha256 if a else None,
                           "current_sha256": b.sha256 if b else None})
    return result


def validate_run_metadata(data, *, previous=None, current=None):
    """Additional Stage 01 state metadata; never grants authority or changes schema."""
    fields = {"run_contract_version", "run_id", "business_clock", "supersedes_run_id",
              "changed_source_ids", "changed_decision_ids", "change_reasons"}
    _require(type(data) is dict and set(data) == fields, "invalid_run_metadata")
    _require(type(data["run_contract_version"]) is int and data["run_contract_version"] == 1,
             "invalid_contract_version")
    _uuid(data["run_id"])
    _require(data["business_clock"] == BUSINESS_CLOCK, "invalid_business_clock")
    supersedes = data["supersedes_run_id"]
    if supersedes is not None:
        _uuid(supersedes)
        _require(supersedes != data["run_id"], "self_supersession")
    changed = {}
    for kind in ("source", "decision"):
        ids = data[f"changed_{kind}_ids"]
        _require(type(ids) is list and all(type(i) is str for i in ids), "invalid_changed_ids")
        for item in ids:
            _identifier(item)
        _require(ids == sorted(set(ids)), "invalid_changed_ids")
        changed[kind] = ids
    reasons = data["change_reasons"]
    _require(type(reasons) is list, "invalid_change_reasons")
    keys = []
    for reason in reasons:
        _require(type(reason) is dict and set(reason) == {"kind", "id", "reason", "evidence_ids"},
                 "invalid_change_reason")
        _require(type(reason["kind"]) is str and reason["kind"] in {"source", "decision", "recovery"},
                 "invalid_change_reason")
        _identifier(reason["id"])
        _require(type(reason["reason"]) is str and bool(reason["reason"].strip()), "missing_reason")
        refs = reason["evidence_ids"]
        _require(type(refs) is list and refs and all(type(r) is str for r in refs), "missing_reason_evidence")
        for ref in refs:
            _identifier(ref)
        _require(len(refs) == len(set(refs)), "duplicate_reason_evidence")
        keys.append((reason["kind"], reason["id"]))
    _require(keys == sorted(set(keys)), "duplicate_or_unsorted_reasons")
    required = {(kind, item) for kind, ids in changed.items() for item in ids}
    _require({k for k in keys if k[0] != "recovery"} == required, "change_reason_mismatch")
    _require(supersedes is not None or not (required or reasons), "changes_without_supersession")
    _require(supersedes is None or bool(reasons), "missing_supersession_reason")
    _require((previous is None) == (current is None), "manifest_pair_required")
    if previous is not None:
        differences = compare_manifests(previous, current)
        for kind in changed:
            actual = (sorted({r["source_id"] for r in differences if r["source_id"] is not None})
                      if kind == "source" else [r["id"] for r in differences if r["kind"] == "decision"])
            _require(changed[kind] == actual,
                     "unsupported_changed_ids")
    return None


def new_run_metadata(*, supersedes_run_id=None, changed_source_ids=(), changed_decision_ids=(),
                     change_reasons=()):
    _require(type(changed_source_ids) is tuple and type(changed_decision_ids) is tuple
             and type(change_reasons) is tuple, "invalid_metadata_arguments")
    data = {"run_contract_version": 1, "run_id": str(uuid4()), "business_clock": BUSINESS_CLOCK,
            "supersedes_run_id": supersedes_run_id, "changed_source_ids": list(changed_source_ids),
            "changed_decision_ids": list(changed_decision_ids), "change_reasons": list(change_reasons)}
    validate_run_metadata(data)
    return data


def new_snapshot_id():
    return str(uuid4())


def _json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ContractError("invalid_json")))
    except (ValueError, UnicodeError, RecursionError):
        raise ContractError("invalid_json") from None


@dataclass(frozen=True)
class SnapshotExpectation:
    run_id: str
    snapshot_id: str
    sequence: int
    pin: InputPin

    def __post_init__(self):
        _uuid(self.run_id)
        _uuid(self.snapshot_id)
        _require(type(self.sequence) is int and 1 <= self.sequence <= 9, "invalid_sequence")
        _pins((self.pin,))
        _require(self.pin.spec.kind == "snapshot", "invalid_snapshot_pin")


@dataclass(frozen=True)
class InspectedSnapshot:
    expectation: SnapshotExpectation
    data: bytes

    @property
    def reference(self):
        return {"snapshot_id": self.expectation.snapshot_id, "path": self.expectation.pin.spec.path,
                "sha256": self.expectation.pin.sha256}


def inspect_predecessor(root, expected, schema_pin, *, predecessor=None):
    """Inspect one stage; callers supply its verified parent for every stage > 1.

    This checks schema, exact identity, clock, and chain linkage. It does not
    replace stage-specific semantic validation or authenticate supplied pins.
    """
    _require(type(expected) is SnapshotExpectation, "invalid_expectation")
    _pins((schema_pin,))
    _require(schema_pin.spec.kind == "schema", "invalid_schema_pin")
    verify_inputs(root, (expected.pin, schema_pin))
    data, identity = _read(root, expected.pin.spec.path)
    _require(identity == expected.pin.identity
             and "sha256:" + hashlib.sha256(data).hexdigest() == expected.pin.sha256, "input_changed")
    snapshot = _json(data)  # Hash and JSON inspection use these exact bytes.
    schema_bytes, schema_identity = _read(root, schema_pin.spec.path)
    _require(schema_identity == schema_pin.identity
             and "sha256:" + hashlib.sha256(schema_bytes).hexdigest() == schema_pin.sha256, "input_changed")
    try:
        schema = _json(schema_bytes)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(snapshot)
    except Exception as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError("snapshot_schema_invalid") from None
    _require(type(snapshot["sequence"]) is int and snapshot["sequence"] == expected.sequence
             and snapshot["stage"] == STAGES[expected.sequence - 1]
             and snapshot["run_id"] == expected.run_id
             and snapshot["snapshot_id"] == expected.snapshot_id, "snapshot_identity_mismatch")
    _require(snapshot["state"].get("business_clock") == BUSINESS_CLOCK, "invalid_business_clock")
    if expected.sequence == 1:
        _require(predecessor is None and snapshot["predecessor"] is None
                 and snapshot["consumed_record_ids"] == [], "invalid_stage1_lineage")
        if expected.run_id != LEGACY_RUN_ID or "run_metadata" in snapshot["state"]:
            metadata = snapshot["state"].get("run_metadata")
            validate_run_metadata(metadata)
            _require(metadata["run_id"] == expected.run_id, "run_metadata_identity_mismatch")
    else:
        _require(type(predecessor) is InspectedSnapshot, "verified_predecessor_required")
        parent = predecessor.expectation
        _require(parent.run_id == expected.run_id and parent.sequence == expected.sequence - 1
                 and parent.snapshot_id != expected.snapshot_id
                 and snapshot["predecessor"] == predecessor.reference, "broken_lineage")
        parent_data = _json(predecessor.data)
        _require("sha256:" + hashlib.sha256(predecessor.data).hexdigest() == parent.pin.sha256
                 and parent_data.get("run_id") == parent.run_id
                 and parent_data.get("snapshot_id") == parent.snapshot_id
                 and type(parent_data.get("sequence")) is int
                 and parent_data["sequence"] == parent.sequence
                 and parent_data.get("stage") == STAGES[parent.sequence - 1], "invalid_parent_inspection")
    final_pins = (expected.pin, schema_pin) + (() if predecessor is None else (predecessor.expectation.pin,))
    verify_inputs(root, final_pins)
    return InspectedSnapshot(expected, data)


def inspect_legacy_run(root):
    """Explicit existing-run compatibility, with historical byte pins and semantics."""
    specs = (InputSpec("schema", "snapshot.schema.json", "schema", LEGACY_SCHEMA_HASH),) + tuple(
        InputSpec(f"stage-{i}", f"deliverables/snapshots/{i:02}-{stage}.json", "snapshot", "sha256:" + digest)
        for i, (stage, digest) in enumerate(zip(STAGES, LEGACY_HASHES), 1))
    pins = pin_inputs(root, specs)
    by_id = {p.spec.id: p for p in pins}
    from event_coordination.validation import validate_snapshot
    previous = None
    results = []
    for i in range(1, 9):
        pin = by_id[f"stage-{i}"]
        data, _ = _read(root, pin.spec.path)
        expected = SnapshotExpectation(LEGACY_RUN_ID, _json(data)["snapshot_id"], i, pin)
        previous = inspect_predecessor(root, expected, by_id["schema"], predecessor=previous)
        validate_snapshot(_json(previous.data), Path(root))
        results.append(previous)
    verify_inputs(root, pins)
    return tuple(results)


def _archive_destination_absent(root, destination):
    """Validate existing prefixes without creating missing parents."""
    directory = _Directory(root)
    opened = [directory]
    try:
        parts = destination.split("/")
        for i, part in enumerate(parts):
            try:
                item = os.stat(part, dir_fd=directory.fd, follow_symlinks=False)
            except FileNotFoundError:
                break
            if i == len(parts) - 1:
                raise ContractError("archive_collision")
            _require(stat.S_ISDIR(item.st_mode), "unsafe_archive_parent")
            directory = _Directory(root, parts[:i + 1])
            opened.append(directory)
        for handle in opened:
            handle.verify()
    except OSError:
        raise ContractError("archive_inspection_failed") from None
    finally:
        for handle in reversed(opened):
            handle.close()


def plan_archive(root, run_id, pins):
    """Return a non-binding copy plan only; never create directories or files."""
    _uuid(run_id)
    _require(bool(pins), "empty_archive")
    verify_inputs(root, pins)
    destination = f"deliverables/history/{run_id}"
    _archive_destination_absent(root, destination)
    files = []
    try:
        for pin in pins:
            path = pin.spec.path
            _require(path == "snapshot.schema.json" or path.startswith(("deliverables/", "evidence/", "interviews/")),
                     "archive_scope_violation")
            _require(not path.startswith("deliverables/history/"), "recursive_archive")
            files.append({"id": pin.spec.id, "source": path, "destination": f"{destination}/{path}",
                          "sha256": pin.sha256})
        verify_inputs(root, pins)
        _archive_destination_absent(root, destination)
        return {"run_id": run_id, "destination": destination, "status": "planned-not-created",
                "files": sorted(files, key=lambda f: f["source"])}
    except OSError:
        raise ContractError("archive_inspection_failed") from None


def describe_failure(*, run_id, attempt_id, stage, last_validated_stage, code,
                     occurred_at, affected_paths=(), expected_sha256=None, observed_sha256=None):
    """Structured diagnostics only; controlled code/path fields, never raw exceptions."""
    _uuid(run_id)
    _uuid(attempt_id)
    _require(type(stage) is int and 1 <= stage <= 9 and type(last_validated_stage) is int
             and 0 <= last_validated_stage < stage, "invalid_failure_stage")
    _require(type(code) is str and code in {"input_missing", "input_changed", "output_missing",
             "output_corrupt", "output_collision", "validation_failed", "interrupted", "io_failed"},
             "invalid_failure_code")
    _require(type(occurred_at) is datetime and occurred_at.tzinfo is not None
             and occurred_at.utcoffset() is not None, "invalid_execution_time")
    _require(type(affected_paths) is tuple, "invalid_failure_paths")
    paths = sorted({relative_path(p) for p in affected_paths})
    for value in (expected_sha256, observed_sha256):
        if value is not None:
            _digest(value)
    return {"failure_contract_version": 1, "run_id": run_id, "attempt_id": attempt_id,
            "stage": stage, "last_validated_stage": last_validated_stage, "code": code,
            "occurred_at": occurred_at.astimezone(timezone.utc).isoformat(),
            "business_clock": BUSINESS_CLOCK, "affected_paths": paths,
            "expected_sha256": expected_sha256, "observed_sha256": observed_sha256,
            "status": "failed", "recovery_action": "preserve-outputs-and-request-review"}


# Task-local, root-bound state, not patched module constants or a configuration
# file that can authorize actions. Outside this scope all historical pins apply.
_ACTIVE_RUN = ContextVar("event_coordination_active_run", default=None)


def current_run(root):
    session = _ACTIVE_RUN.get()
    if session is not None:
        _require(Path(root) == session.root, "run_workspace_mismatch")
    return session


def bound_run_id(root, historical_id):
    session = current_run(root)
    return session.run_id if session else historical_id


def bound_snapshot_id(root, path, historical_id):
    session = current_run(root)
    return session.expected(path).snapshot_id if session else historical_id


def read_predecessor(root, path, historical_hash):
    """Read/hash/parse the same bytes against an independently registered pin."""
    session = current_run(root)
    expected = session.expected(path) if session else None
    data, identity = _read(root, path)
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    _require(digest == (expected.pin.sha256 if expected else historical_hash), "predecessor hash mismatch")
    if expected:
        value = _json(data)
        _require(identity == expected.pin.identity and value["run_id"] == session.run_id
                 and value["snapshot_id"] == expected.snapshot_id
                 and value["sequence"] == expected.sequence, "registered_predecessor_changed")
    return data


class RunSession:
    """Read-only binding/registration of actual outputs; never writes snapshots."""

    def __init__(self, root, metadata, schema_pin):
        validate_run_metadata(metadata)
        self.root = Path(root)
        self.metadata = deepcopy(metadata)
        self.run_id = metadata["run_id"]
        self.schema_pin = schema_pin
        self._snapshots = {}
        self._last = None
        _require(schema_pin.spec.kind == "schema" and schema_pin.sha256 == LEGACY_SCHEMA_HASH,
                 "unchanged_schema_required")
        verify_inputs(self.root, (schema_pin,))

    def expected(self, path):
        _require(path in self._snapshots, "unregistered_predecessor")
        return self._snapshots[path].expectation

    def verify(self):
        validate_run_metadata(self.metadata)
        _require(self.metadata["run_id"] == self.run_id, "run_metadata_changed")
        verify_inputs(self.root, (self.schema_pin, *(s.expectation.pin for s in self._snapshots.values())))

    def register(self, path, reported_hash):
        """Only after the real writer returns: reread bytes and validate semantics."""
        _require(current_run(self.root) is self, "inactive_run")
        sequence = len(self._snapshots) + 1
        _require(sequence <= 9 and path == f"deliverables/snapshots/{sequence:02}-{STAGES[sequence-1]}.json",
                 "out_of_order_snapshot")
        self.verify()
        pin = pin_inputs(self.root, (InputSpec(f"run-stage-{sequence}", path, "snapshot", reported_hash),))[0]
        data, _ = _read(self.root, path)
        snapshot = _json(data)
        _require(snapshot["snapshot_id"] not in {s.expectation.snapshot_id for s in self._snapshots.values()},
                 "reused_snapshot_id")
        inspected = inspect_predecessor(self.root, SnapshotExpectation(
            self.run_id, snapshot["snapshot_id"], sequence, pin), self.schema_pin, predecessor=self._last)
        from event_coordination.validation import validate_snapshot
        validate_snapshot(_json(inspected.data), self.root)
        verify_inputs(self.root, (pin,))
        self._snapshots[path] = inspected
        self._last = inspected
        self.verify()
        return {"path": path, "snapshot_id": snapshot["snapshot_id"], "sha256": pin.sha256,
                "sequence": sequence, "status": snapshot["status"]}


@contextmanager
def activate_run(session):
    _require(type(session) is RunSession and _ACTIVE_RUN.get() is None, "invalid_run_scope")
    token = _ACTIVE_RUN.set(session)
    try:
        session.verify()
        yield session
        session.verify()
    finally:
        _ACTIVE_RUN.reset(token)
