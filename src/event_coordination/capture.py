"""Explicit, bounded capture primitives. No network activity at import time.

Phase A does not interpret observations, authenticate to providers, follow redirects,
or generate a manifest/snapshot. Return records for later orchestration.
"""

from datetime import datetime, timezone
from pathlib import Path
import re
from uuid import uuid4

import httpx

from event_coordination.source_catalog import CATALOG
from event_coordination.sources import hash_bytes

KINDS = {"real-publication", "stakeholder-statement", "fictional-exercise-record"}
METHODS = {"provider-export", "preserved-export", "manually-completed-copy"}


def preserve_original(root: Path, content: bytes) -> tuple[str, str]:
    """Store bytes exclusively by digest; verify rather than overwrite duplicates."""
    digest = hash_bytes(content)
    relative = Path("evidence/originals/captures") / (digest.removeprefix("sha256:") + ".bin")
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError("Refusing a symlink capture target")
    try:
        with target.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if target.read_bytes() != content:
            raise ValueError("Existing capture bytes do not match their digest path")
    if hash_bytes(target.read_bytes()) != digest:
        raise ValueError("Saved capture hash verification failed")
    return relative.as_posix(), digest


def _record(source_id: str, method: str, kind: str) -> dict:
    source = CATALOG[source_id]
    return {
        "id": f"capture-{source_id}-{uuid4()}",
        "summary": f"Capture attempt for {source_id}", "evidence_ids": [],
        "source_identity": source_id, "source_role": source.role,
        "locator": source.url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "retrieval_status": "unavailable", "content_type": "unknown",
        "version_metadata": {
            "method": method, "publication_kind": kind,
            "disclosure": {"path": source.disclosure_path, "line": source.disclosure_line},
            "response_status": None,
        },
        "content_hash": None, "local_reference": None, "observations": [],
    }


def _problem(record: dict, status: str, reason: str) -> dict:
    record["retrieval_status"] = status
    record["version_metadata"]["reason"] = reason
    return record


def _valid(content: bytes, content_type: str) -> bool:
    if not content:
        return False
    if re.search(rb"(?:bearer\s+[a-z0-9._~-]+|(?:access_token|refresh_token|id_token|api_key)\s*[\"']?\s*[:=])", content.lower()):
        return False
    if content_type == "application/pdf":
        return content.startswith(b"%PDF-") and b"%%EOF" in content[-1024:]
    if content_type not in {"text/plain", "text/html", "text/csv", "text/markdown"}:
        return False
    try:
        text = content.decode("utf-8").lower()
    except UnicodeDecodeError:
        return False
    if content_type == "text/html":
        if not any(tag in text for tag in ("<html", "<!doctype html")):
            return False
        if any(marker in text for marker in ("<title>sign in", "<title>login", "<title>access denied", 'type="password"', "accounts.google.com/servicelogin")):
            return False
    # Do not retain recognizable credential-bearing response bodies. No headers,
    # cookies, request objects, or raw exception messages are persisted.
    return True


def retrieve_source(root: Path, source_id: str, *, transport: httpx.BaseTransport | None = None) -> dict:
    """Attempt only the exact catalog URL. Redirects require separate human review.

    Transport injection supports offline tests. No cookies/auth may be supplied;
    authenticated captures should use explicit local provider exports for now.
    """
    source = CATALOG[source_id]
    record = _record(source_id, "http-get", source.publication_kind)
    try:
        with httpx.Client(transport=transport, trust_env=False, follow_redirects=False,
                          timeout=20, headers={"Accept-Encoding": "identity"}) as client:
            response = client.get(source.url)
    except httpx.RequestError as exc:
        return _problem(record, "unavailable", type(exc).__name__)
    metadata = record["version_metadata"]
    metadata["response_status"] = response.status_code
    if response.status_code in (401, 403):
        return _problem(record, "unavailable", "unauthorized")
    if 300 <= response.status_code < 400:
        # Location can contain tokens; intentionally do not store it or follow it.
        return _problem(record, "unverified", "redirect-requires-review")
    if response.status_code != 200:
        return _problem(record, "unavailable", "http-error")
    content_type = response.headers.get("content-type", "unknown").split(";", 1)[0].lower().strip()
    record["content_type"] = content_type if content_type in {
        "text/html", "text/plain", "text/csv", "text/markdown", "application/pdf"
    } else "unknown"
    if content_type != source.expected_type or not _valid(response.content, content_type):
        return _problem(record, "invalid", "unexpected-or-invalid-content")
    if response.headers.get("content-encoding", "identity").lower() != "identity":
        return _problem(record, "invalid", "encoded-response-requires-explicit-byte-handling")
    path, digest = preserve_original(root, response.content)
    record.update(content_hash=digest, local_reference=path, retrieval_status="retrieved")
    metadata["byte_representation"] = "HTTP body without content encoding; transfer framing removed"
    metadata["verification_limit"] = "Retrieved bytes only; source completeness, observations and historical applicability require review"
    return record


def import_local(root: Path, source_id: str, path: Path, *, method: str,
                 publication_kind: str, content_type: str) -> dict:
    """Import supplied bytes; never claim a new online retrieval or equivalence.

    Callers must explicitly classify method and content. Timestamp is this local
    import attempt; the original provider retrieval time remains unknown.
    """
    if method not in METHODS or publication_kind not in KINDS:
        raise ValueError("Explicit supported method and publication kind required")
    record = _record(source_id, method, publication_kind)
    metadata = record["version_metadata"]
    metadata.update(timestamp_basis="local-import-attempt", original_retrieved_at=None,
                    online_equivalence="unverified")
    try:
        content = path.read_bytes()
    except OSError as exc:
        return _problem(record, "unavailable", type(exc).__name__)
    record["content_type"] = content_type
    if not _valid(content, content_type):
        return _problem(record, "invalid", "unexpected-or-invalid-content")
    local, digest = preserve_original(root, content)
    record.update(content_hash=digest, local_reference=local, retrieval_status="unverified")
    metadata["import_status"] = "preserved"
    return record
