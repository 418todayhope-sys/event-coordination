"""Read and verify preserved capture attempts without retrieving or rewriting them."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from event_coordination.source_catalog import CATALOG
from event_coordination.sources import hash_bytes


def project_file(root: Path, relative: str, directory: str) -> Path:
    """Require evidence paths to remain inside their designated project directory."""
    base = (root / directory).resolve()
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(base):
        raise ValueError(f"Path outside {directory}")
    return path


def load_inventory(root: Path) -> tuple[list[dict], list[dict]]:
    schema = json.loads((root / "snapshot.schema.json").read_bytes())
    validator = Draft202012Validator(
        {"$ref": "#/$defs/sourceRecord", "$defs": schema["$defs"]},
        format_checker=FormatChecker(),
    )
    captures, manifest, identifiers = [], [], set()
    for path in sorted((root / "evidence/captures").glob("*.json")):
        relative = path.relative_to(root).as_posix()
        content = project_file(root, relative, "evidence/captures").read_bytes()
        record = json.loads(content)
        validator.validate(record)
        identity = record.get("source_identity")
        if identity not in CATALOG:
            raise ValueError("Unknown capture source identity")
        source = CATALOG[identity]
        if (record["locator"], record["source_role"]) != (source.url, source.role):
            raise ValueError("Capture source URL or role differs from disclosed catalog")
        metadata = record["version_metadata"]
        if not isinstance(metadata, dict) or not metadata.get("method"):
            raise ValueError("Capture method/provenance metadata missing")
        if metadata.get("disclosure") != {"path": source.disclosure_path, "line": source.disclosure_line}:
            raise ValueError("Capture disclosure provenance mismatch")
        if metadata.get("publication_kind") != source.publication_kind:
            raise ValueError("Capture publication classification mismatch")
        # Verify the catalog against its actual interview disclosure as well.
        lines = (root / source.disclosure_path).read_text().splitlines()
        if source.url not in lines[source.disclosure_line - 1]:
            raise ValueError("Disclosed URL no longer matches interview")
        local, digest = record["local_reference"], record["content_hash"]
        if (local is None) != (digest is None):
            raise ValueError("Capture file and hash must be paired")
        if local is not None:
            evidence = project_file(root, local, "evidence/originals").read_bytes()
            if hash_bytes(evidence) != digest:
                raise ValueError("Captured evidence hash mismatch")
            if metadata.get("size_bytes", len(evidence)) != len(evidence):
                raise ValueError("Captured evidence size mismatch")
        elif record["observations"] or record["retrieval_status"] == "retrieved":
            raise ValueError("Capture without bytes cannot supply observations or successful retrieval")
        new_ids = [record["id"]] + [o["id"] for o in record["observations"]]
        if len(new_ids) != len(set(new_ids)) or identifiers.intersection(new_ids):
            raise ValueError("Duplicate capture or observation ID")
        identifiers.update(new_ids)
        captures.append(record)
        manifest.append({"id": record["id"], "path": relative, "sha256": hash_bytes(content)})
    if {r["source_identity"] for r in captures} != set(CATALOG):
        raise ValueError("Capture inventory must represent all seven disclosed sources")
    return captures, manifest
