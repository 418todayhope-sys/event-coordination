"""Read selected preserved evidence without changing or retrieving sources."""

from hashlib import sha256
from pathlib import Path


def hash_bytes(content: bytes) -> str:
    return "sha256:" + sha256(content).hexdigest()


def read_evidence(root: Path, record_id: str, path: str, line: int,
                  expected: str, provenance: str) -> dict:
    content = (root / path).read_bytes()
    lines = content.decode("utf-8").splitlines()
    if line > len(lines) or expected not in lines[line - 1]:
        raise ValueError(f"Evidence no longer matches {path}:{line}")
    return {
        "id": record_id, "summary": expected, "evidence_ids": [],
        "path": path, "sha256": hash_bytes(content),
        "line_start": line, "line_end": line, "excerpt": lines[line - 1],
        "provenance": provenance,
    }
