"""Assignment assertions, independent of renderer constants; temporary copies only."""

from copy import deepcopy
import csv
from decimal import Decimal
import io
import json
from pathlib import Path
import re
import shutil

from icalendar import Calendar
import pytest

from event_coordination import draft_contract as contract
from event_coordination.constraint_sources import workbook_rows
from event_coordination.sources import hash_bytes
from event_coordination.stages import drafts
from event_coordination.validation import validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_external_actions(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Draft format tests cannot perform external actions")
    monkeypatch.setattr("subprocess.Popen", deny)
    monkeypatch.setattr("socket.socket.connect", deny)


@pytest.fixture(scope="module")
def basis(tmp_path_factory):
    root = tmp_path_factory.mktemp("assignment-drafts")
    for directory in ("evidence", "interviews"):
        shutil.copytree(ROOT / directory, root / directory)
    shutil.copyfile(ROOT / "snapshot.schema.json", root / "snapshot.schema.json")
    (root / "deliverables/snapshots").mkdir(parents=True)
    shutil.copytree(ROOT / "deliverables/snapshots/evidence", root / "deliverables/snapshots/evidence")
    for path in (*drafts.ANCESTOR_PATHS, drafts.PREDECESSOR_PATH):
        shutil.copyfile(ROOT / path, root / path)
    return root


@pytest.fixture(scope="module")
def context(basis):
    return drafts._context(basis)


@pytest.fixture(scope="module")
def bundle(context):
    payloads = drafts.render_artifacts(context, "2026-10-18T15:00:00+00:00")
    drafts._validate_content(context, payloads, "2026-10-18T15:00:00+00:00")
    return payloads


def csv_rows(bundle):
    return list(csv.DictReader(io.StringIO(bundle[drafts.ARTIFACT_PATHS[0]].decode())))


def change_csv(bundle, mutate):
    result = dict(bundle)
    reader = csv.DictReader(io.StringIO(result[drafts.ARTIFACT_PATHS[0]].decode()))
    rows = list(reader)
    fields = list(reader.fieldnames)
    mutate(fields, rows)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    writer.writeheader(); writer.writerows(rows)
    result[drafts.ARTIFACT_PATHS[0]] = output.getvalue().encode()
    return result


def test_assignment_columns_values_and_source_membership(basis, bundle):
    # Published README c724104:106. Deliberately do not import the implementation's list.
    required = {"option_id", "quote_ids", "planning_people", "cost_twd", "currency", "feasibility",
                "availability_status", "evidence_ids", "tradeoffs", "unresolved", "approval_status"}
    rows = csv_rows(bundle)
    assert required <= rows[0].keys()
    capture_snapshot = json.loads((basis / "deliverables/snapshots/02-source-capture.json").read_bytes())
    vendor = next(c for c in capture_snapshot["state"]["sources"] if c["source_identity"] == "vendor-register")
    cells = workbook_rows(basis, vendor, "Vendor Quotes")
    # Independent worksheet column locators: A identity, E amount, J original notes.
    offers = {row["raw"][f"A{n}"]: row["raw"] for n, row in enumerate(cells[1:], 2)}
    candidates = {r["option_id"]: r for r in rows if r["row_type"] == "candidate"}
    expected = [("option-oct17-green-table", "Q-003", "494000", "26000", "260.0"),
                ("option-oct17-city-pantry", "Q-004", "512000", "8000", "300.0")]
    for option, catering, total, headroom, capacity in expected:
        row = candidates[option]
        members = ["Q-001", catering, "Q-005", "Q-006", "Q-009", "Q-010"]
        assert row["quote_ids"].split(";") == members
        amount = sum(Decimal(next(v for k, v in offers[q].items() if k.startswith("E"))) for q in members)
        assert amount + Decimal(25000) + Decimal(40000) == Decimal(total)
        assert row["cost_twd"] == row["planning_total_twd"] == total
        assert row["headroom_twd"] == headroom and row["capacity"] == capacity
        assert row["currency"] == "TWD" and row["planning_people"] == "245"
        assert row["feasibility"] == "conditional" and row["availability_status"] == "unverified"
        assert row["approval_status"] == "pending"
        assert row["evidence_ids"] in {"decision-review-oct17-green-table", "decision-review-oct17-city-pantry"}
        assert json.loads(row["tradeoffs"]) and json.loads(row["unresolved"])
    for row in rows:
        for name, value in row.items():
            if name.endswith("_twd") and value:
                assert re.fullmatch(r"-?(0|[1-9][0-9]*)", value), (name, value)
        if row["row_type"] == "quote":
            original = offers[row["quote_ids"]]
            assert row["conditions"] == next(v for k, v in original.items() if k.startswith("J"))
            assert row["planning_people"] == "" and row["feasibility"] == "unverified"
        if row["cost_twd"] == "":
            assert "No complete package total" in row["unresolved"]


@pytest.mark.parametrize("column", ["option_id", "planning_people", "cost_twd", "currency", "feasibility",
                                     "availability_status", "tradeoffs", "unresolved", "approval_status"])
def test_missing_required_column_rejected(context, bundle, column):
    modified = change_csv(bundle, lambda fields, rows: fields.remove(column))
    with pytest.raises(ValueError): contract.validate_artifacts(context, modified, drafts.ARTIFACT_PATHS)


@pytest.mark.parametrize("field,value", [
    ("option_id", "invented"), ("cost_twd", "493999"), ("cost_twd", "494000.0"),
    ("currency", "USD"), ("planning_people", "210"), ("feasibility", "feasible"),
    ("availability_status", "confirmed"), ("approval_status", "approved"),
    ("tradeoffs", '["No capacity trade-off"]'), ("unresolved", '[]'),
])
def test_option_claim_tampering_rejected(context, bundle, field, value):
    def mutate(fields, rows):
        next(r for r in rows if r["row_type"] == "candidate")[field] = value
    modified = change_csv(bundle, mutate)
    with pytest.raises(ValueError): contract.validate_artifacts(context, modified, drafts.ARTIFACT_PATHS)


def test_whole_twd_plan_and_policy_without_altering_source_context(context, bundle):
    before = deepcopy(context)
    for path in (drafts.ARTIFACT_PATHS[1], drafts.ARTIFACT_PATHS[3]):
        text = bundle[path].decode()
        assert "TWD 494000" in text and "TWD 512000" in text
        assert not re.search(r"\bTWD\s+-?\d+\.\d+", text)
        assert "| option-oct17-green-table | 429000 | 494000 | 260.0 | 26000 | conditional |" in text
    plan = bundle[drafts.ARTIFACT_PATHS[1]].decode()
    assert "| venue | 155000 | 155000 | 155000 | 180000 | 0 | Operations |" in plan
    assert "planned allocations: TWD 510000." in plan
    drafts.render_artifacts(context, "2026-10-18T15:00:00+00:00")
    assert context == before


@pytest.mark.parametrize("value,expected", [("155000.0", "155000"), ("0.00", "0"),
                                            ("-3000.0", "-3000"), (Decimal("494000"), "494000")])
def test_whole_amounts_are_exact(value, expected):
    assert contract.whole_twd(value) == expected


@pytest.mark.parametrize("value", [True, False, 1.0, "unknown", "1.1", "NaN", "Infinity"])
def test_no_rounding_or_unknown_to_zero(value):
    with pytest.raises(ValueError): contract.whole_twd(value)


def test_calendar_publish_is_metadata_only_and_schedule_is_unchanged(context, bundle):
    calendar = Calendar.from_ical(bundle[drafts.ARTIFACT_PATHS[2]])
    assert str(calendar["VERSION"]) == "2.0" and str(calendar["METHOD"]) == "PUBLISH"
    historic = Calendar.from_ical((ROOT / "deliverables/event-calendar.ics").read_bytes())
    assert historic.get("METHOD") is None
    current_events, old_events = calendar.walk("VEVENT"), historic.walk("VEVENT")
    assert len(current_events) == len(old_events) == 35
    for current, old in zip(current_events, old_events, strict=True):
        for key in ("UID", "DTSTART", "DTEND", "STATUS", "X-EVIDENCE-ID", "X-RESOURCE-LANE"):
            assert current.get(key) == old.get(key)
        assert str(current["STATUS"]) == "TENTATIVE"
        assert current.get("ATTENDEE") is current.get("ORGANIZER") is None
    assert sum(str(e["SUMMARY"]) == "DRAFT: demo" for e in current_events) == 12
    assert sum(str(e["SUMMARY"]) == "DRAFT: changeover" for e in current_events) == 12


@pytest.mark.parametrize("method", [None, "REQUEST", "CANCEL"])
def test_missing_or_delivery_calendar_method_is_rejected(context, bundle, method):
    changed = dict(bundle)
    calendar = Calendar.from_ical(changed[drafts.ARTIFACT_PATHS[2]])
    del calendar["METHOD"]
    if method is not None: calendar.add("method", method)
    changed[drafts.ARTIFACT_PATHS[2]] = calendar.to_ical()
    with pytest.raises(ValueError): contract.validate_artifacts(context, changed, drafts.ARTIFACT_PATHS)


def test_each_message_has_explicit_review_contract_and_honest_owner(bundle):
    text = bundle[drafts.ARTIFACT_PATHS[3]].decode()
    titles = ["Operations review", "Category budget owners", "Vendors", "Staff", "Attendees"]
    for title in titles:
        section = text.split(f"## {title} — UNSENT DRAFT\n", 1)[1].split("\n## ", 1)[0]
        for label in ("Audience", "Purpose", "Conditions", "Approval owner"):
            assert re.search(rf"^- {label}: .+", section, re.M)
        if title in ("Vendors", "Staff", "Attendees"):
            assert "Approval owner: Unresolved:" in section and "[gate-external-actions]" in section
        else:
            assert "role only; approval pending" in section
    assert "@" not in text and "not an order, acceptance, booking or payment authorization" in text


@pytest.mark.parametrize("field", ["Audience", "Purpose", "Conditions", "Approval owner", "UNSENT DRAFT"])
def test_missing_or_forged_message_fields_are_rejected(context, bundle, field):
    changed = dict(bundle)
    target = field if field == "UNSENT DRAFT" else f"- {field}:"
    changed[drafts.ARTIFACT_PATHS[3]] = changed[drafts.ARTIFACT_PATHS[3]].replace(target.encode(), b"unsupported", 1)
    with pytest.raises(ValueError): contract.validate_artifacts(context, changed, drafts.ARTIFACT_PATHS)


@pytest.fixture(scope="module")
def historical(basis, tmp_path_factory):
    root = tmp_path_factory.mktemp("audited-historical-drafts")
    shutil.copytree(basis, root, dirs_exist_ok=True)
    for relative in (*drafts.ARTIFACT_PATHS, drafts.OUTPUT):
        shutil.copyfile(ROOT / relative, root / relative)
    return root


def test_exact_historical_snapshot_and_outputs_still_validate(historical):
    expected = [
        "0345bb6da5afc0bda7a10e23fe8ecff072b136f75bedcdb932dd02f48d3820d2",
        "4522dd7ebceb0a1c206b1cca8b06ca5e926cd4ac07e5d2c93b6d51985fa2ecc6",
        "fcedef5eeb537658e109d76905b61d0b94ede31b3e646bac25c3ed024a2abb09",
        "d011bc19ba646ef4988585e695fbdb5c57438745dc268615df362aaba7df72cd",
        "a96c01eb2fdcfbad709445918142a888c0b018ef1b6b6e6df9e748f36413d0a6",
    ]
    before = {p: (historical / p).read_bytes() for p in (*drafts.ARTIFACT_PATHS, drafts.OUTPUT)}
    assert [hash_bytes(data) for data in before.values()] == ["sha256:" + h for h in expected]
    validate_snapshot(json.loads(before[drafts.OUTPUT]), historical)
    assert all((historical / p).read_bytes() == data for p, data in before.items())


def test_historical_format_is_not_assignment_compliance(context, historical):
    old = {path: (historical / path).read_bytes() for path in drafts.ARTIFACT_PATHS}
    with pytest.raises(ValueError, match="columns"):
        contract.validate_artifacts(context, old, drafts.ARTIFACT_PATHS)


@pytest.mark.parametrize("mutation", ["id", "time", "run", "claimed-current-version", "forged-legacy-version"])
def test_historical_exception_cannot_be_reused_for_other_snapshots(historical, mutation):
    snapshot = json.loads((historical / drafts.OUTPUT).read_bytes())
    if mutation == "id": snapshot["snapshot_id"] = "f27a4b1d-b0fa-47e8-88c1-bad757ae96b2"
    if mutation == "time": snapshot["created_at"] = "2026-10-18T15:00:00+00:00"
    if mutation == "run": snapshot["run_id"] = "f27a4b1d-b0fa-47e8-88c1-bad757ae96b2"
    if mutation == "claimed-current-version": snapshot["state"]["draft_contract_version"] = "assignment-drafts/1"
    if mutation == "forged-legacy-version": snapshot["state"]["draft_contract_version"] = "legacy"
    with pytest.raises(ValueError): validate_snapshot(snapshot, historical)


def test_new_build_requires_new_contract_and_preserves_pending_state(basis):
    snapshot = drafts.build_snapshot(basis)
    assert snapshot["state"]["draft_contract_version"] == "assignment-drafts/1"
    upstream = json.loads((basis / drafts.PREDECESSOR_PATH).read_bytes())
    assert snapshot["unresolved"] == upstream["unresolved"] and len(snapshot["unresolved"]) == 88
    assert snapshot["state"]["approval_requirements"] == upstream["state"]["approval_requirements"]
    assert snapshot["state"]["retained_early_screening"] == upstream["state"]["retained_early_screening"]
    for version in (None, True, 1, "legacy", "assignment-drafts/2"):
        changed = deepcopy(snapshot)
        if version is None: del changed["state"]["draft_contract_version"]
        else: changed["state"]["draft_contract_version"] = version
        with pytest.raises((ValueError, OSError)): validate_snapshot(changed, basis)
    assert not (basis / drafts.OUTPUT).exists()
