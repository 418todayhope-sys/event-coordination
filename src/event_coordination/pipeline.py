"""Bounded local Stage 01–09 execution from registered evidence, never retrieval.

Creates only a new separate workspace. No archival, replacement, recovery, Git,
or external actions. Failure leaves the workspace intact for review.
"""

import json
import os
from pathlib import Path
import stat

from event_coordination import draft_contract
from event_coordination.run_contract import (
    InputSpec, RunSession, activate_run, new_run_metadata, pin_inputs,
    relative_path, _read,
)
from event_coordination.source_inventory import load_inventory
from event_coordination.source_catalog import CATALOG
from event_coordination.sources import hash_bytes
from event_coordination.stages import scope, capture, constraints, baseline, options, feasibility, decisions, drafts, publication

STAGE_MODULES = (scope, capture, constraints, baseline, options, feasibility, decisions, drafts)


def _inputs(root):
    """Complete no-follow observations, including additions and directory changes."""
    result = {}

    def visit(relative):
        relative_path(relative)
        with decisions._Directories(root, relative.split("/")) as directories:
            fd = directories.fds[-1]
            before = decisions._identity(os.fstat(fd))
            names = sorted(os.listdir(fd))
            for name in names:
                child = relative + "/" + name
                entry = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(entry.st_mode):
                    visit(child)
                elif stat.S_ISREG(entry.st_mode):
                    relative_path(child)
                    result[child] = decisions._protected_file(root, child)
                else:
                    raise ValueError("Source inputs contain a link or special file")
            if before != decisions._identity(os.fstat(fd)) or names != sorted(os.listdir(fd)):
                raise ValueError("Source input directory changed")
            result[relative] = ("directory", before)
            directories.verify()

    for path in ("evidence", "interviews"):
        visit(path)
    result["snapshot.schema.json"] = decisions._protected_file(root, "snapshot.schema.json")
    if result["snapshot.schema.json"][2] != drafts.SCHEMA_HASH:
        raise ValueError("The unchanged snapshot schema is required")
    return result


def _verify(root, expected):
    if _inputs(root) != expected:
        raise ValueError("Pinned source inputs changed")


def _mkdir(root, relative):
    parts = relative_path(relative).split("/")
    for index, name in enumerate(parts):
        with decisions._Directories(root, parts[:index]) as parent:
            try:
                os.mkdir(name, mode=0o700, dir_fd=parent.fds[-1])
            except FileExistsError:
                item = os.stat(name, dir_fd=parent.fds[-1], follow_symlinks=False)
                if not stat.S_ISDIR(item.st_mode):
                    raise ValueError("Unsafe workspace parent") from None
            parent.verify()


def _copy_bytes(root, relative, content):
    parts = relative_path(relative).split("/")
    if len(parts) > 1:
        _mkdir(root, "/".join(parts[:-1]))
    with decisions._Directories(root, parts[:-1]) as parent:
        drafts._write_exclusive(root, relative, content, parent)


def run_stages(source_root, workspace, through_stage=9, *, metadata=None, progress=None):
    """Run actual existing writers in order, with no historical output reuse."""
    if type(through_stage) is not int or through_stage not in (8, 9):
        raise ValueError("Only complete Stage 01–08 or 01–09 batches are supported")
    source_root, workspace = Path(source_root).absolute(), Path(workspace).absolute()
    if (source_root.resolve(strict=True) != source_root
            or workspace.is_relative_to(source_root) or source_root.is_relative_to(workspace)):
        raise ValueError("A separate canonical workspace is required")
    source_inputs = _inputs(source_root)
    registered, _ = load_inventory(source_root, include_all=True)
    if {c["source_identity"] for c in registered} != set(CATALOG):
        raise ValueError("Current run requires a recorded attempt for every catalog source")
    _verify(source_root, source_inputs)
    # The parent must exist. Exclusive mkdir refuses even empty destinations.
    with decisions._Directories(workspace.parent, []) as parent:
        os.mkdir(workspace.name, mode=0o700, dir_fd=parent.fds[-1])
        parent.verify()
        with decisions._Directories(workspace, []) as destination:
            for path, identity in sorted(source_inputs.items()):
                if identity[0] != "file":
                    continue
                content, _ = _read(source_root, path)
                if hash_bytes(content) != identity[2] or decisions._protected_file(source_root, path) != identity:
                    raise ValueError("Source changed while copying registered inputs")
                _copy_bytes(workspace, path, content)
            _verify(source_root, source_inputs)
            copied = _inputs(workspace)
            _mkdir(workspace, "deliverables/snapshots/evidence")
            captures, _ = load_inventory(workspace)
            floor = {(c["local_reference"], c["content_hash"]) for c in captures
                     if c["source_identity"] == "official-floor-plan" and c["local_reference"]}
            if len(floor) != 1:
                raise ValueError("The floor-plan representation must be unambiguous")
            floor_path, floor_hash = next(iter(floor))
            floor_bytes, _ = _read(workspace, floor_path)
            if hash_bytes(floor_bytes) != floor_hash:
                raise ValueError("Floor-plan hash mismatch")
            media_path = "deliverables/snapshots/evidence/" + Path(floor_path).name
            _copy_bytes(workspace, media_path, floor_bytes)
            media = decisions._protected_file(workspace, media_path)
            schema_pin = pin_inputs(workspace, (
                InputSpec("run-schema", "snapshot.schema.json", "schema", drafts.SCHEMA_HASH),))[0]
            session = RunSession(workspace, metadata if metadata is not None else new_run_metadata(), schema_pin)

            def verify():
                parent.verify(); destination.verify()
                _verify(source_root, source_inputs)
                _verify(workspace, copied)
                if decisions._protected_file(workspace, media_path) != media:
                    raise ValueError("Floor-plan media copy changed")
                session.verify()

            snapshots = []
            with activate_run(session):
                for module in (*STAGE_MODULES, publication)[:through_stage]:
                    verify()
                    if progress is not None:
                        progress(len(snapshots)+1, session.run_id)
                    path, digest = module.write_snapshot(workspace)
                    relative = path.relative_to(workspace).as_posix()
                    snapshots.append(session.register(relative, digest))
                    verify()
                final_bytes, _ = _read(workspace, drafts.OUTPUT)
                final = json.loads(final_bytes)
                if final["state"]["draft_contract_version"] != draft_contract.VERSION:
                    raise ValueError("The assignment draft contract is required")
                artifacts = []
                for record in final["state"]["artifact_drafts"]:
                    content, _ = _read(workspace, record["path"])
                    if hash_bytes(content) != record["sha256"] or record["saved_file_verified"] is not True:
                        raise ValueError("Saved artifact verification failed")
                    artifacts.append({"path": record["path"], "sha256": hash_bytes(content)})
                verify()
            return {"scope": f"stages-01-through-{through_stage:02}", "workspace": str(workspace),
                    "run_id": session.run_id, "status": final["status"], "validation_status": "valid",
                    "source_mode": "registered-local-evidence; no new remote retrieval",
                    "business_clock": scope.BUSINESS_CLOCK, "draft_contract_version": draft_contract.VERSION,
                    "snapshots": snapshots, "artifacts": artifacts,
                    "unresolved_count": len(final["unresolved"]),
                    "pending_approval_count": sum(g["status"] == "pending" for g in final["state"]["approval_requirements"]),
                    "retained_screening_count": len(final["state"]["retained_early_screening"]),
                    "external_actions_authorized": False,
                    "publication_status": "blocked" if through_stage == 9 else "not-assessed",
                    "limitations": ["Material-change recovery is not implemented.",
                                    "Local source copies remain unverified against live sources."]}
