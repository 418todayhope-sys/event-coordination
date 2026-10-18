"""Synthetic capture tests. HTTP uses MockTransport; sockets are prohibited."""

from datetime import datetime
import json
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator, FormatChecker
import pytest

from event_coordination.capture import import_local, preserve_original, retrieve_source
from event_coordination.source_catalog import CATALOG, SOURCES
from event_coordination.sources import hash_bytes


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Live network access forbidden in capture tests")
    monkeypatch.setattr("socket.socket.connect", deny)


def check_record(record):
    schema = json.loads((Path(__file__).resolve().parents[1] / "snapshot.schema.json").read_text())
    Draft202012Validator({"$ref": "#/$defs/sourceRecord", "$defs": schema["$defs"]},
                        format_checker=FormatChecker()).validate(record)
    assert datetime.fromisoformat(record["retrieved_at"]).utcoffset() is not None
    assert record["observations"] == []


def mock_response(status=200, content=b"<!doctype html><html>synthetic test</html>", headers=None):
    def handler(request):
        assert str(request.url) == CATALOG["event-brief"].url
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        return httpx.Response(status, content=content,
                              headers=headers or {"Content-Type": "text/html"})
    return httpx.MockTransport(handler)


def test_catalog_matches_preserved_disclosures():
    assert len(SOURCES) == len(CATALOG) == 8
    root = Path(__file__).resolve().parents[1]
    for source in SOURCES:
        lines = (root / source.disclosure_path).read_text().splitlines()
        assert source.url in lines[source.disclosure_line - 1]


def test_original_storage_deduplicates_and_detects_corruption(tmp_path):
    content = b"synthetic original\r\n"
    relative, digest = preserve_original(tmp_path, content)
    path = tmp_path / relative
    stamp = path.stat().st_mtime_ns
    assert digest == hash_bytes(content)
    assert preserve_original(tmp_path, content) == (relative, digest)
    assert path.stat().st_mtime_ns == stamp
    path.write_bytes(b"tampered fixture")
    with pytest.raises(ValueError, match="Existing capture bytes"):
        preserve_original(tmp_path, content)
    assert path.read_bytes() == b"tampered fixture"


def test_success_preserves_exact_bytes(tmp_path):
    body = b"<!doctype html><html>synthetic\r\nrecord</html>"
    record = retrieve_source(tmp_path, "event-brief", transport=mock_response(content=body))
    check_record(record)
    assert record["retrieval_status"] == "retrieved"
    assert record["content_hash"] == hash_bytes(body)
    assert (tmp_path / record["local_reference"]).read_bytes() == body
    assert record["version_metadata"]["response_status"] == 200
    assert record["version_metadata"]["publication_kind"] == "fictional-exercise-record"


@pytest.mark.parametrize("status,expected,reason", [
    (401, "unavailable", "unauthorized"), (403, "unavailable", "unauthorized"),
    (404, "unavailable", "http-error"), (500, "unavailable", "http-error"),
    (302, "unverified", "redirect-requires-review"),
])
def test_unsuccessful_requests_never_preserve_or_invent_content(tmp_path, status, expected, reason):
    record = retrieve_source(tmp_path, "event-brief", transport=mock_response(
        status, headers={"Location": "https://example.invalid/?access_token=SECRET"}))
    check_record(record)
    assert record["retrieval_status"] == expected
    assert record["version_metadata"]["reason"] == reason
    assert record["content_hash"] is None and record["local_reference"] is None
    assert not list(tmp_path.rglob("*.bin"))
    assert "SECRET" not in json.dumps(record)


def test_transport_error_does_not_leak_exception_details(tmp_path):
    def handler(request):
        raise httpx.ConnectError("credential=SECRET", request=request)
    record = retrieve_source(tmp_path, "event-brief", transport=httpx.MockTransport(handler))
    check_record(record)
    assert record["retrieval_status"] == "unavailable"
    assert "SECRET" not in json.dumps(record)


def test_timeout_is_unavailable(tmp_path):
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)
    record = retrieve_source(tmp_path, "event-brief", transport=httpx.MockTransport(handler))
    check_record(record)
    assert record["retrieval_status"] == "unavailable"
    assert record["version_metadata"]["reason"] == "ReadTimeout"


def test_repeated_capture_has_new_attempt_identity_but_reuses_bytes(tmp_path):
    first = retrieve_source(tmp_path, "event-brief", transport=mock_response())
    second = retrieve_source(tmp_path, "event-brief", transport=mock_response())
    assert first["id"] != second["id"]
    assert first["local_reference"] == second["local_reference"]
    assert len(list(tmp_path.rglob("*.bin"))) == 1


@pytest.mark.parametrize("body", [b"", b"not html", b'<html><input type="password"></html>',
                                  b'<html><title>Sign in</title></html>',
                                  b'<html>access_token=SECRET</html>'])
def test_invalid_or_credential_content_not_saved(tmp_path, body):
    record = retrieve_source(tmp_path, "event-brief", transport=mock_response(content=body))
    check_record(record)
    assert record["retrieval_status"] == "invalid"
    assert record["local_reference"] is None
    assert not list(tmp_path.rglob("*.bin"))


def test_content_type_mismatch_not_saved(tmp_path):
    record = retrieve_source(tmp_path, "event-brief", transport=mock_response(
        headers={"Content-Type": "application/pdf"}))
    assert record["retrieval_status"] == "invalid"


def test_pdf_capture_and_html_error_page(tmp_path):
    for body, expected in [(b"%PDF-1.7\nsynthetic fixture\n%%EOF", "retrieved"),
                           (b"<html>not a PDF</html>", "invalid")]:
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, content=body, headers={"Content-Type": "application/pdf"}))
        record = retrieve_source(tmp_path, "official-floor-plan", transport=transport)
        check_record(record)
        assert record["retrieval_status"] == expected


@pytest.mark.parametrize("kind", ["real-publication", "stakeholder-statement", "fictional-exercise-record"])
def test_local_import_retains_classification_and_uncertainty(tmp_path, kind):
    original = tmp_path / "synthetic.txt"
    content = b"Synthetic manually completed fixture\r\n"
    original.write_bytes(content)
    record = import_local(tmp_path, "event-brief", original,
                          method="manually-completed-copy", publication_kind=kind,
                          content_type="text/plain")
    check_record(record)
    assert original.read_bytes() == content
    assert record["retrieval_status"] == "unverified"
    metadata = record["version_metadata"]
    assert metadata["method"] == "manually-completed-copy"
    assert metadata["publication_kind"] == kind
    assert metadata["original_retrieved_at"] is None
    assert metadata["response_status"] is None
    assert (tmp_path / record["local_reference"]).read_bytes() == content


def test_missing_local_import_honestly_unavailable(tmp_path):
    record = import_local(tmp_path, "event-brief", tmp_path / "missing", method="preserved-export",
                          publication_kind="fictional-exercise-record", content_type="text/plain")
    check_record(record)
    assert record["retrieval_status"] == "unavailable"
    assert record["content_hash"] is None


def test_explicit_local_provenance_required(tmp_path):
    with pytest.raises(ValueError):
        import_local(tmp_path, "event-brief", tmp_path / "missing", method="guessed",
                     publication_kind="fictional-exercise-record", content_type="text/plain")
