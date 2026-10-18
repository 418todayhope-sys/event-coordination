"""Offline Stage 2 assembly from preserved captures; no live retrieval or planning."""

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from event_coordination.source_catalog import CATALOG
from event_coordination.source_inventory import load_inventory
from event_coordination.sources import hash_bytes
from event_coordination.run_contract import read_predecessor
from event_coordination.stages.scope import OUTPUT as PREDECESSOR_PATH

PREDECESSOR_HASH = "sha256:6579a81d06ac405d3e612dbe7ad4d354b9373ff5840168af0981d961186fde7d"
OUTPUT = "deliverables/snapshots/02-source-capture.json"


def _inputs(root: Path) -> dict:
    from event_coordination.validation import validate_snapshot

    predecessor_bytes = read_predecessor(root, PREDECESSOR_PATH, PREDECESSOR_HASH)
    predecessor_hash = hash_bytes(predecessor_bytes)
    predecessor = json.loads(predecessor_bytes)
    validate_snapshot(predecessor, root)
    captures, manifest = load_inventory(root)
    # Read-only use of each scope field and inherited uncertainty is recorded.
    consumed = [r["id"] for r in predecessor["state"]["scope_records"] + predecessor["unresolved"]]
    unresolved = []

    def gap(record_id, category, summary, evidence_ids, **details):
        unresolved.append({"id": record_id, "summary": summary, "category": category,
                           "evidence_ids": evidence_ids, "owner": None, **details})

    for record in predecessor["unresolved"]:
        gap("stage2-inherited-" + record["id"], "inherited",
            record["summary"], [record["id"]], origin_record_id=record["id"])
    for capture in captures:
        cid = capture["id"]
        metadata = capture["version_metadata"]
        if capture["retrieval_status"] != "retrieved":
            gap(f"stage2-{cid}-status", "capture-status",
                f"Capture status remains {capture['retrieval_status']}; no upgrade in verification is inferred.",
                [cid], original_status=capture["retrieval_status"])
        if capture["local_reference"] and metadata.get("method") != "http-get":
            gap(f"stage2-{cid}-historical-time", "historical-retrieval-time",
                "Local registration is not a verified original online retrieval time.", [cid])
        # Carry reviewed limitations verbatim, including conditions and privacy.
        for key in ("reason", "completeness", "online_equivalence", "limitations",
                    "conditions", "possible_interpretations_not_resolutions", "privacy",
                    "verification_limit", "parser_limitations"):
            items = metadata.get(key, [])
            if not isinstance(items, list):
                items = [items]
            for index, item in enumerate(items):
                if not item:
                    continue
                summary = item if isinstance(item, str) else item["summary"]
                gap(f"stage2-{cid}-{key}-{index}", key, summary, [cid],
                    metadata_field=key, original_detail=item)

    groups = []
    for identity in sorted({r["source_identity"] for r in captures}):
        group = [r for r in captures if r["source_identity"] == identity]
        groups.append({"id": "source-group-" + identity,
                       "summary": f"Disclosed source {identity}; attempts/representations are not additional sources.",
                       "evidence_ids": [r["id"] for r in group], "source_identity": identity,
                       "capture_ids": [r["id"] for r in group]})
    observation_ids = [o["id"] for c in captures for o in c["observations"]]
    produced = [r["id"] for r in captures + groups + unresolved] + observation_ids
    if len(produced) != len(set(produced)) or set(produced).intersection(predecessor["produced_record_ids"]):
        raise ValueError("Duplicate or reused upstream record ID")
    available = set(produced + consumed)
    for record in captures + groups + unresolved:
        if not set(record["evidence_ids"]).issubset(available):
            raise ValueError("Capture or uncertainty references an unconsumed/unknown record")
    files = {c["local_reference"] for c in captures if c["local_reference"]}
    state = {
        "sources": captures, "source_inventory": groups, "capture_manifest": manifest,
        "inventory_counts": {"source_identities": len(groups), "capture_attempts": len(captures),
                             "evidence_files": len(files), "observations": len(observation_ids)},
        "scope_basis": predecessor["state"]["scope_records"],
        "business_clock": predecessor["state"]["business_clock"],
        "business_timezone": predecessor["state"]["business_timezone"],
        "output_status": "draft", "audience": "internal-evidence-review",
        "privacy_boundary": "Contains aggregate accessibility/dietary evidence. Do not copy this inventory wholesale into public communications; no public artifact is generated here.",
    }
    return {"run_id": predecessor["run_id"],
            "predecessor": {"snapshot_id": predecessor["snapshot_id"], "path": PREDECESSOR_PATH,
                            "sha256": predecessor_hash},
            "consumed_record_ids": consumed, "produced_record_ids": produced, "state": state,
            "unresolved": unresolved, "decisions": [],
            "status": "partial" if unresolved else "complete"}


def build_snapshot(root: Path) -> dict:
    """Assemble in memory only. Validate all captures and the approved predecessor."""
    return {"schema_version": "event-coordination-stage-snapshot/2",
            "snapshot_id": str(uuid4()), "stage": "source-capture", "sequence": 2,
            "created_at": datetime.now(timezone.utc).isoformat(), **_inputs(root)}


def validate_stage2(snapshot: dict, root: Path) -> None:
    """Reconstruct expected lineage and evidence from actual immutable inputs."""
    expected = _inputs(root)
    for key, value in expected.items():
        if snapshot.get(key) != value:
            raise ValueError(f"Stage 2 {key} differs from verified capture inputs")
    if snapshot["snapshot_id"] == snapshot["predecessor"]["snapshot_id"]:
        raise ValueError("Stage 2 must have a distinct snapshot ID")
    schema = json.loads((root / "snapshot.schema.json").read_bytes())
    from jsonschema import Draft202012Validator, FormatChecker
    validator = Draft202012Validator({"$ref": "#/$defs/record", "$defs": schema["$defs"]},
                                    format_checker=FormatChecker())
    for record in snapshot["state"]["source_inventory"] + snapshot["unresolved"]:
        validator.validate(record)


def write_snapshot(root: Path) -> tuple[Path, str]:
    """Explicit writer, tested only in temporary directories until authorized."""
    from event_coordination.validation import validate_snapshot

    target = root / OUTPUT
    if target.exists():
        raise FileExistsError(target)
    snapshot = build_snapshot(root)
    validate_snapshot(snapshot, root)
    content = (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(content)
    saved = target.read_bytes()
    if saved != content:
        raise ValueError("Saved Stage 2 bytes differ from validated snapshot")
    validate_snapshot(json.loads(saved), root)
    return target, hash_bytes(saved)
