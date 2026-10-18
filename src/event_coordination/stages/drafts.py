"""Stage 8: deterministic draft bytes and controlled, separately authorized local writing.

Controlled local writing requires separate generation authorization.
No retrieval, messaging, approval ingestion or operational execution.
Artifact hashes describe rendered bytes, never purported saved files.
"""

from copy import deepcopy
import csv
from datetime import datetime, timezone
from decimal import Decimal
import html
import io
import json
import os
import stat
from contextlib import ExitStack
from pathlib import Path
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event, Timezone
from jsonschema import Draft202012Validator, FormatChecker

from event_coordination.sources import hash_bytes
from event_coordination import draft_contract
from event_coordination.run_contract import read_predecessor, bound_run_id, bound_snapshot_id
from event_coordination.stages import decisions

PREDECESSOR_PATH = decisions.OUTPUT
PREDECESSOR_ID = "f0109784-d5b8-4f2e-8a5b-cf94f3065c23"
PREDECESSOR_HASH = "sha256:ffe4619118b95982c0a53c9d7b1b02e66360a99e4bb402b9e50a1090c0353ad8"
RUN_ID = decisions.RUN_ID
BUSINESS_CLOCK = decisions.BUSINESS_CLOCK
SCHEMA_HASH = "sha256:787e6ac3e2008458b311c2ab2e287a3cafb68aaa82d49a489775864ba32221ee"
OUTPUT = "deliverables/snapshots/08-draft-propagation.json"
ANCESTOR_PATHS = (*decisions.ANCESTOR_PATHS, decisions.PREDECESSOR_PATH)
ARTIFACT_PATHS = (
    "deliverables/vendor-comparison.csv", "deliverables/event-plan.md",
    "deliverables/event-calendar.ics", "deliverables/draft-communications.md",
)
ARTIFACT_IDS = ("draft-vendor-comparison", "draft-event-plan", "draft-event-calendar", "draft-communications")
NOTICE = ("DRAFT — fictional exercise. All approval gates remain pending. No vendor selection, "
          "booking, spending, invitation, publication or production-calendar action is authorized.")
HISTORICAL_SNAPSHOT_ID = "0ae9725f-8f59-4fa9-994f-9cd18c376e70"
HISTORICAL_SNAPSHOT_HASH = "sha256:a96c01eb2fdcfbad709445918142a888c0b018ef1b6b6e6df9e748f36413d0a6"
RECORD_ARRAYS = ("artifact_drafts", "affected_dependencies", "unresolved_items",
                 "approval_requirements", "retained_early_screening", "ancestor_references")


class _PinnedInputs:
    def __init__(self, root):
        self.root = root
        self.earlier = decisions._PinnedInputs(root)
        if decisions._protected_file(root, "snapshot.schema.json")[2] != SCHEMA_HASH:
            raise ValueError("Stage 8 requires the unchanged public schema bytes")
        self.predecessor = decisions._protected_file(root, PREDECESSOR_PATH)

    def verify(self):
        self.earlier.verify()
        if decisions._protected_file(self.root, PREDECESSOR_PATH) != self.predecessor:
            raise ValueError("Stage 8 predecessor changed during evaluation")


def _check_outputs_absent(root):
    for relative in (*ARTIFACT_PATHS, OUTPUT):
        parts = decisions._parts(relative)
        with decisions._Directories(root, parts[:-1]) as directories:
            try:
                os.stat(parts[-1], dir_fd=directories.fds[-1], follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise FileExistsError("Stage 8 foundation requires absent real outputs")
            directories.verify()


def _read_snapshot(root, relative):
    identity = decisions._protected_file(root, relative)
    content = (root / relative).read_bytes()
    if hash_bytes(content) != identity[2] or decisions._protected_file(root, relative) != identity:
        raise ValueError("Stage 8 input changed while reading")
    return json.loads(content), content


def _timestamp(value):
    if type(value) is not str:
        raise ValueError("Stage 8 execution timestamp must be a UTC string")
    actual = datetime.fromisoformat(value)
    if actual.utcoffset() != timezone.utc.utcoffset(actual) or actual == datetime.fromisoformat(BUSINESS_CLOCK):
        raise ValueError("Stage 8 requires UTC execution time separate from its business clock")
    return actual


def _find_record(value, identifier):
    if isinstance(value, dict):
        if value.get("id") == identifier:
            return value
        for child in value.values():
            result = _find_record(child, identifier)
            if result is not None:
                return result
    elif isinstance(value, list):
        for child in value:
            result = _find_record(child, identifier)
            if result is not None:
                return result
    return None


def _context(root):
    from event_coordination.validation import validate_snapshot
    upstream, data = _read_snapshot(root, PREDECESSOR_PATH)
    registered = read_predecessor(root, PREDECESSOR_PATH, PREDECESSOR_HASH)
    run_id = bound_run_id(root, RUN_ID)
    if (data != registered or upstream["snapshot_id"] != bound_snapshot_id(root, PREDECESSOR_PATH, PREDECESSOR_ID)
            or upstream["run_id"] != run_id):
        raise ValueError("Stage 8 predecessor identity/hash/run mismatch")
    validate_snapshot(upstream, root)  # Recursively validates prior semantics and source integrity.
    chain = [(upstream, PREDECESSOR_PATH, data)]
    child = upstream
    for sequence, path in reversed(list(enumerate(ANCESTOR_PATHS, 1))):
        parent, content = _read_snapshot(root, path)
        if (child["predecessor"] != {"snapshot_id": parent["snapshot_id"], "path": path,
                                     "sha256": hash_bytes(content)}
                or parent["run_id"] != run_id or parent["sequence"] != sequence):
            raise ValueError("Stage 8 ancestor lineage mismatch")
        chain.append((parent, path, content))
        child = parent
    by_sequence = {s["sequence"]: s for s, _, _ in chain}
    baseline = by_sequence[4]["state"]
    baseline_records = {r["id"]: r for category in (
        "headcount_basis", "schedule_dependencies", "budget_baseline", "accessibility_baseline")
        for r in baseline[category]}
    recommendation = upstream["state"]["recommendation"]
    from event_coordination.run_contract import current_run
    if (recommendation not in {r['candidate_id'] for r in upstream['state']['candidate_reviews']}
            or (current_run(root) is None and recommendation != "option-oct17-green-table")):
        raise ValueError("Stage 8 requires an evidence-supported provisional schedule basis; deferral needs human review")
    witness_id = next(r["schedule_witness_id"] for r in upstream["state"]["candidate_reviews"]
                      if r["candidate_id"] == recommendation)
    witness = next(r for r in by_sequence[6]["state"]["schedule_witnesses"] if r["id"] == witness_id)
    result = next(r for r in by_sequence[6]["state"]["option_results"] if r["candidate_id"] == recommendation)
    proposed_quotes = [r["values"]["quote_id"] for r in by_sequence[5]["state"]["quote_evidence"]
                       if r["id"] in result["evidence_ids"]]
    floor = next(r for r in by_sequence[2]["state"]["sources"]
                 if r["source_identity"] == "official-floor-plan" and r["local_reference"])
    media_copy = "deliverables/snapshots/evidence/" + Path(floor["local_reference"]).name
    if decisions._protected_file(root, media_copy)[2] != floor["content_hash"]:
        raise ValueError("Stage 8 floor-plan media copy differs from its recorded evidence hash")
    from event_coordination.run_contract import current_run
    return {"fresh_run": current_run(root) is not None, "chain": chain, "upstream": upstream, "baseline": baseline_records,
            "quotes": by_sequence[5]["state"]["quote_evidence"], "witness": witness,
            "floor": floor, "objective": by_sequence[1]["state"]["objective"],
            "proposed_quote_ids": proposed_quotes,
            "options": {r["id"]: r for r in by_sequence[5]["state"]["options"]},
            "checks": by_sequence[6]["state"]["checks"]}


def _csv_cell(value):
    text = str(value)
    # CSV quoting does not prevent spreadsheet formula execution.
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def _md(value):
    return html.escape(str(value), quote=False).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _amount(value, historical):
    return str(value) if historical else draft_contract.whole_twd(value)


def _rationale(context, historical):
    text = context["upstream"]["state"]["review_policy"][0]["rationale"]
    return text if historical else draft_contract.monetary_prose(text)


def _render_vendor_comparison(context, historical=False):
    """Render only allowlisted quote/business fields from a verified context."""
    columns = ("row_type", "record_id", "quote_ids", "vendor_or_candidate", "category", "scope",
               "quoted_amount_twd", "allowances_twd", "planning_total_twd", "headroom_twd",
               "capacity", "capacity_meaning", "service_date", "valid_until", "source_status",
               "conditions", "evidence_ids", "source_locator", "source_sha256", "draft_status",
               "provenance_classification", "real_world_availability")
    if not historical:
        columns += draft_contract.ADDED_CSV_COLUMNS
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    def add(record, **row):
        row["draft_status"] = "draft; unselected; approvals pending; local sources unverified"
        row["provenance_classification"] = "fictional exercise evidence"
        row["real_world_availability"] = "unverified; exercise availability is not live vendor confirmation"
        if not historical:
            row.update(draft_contract.option_fields(context, row["row_type"], record))
            for key, value in row.items():
                if key.endswith("_twd") and value != "":
                    row[key] = draft_contract.whole_twd(value)
        writer.writerow({key: (value if not historical and key.endswith("_twd") else _csv_cell(value))
                         for key, value in row.items()})
    for quote in context["quotes"]:
        values = quote["values"]
        provenance = quote["source_fact"]["provenance"][0]
        add(quote, row_type="quote", record_id=quote["id"], quote_ids=values["quote_id"],
            vendor_or_candidate=values["vendor"], category=values["category"], scope=values["option"],
            quoted_amount_twd=values["quote_amount_twd"], capacity=values["capacity"],
            capacity_meaning=quote["capacity"]["interpretation"], service_date=values["available_date"],
            valid_until=values["valid_until"], source_status=values["status"], conditions=values["notes"],
            evidence_ids=quote["source_observation"]["id"], source_locator=quote["source_observation"]["locator"]["value"],
            source_sha256=provenance["sha256"])
    for review in context["upstream"]["state"]["candidate_reviews"]:
        costs = review["costs"]
        option = context["options"][review["candidate_id"]]
        members = [q for q in context["quotes"] if q["values"]["quote_id"] in option["component_quote_ids"]]
        if (len(members) != len(option["component_quote_ids"])
                or any(q["values"]["available_date"] != option["proposed_event_date"] for q in members)):
            raise ValueError("Candidate quote membership or service date is inconsistent")
        add(review, row_type="candidate", quote_ids=";".join(option["component_quote_ids"]),
            service_date=option["proposed_event_date"], record_id=review["id"], vendor_or_candidate=review["candidate_id"],
            quoted_amount_twd=costs["quoted_subtotal"],
            allowances_twd=str(sum(map(Decimal, costs["retained_allowances"].values()))),
            planning_total_twd=costs["planning_total"], headroom_twd=review["remaining_ceiling"],
            capacity=review["catering"]["capacity"], capacity_meaning=review["catering"]["meaning"],
            source_status=review["feasibility"], conditions=";".join(review["condition_ids"]),
            evidence_ids=review["id"])
    for screen in context["upstream"]["state"]["retained_early_screening"]:
        add(screen, row_type="screening", record_id=screen["id"], scope=screen["summary"],
            source_status="retained screening; not a selected remedy", evidence_ids=screen["id"])
    return stream.getvalue().encode("utf-8")


def _comparison_table(context, historical=False):
    lines = ["| Candidate | Quoted subtotal TWD | Planning total TWD | Catering capacity | Headroom TWD | Feasibility |",
             "|---|---:|---:|---:|---:|---|"]
    for r in context["upstream"]["state"]["candidate_reviews"]:
        lines.append("| " + " | ".join(map(_md, [r["candidate_id"], _amount(r["costs"]["quoted_subtotal"], historical),
            _amount(r["costs"]["planning_total"], historical), r["catering"]["capacity"],
            _amount(r["remaining_ceiling"], historical), r["feasibility"]])) + " |")
    return lines


def _proposed_details(context):
    programme = [r for r in context["witness"]["intervals"] if r["lane"] == "programme"]
    room = context["baseline"]["baseline-accessibility-space-limits"]["values"]["rooms"][0]
    return (f"Proposed date: {context['witness']['event_date']}; programme: {programme[0]['start_at']} "
            f"to {programme[-1]['end_at']} (Asia/Taipei). Proposed exercise venue: TICC, {room}. "
            "Date and venue are not approved or booked.")



def _coverage_provision(check, context, option):
    """Select business scope only; never serialize private assessment inputs."""
    requirement = check["requirement"]
    quotes = {q["values"]["quote_id"]: q["values"] for q in context["quotes"]}
    members = option["component_quote_ids"]
    catering = next(q for q in members if quotes[q]["category"] == "catering")
    if requirement.startswith(("quote-Q-", "scope-Q-")):
        identifier = requirement.split("-", 1)[1]
        return identifier + ": " + quotes[identifier]["option"]
    if "quiet" in requirement:
        return "Proposed quiet room: V.I.P. Room (fictional venue allocation); Q-010 staffing; no operational confirmation"
    if requirement.startswith("dietary-"):
        return catering + ": Operations-coordinated dietary/allergy response; individual arrangements remain private"
    if "caption" in requirement:
        return "Q-005 live captions and transcript"
    if "hearing-loop" in requirement or "av-service" in requirement:
        return "Q-006 AV package with hearing loop"
    if "step-free" in requirement:
        return "Fictional coordination basis for step-free programme/restroom routes; current routes require verification"
    if "wheelchair" in requirement or "companions" in requirement or "audience" in requirement or "venue-quote" in requirement:
        return "Q-001 audience allocation; wheelchair spaces included; companions use ordinary places"
    if "catering" in requirement:
        return catering + ": " + quotes[catering]["option"]
    if "security" in requirement or requirement == "safety":
        return "Q-009 security and first-aid staffing"
    if requirement.startswith(("category-", "allocation-policy-")) or requirement in ("quote-subtotal", "planning-total", "budget-ceiling"):
        return "Candidate quoted services plus retained communications/contingency allowances; see category budget table"
    if requirement in ("programme", "access-windows"):
        return "Proposed schedule witness: " + next(r["schedule_witness_id"] for r in context["upstream"]["state"]["candidate_reviews"] if r["candidate_id"] == option["id"])
    if requirement == "walkthrough-prerequisite":
        return "Venue confirmation required before CAL-006 accessibility walkthrough"
    if requirement == "decision-deadline":
        return "Operations review by the evidenced CAL-005 deadline; approval remains pending"
    if requirement == "attendance-basis":
        return "245-person planning quantity including uncertain forecast; needs overlap, not extra people"
    return "Proposed constituent offers: " + "; ".join(members) + "; no live operational verification"


def _coverage_tables(context):
    lines = ["", "## Candidate hard-constraint coverage", "",
             "These are preserved Stage 6 fictional-exercise assessments, not fulfillment or approvals. " +
             ("Candidate classifications: " + "; ".join(r["candidate_id"] + "=" + r["feasibility"] for r in context["upstream"]["state"]["candidate_reviews"]) + ". Venue confirmation before CAL-006 remains required. " if context.get("fresh_run") else "Both candidates remain conditional. Venue confirmation before CAL-006 remains required. ") +
             "All five approval gates and each candidate's remaining conditions apply even where an individual check passes."]
    for review in context["upstream"]["state"]["candidate_reviews"]:
        option = context["options"][review["candidate_id"]]
        lines += ["", "### " + _md(review["candidate_id"]), "",
                  "Candidate-level open conditions: " + _md("; ".join(review["condition_ids"])), "",
                  "| Requirement | Proposed provision | Exercise assessment | Remaining dependencies | Live-verification limitations | Evidence |",
                  "|---|---|---|---|---|---|"]
        for check in context["checks"]:
            if check["candidate_id"] != review["candidate_id"] or check["hard_requirement"] is not True:
                continue
            dependencies = "; ".join(check["condition_ids"]) or "No additional check-specific condition; candidate conditions and pending gates still apply"
            evidence = "; ".join([check["id"], *check["evidence_ids"]])
            lines.append("| " + " | ".join(map(_md, [check["requirement"], _coverage_provision(check, context, option),
                check["outcome"], dependencies, "; ".join(check["source_limitations"]), evidence])) + " |")
    return lines


def _render_event_plan(context, historical=False):
    upstream = context["upstream"]
    baseline = context["baseline"]
    policy = upstream["state"]["review_policy"][0]
    lines = ["# Event plan — draft", "", NOTICE, "", _md(_proposed_details(context)), "", "## Objective", "", _md(context["objective"]),
             "", "## Planning basis", ""]
    for identifier, label in (("baseline-headcount-registered", "Registered people"),
                              ("baseline-headcount-required-onsite", "Required onsite personnel"),
                              ("baseline-headcount-forecast", "Forecast walk-ins (uncertain)"),
                              ("baseline-headcount-planning-demand", "Planning quantity, not confirmed attendance")):
        lines.append(f"- {label}: {_md(baseline[identifier]['values']['value'])} [{identifier}]")
    lines += ["", "Needs overlap within that population and add no people. The check-in target is not a capacity discount.",
              "Success target: " + baseline["baseline-headcount-success-target"]["values"]["check_in_target"] + "% of registered attendees check in, all demos run, and accessibility requests receive a documented response before the event.",
              "", "## Options and provisional recommendation", "", *_comparison_table(context, historical), "",
              _md(_rationale(context, historical)), "", "Evidence: decision-policy-initial-review; both decision-review records.",
              "", "## Budget and pending authority", "",
              "Quoted subtotals plus communications 25000 and contingency 40000 yield the planning totals; do not add allocations again.",
              "", "| Category | Planned allocation TWD | Green Table proposal TWD | City Pantry proposal TWD | Approval limit TWD | Recorded commitment TWD | Owner role |",
              "|---|---:|---:|---:|---:|---:|---|"]
    reviews = upstream["state"]["candidate_reviews"]
    allocations = Decimal(0)
    for identifier, record in baseline.items():
        if identifier.startswith("baseline-budget-category-"):
            v = record["values"];category = v["category"];allocations += Decimal(v["planned_amount_twd"])
            lines.append("| " + " | ".join(map(_md, [category, _amount(v["planned_amount_twd"], historical),
                _amount(reviews[0]["category_budget"][category]["proposed"], historical),
                _amount(reviews[1]["category_budget"][category]["proposed"], historical),
                _amount(v["approval_limit_twd"], historical), _amount(v["committed_amount_twd"], historical), v["owner"]])) + " |")
    ceiling = baseline["baseline-budget-ceiling"]["values"]["value"]
    lines += ["", f"Overall ceiling: TWD {_amount(ceiling, historical)}; planned allocations: TWD {_amount(allocations, historical)}. Neither is spending authorization.",
              "Category allocation variances remain review matters; transfers are not authorized. Both have a security variance; City Pantry also has a catering variance.",
              "", "## Proposed programme and calendar constraints", "",
              "Asia/Taipei. The following is the verified exercise schedule witness, not an approved run of show. Demo ordering, breaks and flexible time remain planning choices.",
              "", "| Interval | Start | End | Resource lane | Basis |", "|---|---|---|---|---|"]
    for interval in context["witness"]["intervals"]:
        lines.append("| " + " | ".join(map(_md, [interval["id"], interval["start_at"], interval["end_at"], interval["lane"], interval["basis"]])) + " |")
    lines += ["", "Twelve demonstrations and twelve changeovers total 156 minutes; individual vendor setup durations are unspecified.",
              "", "| Constraint | Window | Source note |", "|---|---|---|"]
    for record in baseline.values():
        if record["id"].startswith("baseline-schedule-CAL-"):
            v = record["values"]
            lines.append(f"| {v['constraint_id']} | {v['start_at']} to {v['end_at']} | {_md(v['notes'])} |")
    lines += ["", "The fallback date is retained for comparison, not scheduled as an approved alternative. Date-only quote/hold expirations have no invented time cutoff.",
              "", "## Accessibility, dietary coordination and safety", "",
              "Required: step-free programme and restroom access; wheelchair seating; captions; hearing-loop coverage; a quiet room and staffing; dietary/allergy coordination; security and first aid.",
              "Exercise service confirmations do not establish current real-world operation. Verify routes, equipment and staffing before operational use. Individual arrangements must be coordinated privately with Operations; no private medical or contact details belong in these drafts.",
              "", "Proposed quiet room: V.I.P. Room, from the fictional venue allocation [baseline-accessibility-space-limits; option-source-Q-001]. Q-010 proposes staffing; this is not a confirmed operational arrangement.",
              *_coverage_tables(context),
              "", "## Registered floor-plan observations", ""]
    for obs in context["floor"]["observations"]:
        lines.append(f"- {_md(obs['summary'])} [{obs['id']}; {_md(obs['locator']['value'])}]")
    lines += ["", f"Registered PDF: {_md(context['floor']['local_reference'])}; {_md(context['floor']['content_hash'])}.",
              "Disclosed source: " + _md(context["floor"]["locator"]) + ". Browser origin and live equivalence remain unverified."]
    lines += ["", "The preserved PDF identifies the floor/venue; it does not certify current access, route clearance or service operation.",
              "", "## Unresolved conditions and review requests", "",
              (f"All {len(upstream['unresolved'])} inherited unresolved records remain in the internal snapshot. Public drafts summarize impact without reproducing private attendee details." if not historical else "All 88 inherited unresolved records remain in the internal snapshot. Public drafts summarize impact without reproducing private attendee details."),
              "Venue confirmation must precede the accessibility walkthrough. Allocation reviews, quote expiry precision, forecast uncertainty, unverified local copies and live-service verification remain open."]
    for snapshot, _, _ in context["chain"]:
        if snapshot["sequence"] == 2:
            for capture in snapshot["state"]["sources"]:
                if capture["source_identity"] == "official-plenary-hall" and capture["retrieval_status"] == "retrieved":
                    lines += ["", "## Official Plenary Hall webpage — current public rules", "",
                              "Retrieved " + capture["retrieved_at"] + "; " + capture["locator"] + "; " + capture["content_hash"] + "."]
                    lines += ["- " + _md(o["summary"]) + " [" + o["id"] + "; " + _md(o["locator"]["value"]) + "]" for o in capture["observations"]]
                    lines += ["Venue-policy review remains pending before real use; no permission, briefing completion or new calendar time is invented. The current page does not establish its contents at the simulated business clock.", ""]
    for gate in upstream["state"]["approval_requirements"]:
        lines.append(f"- {gate['id']}: pending; {_md(gate['summary'])} Applicability: {_md(gate['applies_if'])}; owner role: {_md(gate['owner'] or 'not established')}; deadline: {_md(gate.get('deadline') or 'not established')}.")
    for screen in upstream["state"]["retained_early_screening"]:
        lines.append(f"- Retained {screen['id']}: {_md(screen['summary'])}")
    lines += ["", f"Business evaluation clock: {BUSINESS_CLOCK}; this is not a retrieval timestamp.",
              "Source provenance and record/section dependencies are retained in the in-memory Stage 8 model."]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _calendar_entries(context):
    entries = [(r["id"], r["kind"], r["start_at"], r["end_at"], r["lane"], context["witness"]["id"])
               for r in context["witness"]["intervals"]]
    for code in ("CAL-005", "CAL-006", "CAL-007"):
        record = context["baseline"]["baseline-schedule-" + code];v = record["values"]
        entries.append((record["id"], v["constraint_type"], v["start_at"], v["end_at"], "review-and-preparation", record["id"]))
    return entries


def _render_event_calendar(context, created_at, historical=False):
    calendar = Calendar()
    calendar.add("prodid", "-//Project C//In-memory draft foundation//EN")
    calendar.add("version", "2.0")
    if not historical:
        calendar.add("method", "PUBLISH")  # Draft file metadata; no delivery action.
    calendar.add("x-draft-notice", NOTICE)
    dates = [datetime.fromisoformat(entry[2]).date() for entry in _calendar_entries(context)]
    calendar.add_component(Timezone.from_tzinfo(ZoneInfo("Asia/Taipei"),
        first_date=min(dates), last_date=max(dates)))
    for identifier, label, start, end, lane, evidence in _calendar_entries(context):
        event = Event()
        event.add("uid", str(uuid5(NAMESPACE_URL, context["upstream"]["run_id"] + ":" + identifier)))
        event.add("dtstamp", _timestamp(created_at))
        event.add("dtstart", datetime.fromisoformat(start).astimezone(ZoneInfo("Asia/Taipei")))
        if start != end:  # A deadline is a point marker, not an invented meeting.
            event.add("dtend", datetime.fromisoformat(end).astimezone(ZoneInfo("Asia/Taipei")))
        event.add("summary", "DRAFT: " + label)
        event.add("description", NOTICE + " Proposed exercise schedule. Venue confirmation and all authorizations remain pending.")
        event.add("status", "TENTATIVE")
        event.add("transp", "TRANSPARENT")
        event.add("x-evidence-id", evidence)
        event.add("x-resource-lane", lane)
        calendar.add_component(event)
    payload = calendar.to_ical()
    parsed = Calendar.from_ical(payload)
    if ((parsed.get("METHOD") is not None if historical else str(parsed.get("METHOD")) != "PUBLISH")
            or len(parsed.walk("VEVENT")) != len(_calendar_entries(context))):
        raise ValueError("Unsafe or incomplete tentative calendar")
    return payload


def _render_communications(context, historical=False):
    upstream = context["upstream"]
    lines = ["# Unsent communications — drafts", "", NOTICE, "",
             "Audience roles below are not verified recipients or distribution lists. No addresses, invitation transmission or supplier commitments are supplied.",
             "", _md(_proposed_details(context)), "", "## Operations review — UNSENT", "",
             "Please review the proposed plan, date/venue, headcount basis, hard-constraint results and outstanding conditions. This request is not evidence of approval.",
             "", *_comparison_table(context, historical), "", _md(_rationale(context, historical)),
             "", "## Category budget owners — UNSENT", "",
             "Please review your proposed category cost, allocation variance, approval limit and quote validity against the plan revision. Spending remains unauthorized, including amounts below approval limits. No transfer is approved.",
             "", "## Vendors — UNSENT confirmation request", "",
             "Proposed exercise quote references for confirmation only: " + ", ".join(context["proposed_quote_ids"]) + ". No supplier is selected.",
             "Please confirm the cited service date, quote validity, scope, capacity, exclusions and operational prerequisites for review. This is not an order, acceptance, booking or payment authorization.",
             "", "## Staff — UNSENT planning note", "",
             "The proposed programme, setup/readiness and teardown windows remain subject to review. Accessibility, quiet-room staffing, dietary coordination, security and first aid must be checked through Operations. Coordinate individual arrangements privately.",
             "", "## Attendees — UNSENT proposed information", "",
             "Event details are provisional. Accessible participation and dietary coordination are being planned; no accommodation is guaranteed by this draft. A reviewed contact channel and final arrangements must be supplied by Operations before any release.",
             "", "## Conditions before release", "",
             "All five approval gates remain pending; the Programme gate applies only to roster/duration changes. Venue confirmation, category allocation reviews and current service verification remain open. Do not send these drafts or import the calendar into production without human authorization."]
    if not historical:
        for title, *_ in draft_contract.MESSAGES:
            index = next(i for i, line in enumerate(lines) if line.startswith(f"## {title} — UNSENT"))
            lines[index] = f"## {title} — UNSENT DRAFT"
            fields = draft_contract.message_fields(context, title)
            lines[index + 1:index + 1] = ["", *(f"- {key}: {_md(value)}" for key, value in fields.items()), ""]
    return ("\n".join(lines) + "\n").encode("utf-8")


def render_vendor_comparison(context):
    return _render_vendor_comparison(context)


def render_event_plan(context):
    return _render_event_plan(context)


def render_event_calendar(context, created_at):
    return _render_event_calendar(context, created_at)


def render_communications(context):
    return _render_communications(context)


def render_artifacts(context, created_at):
    """Pure rendering from the internally validated context and batch timestamp."""
    return dict(zip(ARTIFACT_PATHS, (render_vendor_comparison(context), render_event_plan(context),
        render_event_calendar(context, created_at), render_communications(context)), strict=True))



def _validate_content(context, artifacts, created_at, *, historical=False):
    """Independent parsed cross-checks; reconstruction alone is not sufficient."""
    if set(artifacts) != set(ARTIFACT_PATHS) or any(type(v) is not bytes for v in artifacts.values()):
        raise ValueError("Stage 8 rendered artifact scope/type mismatch")
    if not historical:
        draft_contract.validate_artifacts(context, artifacts, ARTIFACT_PATHS)
    rows = list(csv.DictReader(io.StringIO(artifacts[ARTIFACT_PATHS[0]].decode("utf-8"))))
    quote_rows = [r for r in rows if r.get("row_type") == "quote"]
    candidate_rows = [r for r in rows if r.get("row_type") == "candidate"]
    quotes = {q["values"]["quote_id"]: q["values"] for q in context["quotes"]}
    if (len(rows) != 16 or len(quote_rows) != 10 or len(candidate_rows) != 2
            or {r["quote_ids"] for r in quote_rows} != set(quotes)):
        raise ValueError("Stage 8 CSV is incomplete")
    for row in quote_rows:
        source = quotes[row["quote_ids"]]
        if (Decimal(row["quoted_amount_twd"]) != Decimal(source["quote_amount_twd"])
                or row["service_date"] != source["available_date"]
                or row["conditions"] != _csv_cell(source["notes"])
                or row["capacity"] != str(source["capacity"]) or row["source_status"] != source["status"]):
            raise ValueError("Stage 8 CSV quote differs from evidence")
    plan = artifacts[ARTIFACT_PATHS[1]].decode("utf-8")
    communications = artifacts[ARTIFACT_PATHS[3]].decode("utf-8")
    if {r["vendor_or_candidate"] for r in candidate_rows} != set(context["options"]):
        raise ValueError("Stage 8 candidate comparison is incomplete")
    for row in candidate_rows:
        option = context["options"][row["vendor_or_candidate"]]
        members = row["quote_ids"].split(";")
        subtotal = sum(Decimal(quotes[q]["quote_amount_twd"]) for q in option["component_quote_ids"])
        allowances = sum(Decimal(v) for v in option["retained_allowances"].values())
        total = subtotal + allowances
        ceiling = Decimal(context["baseline"]["baseline-budget-ceiling"]["values"]["value"])
        if (members != option["component_quote_ids"] or row["service_date"] != option["proposed_event_date"]
                or Decimal(row["quoted_amount_twd"]) != subtotal or Decimal(row["allowances_twd"]) != allowances
                or Decimal(row["planning_total_twd"]) != total or Decimal(row["headroom_twd"]) != ceiling-total):
            raise ValueError("Stage 8 cross-artifact costs or membership differ from evidence")
        review = next(r for r in context["upstream"]["state"]["candidate_reviews"] if r["candidate_id"] == option["id"])
        if (row["capacity"] != review["catering"]["capacity"]
                or row["source_status"] != review["feasibility"]
                or row["conditions"] != ";".join(review["condition_ids"])):
            raise ValueError("Stage 8 candidate capacity, feasibility or conditions are inconsistent")
        expected_row = "| " + " | ".join(map(_md, [option["id"], _amount(subtotal, historical), _amount(total, historical),
            review["catering"]["capacity"], _amount(ceiling-total, historical), review["feasibility"]])) + " |"
        if expected_row not in plan or expected_row not in communications:
            raise ValueError("Stage 8 plan/communications comparison is inconsistent")
    if (NOTICE not in plan or NOTICE not in communications or "Proposed quiet room: V.I.P. Room" not in plan
            or any(r["provenance_classification"] != "fictional exercise evidence" for r in quote_rows+candidate_rows)):
        raise ValueError("Stage 8 draft/provenance boundary is missing")
    calendar = Calendar.from_ical(artifacts[ARTIFACT_PATHS[2]])
    entries = _calendar_entries(context)
    events = calendar.walk("VEVENT")
    if ((calendar.get("METHOD") is not None if historical else str(calendar.get("METHOD")) != "PUBLISH")
            or len(events) != len(entries)):
        raise ValueError("Stage 8 calendar scope mismatch")
    for event, (identifier, label, start, end, lane, evidence) in zip(events, entries, strict=True):
        if (str(event["UID"]) != str(uuid5(NAMESPACE_URL, context["upstream"]["run_id"] + ":" + identifier))
                or event.decoded("DTSTART") != datetime.fromisoformat(start)
                or (start != end and event.decoded("DTEND") != datetime.fromisoformat(end))
                or (start == end and (event.get("DTEND") is not None or event.get("DURATION") is not None))
                or str(event["STATUS"]) != "TENTATIVE" or str(event["TRANSP"]) != "TRANSPARENT"
                or event.get("ATTENDEE") is not None or event.get("ORGANIZER") is not None or event.subcomponents
                or str(event["X-RESOURCE-LANE"]) != lane
                or str(event["X-EVIDENCE-ID"]) != evidence or str(event["SUMMARY"]) != "DRAFT: " + label
                or NOTICE not in str(event["DESCRIPTION"])
                or event["DTSTART"].params.get("TZID") != "Asia/Taipei"
                or event.decoded("DTSTAMP") != _timestamp(created_at).replace(microsecond=0)):
            raise ValueError("Stage 8 calendar differs from proposed schedule or draft boundary")
    for interval in context["witness"]["intervals"]:
        if not all(value in plan for value in (interval["id"], interval["start_at"], interval["end_at"])):
            raise ValueError("Stage 8 plan omits a calendar schedule interval")


def _expected(root, created_at, mode="in-memory-only", *, historical=False):
    context = _context(root)
    upstream = context["upstream"]
    if historical:
        artifacts = dict(zip(ARTIFACT_PATHS, (
            _render_vendor_comparison(context, True), _render_event_plan(context, True),
            _render_event_calendar(context, created_at, True), _render_communications(context, True)), strict=True))
    else:
        artifacts = render_artifacts(context, created_at)
    _validate_content(context, artifacts, created_at, historical=historical)
    state = {key: [] for key in RECORD_ARRAYS}
    consumed = set(upstream["produced_record_ids"])
    owners = {}
    for snapshot, path, content in reversed(context["chain"]):
        for identifier in snapshot["produced_record_ids"]:
            owners[identifier] = (snapshot, path, content)
    references = {}
    closure_cache = {}
    def use(identifier):
        if identifier not in owners:
            raise ValueError("Stage 8 dependency lacks a verified owner")
        consumed.add(identifier)
        if identifier not in upstream["produced_record_ids"] and identifier not in references:
            snapshot, path, content = owners[identifier]
            references[identifier] = {"id": "draft-ancestor-" + identifier,
                "summary": "Verified ancestor ownership; source verification is not upgraded.",
                "evidence_ids": [identifier], "record_id": identifier, "snapshot_id": snapshot["snapshot_id"],
                "snapshot_path": path, "snapshot_sha256": hash_bytes(content), "stage": snapshot["stage"], "run_id": snapshot["run_id"]}
        return identifier
    def closure(identifier, visiting=None):
        if identifier in closure_cache:
            return closure_cache[identifier]
        visiting = set() if visiting is None else visiting
        if identifier in visiting:
            return {identifier}
        use(identifier)
        record = _find_record(owners[identifier][0], identifier)
        if record is None:
            raise ValueError("Stage 8 dependency record is missing")
        result = {identifier}
        for parent in record.get("evidence_ids", []):
            result |= closure(parent, visiting | {identifier})
        closure_cache[identifier] = result
        return result
    def impact(artifact_id, locator, identifiers):
        direct = sorted(set(identifiers))
        ids = sorted(set().union(*(closure(i) for i in direct))) if direct else []
        if not ids:
            raise ValueError("Draft section requires evidence")
        state["affected_dependencies"].append({"id": "dependency-" + artifact_id + "-" + locator,
            "summary": "Changed inputs require upstream reevaluation and renewed draft review.",
            "evidence_ids": ids, "source_record_ids": direct, "target_artifact_id": artifact_id,
            "target_locator": locator, "on_change": "stop-and-reevaluate-upstream", "external_actions_authorized": False})
    common = [r["id"] for r in upstream["state"]["candidate_reviews"]] + ["decision-policy-initial-review"]
    quote_ids = [r["id"] for r in context["quotes"]]
    baseline_ids = [i for i in context["baseline"] if not i.startswith("baseline-needs-")]
    witness_id = context["witness"]["id"]
    for artifact_id, path in zip(ARTIFACT_IDS, ARTIFACT_PATHS, strict=True):
        relevant = list(common)
        if artifact_id == "draft-vendor-comparison": relevant += quote_ids
        if artifact_id == "draft-event-plan": relevant += baseline_ids + ["ev-objective", witness_id] + [o["id"] for o in context["floor"]["observations"]]
        if artifact_id == "draft-event-calendar": relevant += [witness_id] + ["baseline-schedule-CAL-00" + str(n) for n in range(1,9)]
        relevant += [r["id"] for r in upstream["state"]["approval_requirements"]]
        relevant += [r["id"] for r in upstream["state"]["retained_early_screening"]]
        impact(artifact_id, "comparison-and-review", relevant)
        if artifact_id == "draft-vendor-comparison":
            for quote in context["quotes"]:
                impact(artifact_id, "row-" + quote["values"]["quote_id"], [quote["id"]])
        if artifact_id == "draft-event-plan":
            for section, prefixes in (("headcount", ("baseline-headcount-",)),
                                       ("budget", ("baseline-budget-",)),
                                       ("accessibility", ("baseline-accessibility-", "baseline-needs-"))):
                impact(artifact_id, "section-" + section, [i for i in context["baseline"] if i.startswith(prefixes)])
            impact(artifact_id, "section-programme", [witness_id])
        if artifact_id == "draft-event-calendar":
            for identifier, _, _, _, _, evidence in _calendar_entries(context):
                impact(artifact_id, "uid-" + str(uuid5(NAMESPACE_URL, upstream["run_id"] + ":" + identifier)), [evidence])
        # Preserve every inherited issue without publishing its raw text in general artifacts.
        unresolved_ids = [r["id"] for r in upstream["unresolved"]]
        impact(artifact_id, "unresolved-context", unresolved_ids)
        state["unresolved_items"].append({"id": "impact-" + artifact_id,
            "summary": "All inherited issues remain open; public draft contains audience-appropriate impact summaries.",
            "evidence_ids": sorted(unresolved_ids), "artifact_id": artifact_id,
            "inherited_unresolved_ids": list(unresolved_ids), "resolution_status": "unresolved"})
        payload = artifacts[path]
        state["artifact_drafts"].append({"id": artifact_id, "path": path, "sha256": hash_bytes(payload),
            "validation_status": "not-produced", "render_validation_status": "valid",
            "hash_scope": "rendered-in-memory-bytes", "saved_file_verified": False,
            "storage_state": "planned-in-memory-only", "byte_length": len(payload),
            "rendered_text": payload.decode("utf-8"), "evidence_ids": sorted({use(i) for i in relevant}),
            "output_status": "draft", "selected": False, "external_actions_authorized": False})
    state["approval_requirements"] = deepcopy(upstream["state"]["approval_requirements"])
    state["retained_early_screening"] = deepcopy(upstream["state"]["retained_early_screening"])
    unresolved = deepcopy(upstream["unresolved"])
    # Preserve the original evidence IDs on carried records, declaring actual owners.
    for record in unresolved + state["approval_requirements"] + state["retained_early_screening"]:
        for identifier in record["evidence_ids"]: use(identifier)
    state["ancestor_references"] = [references[i] for i in sorted(references)]
    state.update(business_clock=BUSINESS_CLOCK, business_timezone="Asia/Taipei", output_status="draft",
                 audience="internal-evidence-review", generation_mode="in-memory-only",
                 recommendation=upstream["state"]["recommendation"], learner_decisions=[],
                 inherited_unresolved_ids=[r["id"] for r in unresolved], external_actions_authorized=False)
    if not historical:
        state["draft_contract_version"] = draft_contract.VERSION
    if mode == "saved-files-verified":
        state["generation_mode"] = mode
        for record in state["artifact_drafts"]:
            record.update(validation_status="valid", saved_file_verified=True,
                          hash_scope="verified-saved-bytes", storage_state="verified-saved-file")
    elif mode != "in-memory-only":
        raise ValueError("Unsupported Stage 8 generation mode")
    records = [r for key in RECORD_ARRAYS for r in state[key]] + unresolved
    produced = [r["id"] for r in records]
    if len(produced) != len(set(produced)) or any(not set(r["evidence_ids"]) <= consumed | set(produced) for r in records):
        raise ValueError("Stage 8 record lineage is inconsistent")
    return {"run_id": upstream["run_id"], "stage": "draft-propagation", "sequence": 8, "status": "partial",
            "predecessor": {"snapshot_id": upstream["snapshot_id"], "path": PREDECESSOR_PATH,
                            "sha256": hash_bytes(context["chain"][0][2])},
            "consumed_record_ids": sorted(consumed), "produced_record_ids": produced,
            "state": state, "unresolved": unresolved, "decisions": []}


def build_snapshot(root: Path):
    """Return a proposed Stage 8 snapshot without creating any output files."""
    root = Path(root)
    pinned = _PinnedInputs(root)
    _check_outputs_absent(root)
    created_at = datetime.now(timezone.utc).isoformat()
    snapshot = {"schema_version": "event-coordination-stage-snapshot/2", "snapshot_id": str(uuid4()),
                "created_at": created_at, **_expected(root, created_at)}
    validate_stage8(snapshot, root)
    pinned.verify()
    _check_outputs_absent(root)
    return snapshot


def rendered_bytes(snapshot):
    """Extract planned bytes; callers must validate source semantics separately."""
    records = snapshot["state"]["artifact_drafts"]
    if len(records) != 4 or {r["path"] for r in records} != set(ARTIFACT_PATHS):
        raise ValueError("Stage 8 artifact path scope mismatch")
    result = {}
    for r in records:
        if type(r["rendered_text"]) is not str:
            raise ValueError("Stage 8 rendered text must be UTF-8 text")
        payload = r["rendered_text"].encode("utf-8")
        if hash_bytes(payload) != r["sha256"] or len(payload) != r["byte_length"]:
            raise ValueError("Stage 8 rendered bytes/hash mismatch")
        result[r["path"]] = payload
    return result


def build_bundle(root: Path):
    snapshot = build_snapshot(root)
    return snapshot, rendered_bytes(snapshot)


def validate_stage8(snapshot, root):
    root = Path(root)
    pinned = _PinnedInputs(root)
    version = snapshot.get("state", {}).get("draft_contract_version")
    historical = version is None
    if historical:
        # Only the exact previously audited saved snapshot can use the old format.
        # No caller-controlled profile flag or copied run ID grants an exemption.
        saved, content = _read_snapshot(root, OUTPUT)
        if (snapshot.get("snapshot_id") != HISTORICAL_SNAPSHOT_ID
                or hash_bytes(content) != HISTORICAL_SNAPSHOT_HASH
                or snapshot.get("state", {}).get("generation_mode") != "saved-files-verified"):
            raise ValueError("Only the pinned historical Stage 8 snapshot has a legacy draft format")
        decisions._strict_equal(saved, snapshot)
    elif type(version) is not str or version != draft_contract.VERSION:
        raise ValueError("Unsupported draft artifact contract version")
    mode = snapshot.get("state", {}).get("generation_mode")
    if mode not in ("in-memory-only", "saved-files-verified"):
        raise ValueError("Unsupported Stage 8 generation mode")
    if mode == "in-memory-only":
        _check_outputs_absent(root)
    saved_identities = {}
    if mode == "saved-files-verified":
        saved_identities = _verify_saved_artifacts(root, rendered_bytes(snapshot))
        if os.path.lexists(root / OUTPUT):
            saved_snapshot, saved_bytes = _read_snapshot(root, OUTPUT)
            decisions._strict_equal(saved_snapshot, snapshot)
            saved_identities[OUTPUT] = _read_saved(root, OUTPUT, saved_bytes)
    schema = json.loads((root / "snapshot.schema.json").read_bytes())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(snapshot)
    _timestamp(snapshot["created_at"])
    UUID(snapshot["snapshot_id"])
    expected = _expected(root, snapshot["created_at"], mode, historical=historical)
    envelope = {"schema_version", "snapshot_id", "created_at"}
    if snapshot.keys() != expected.keys() | envelope or snapshot["snapshot_id"] in {
            json.loads((root/p).read_bytes())["snapshot_id"] for p in (*ANCESTOR_PATHS, PREDECESSOR_PATH)}:
        raise ValueError("Stage 8 envelope or snapshot identity is invalid")
    if snapshot["schema_version"] != "event-coordination-stage-snapshot/2":
        raise ValueError("Stage 8 schema version mismatch")
    for key, value in expected.items(): decisions._strict_equal(snapshot[key], value)
    rendered_bytes(snapshot)
    for category in RECORD_ARRAYS:
        record_schema = "artifactRecord" if category == "artifact_drafts" else "record"
        validator = Draft202012Validator({"$ref": "#/$defs/" + record_schema, "$defs": schema["$defs"]})
        for record in snapshot["state"][category]: validator.validate(record)
    if mode == "in-memory-only":
        _check_outputs_absent(root)
    else:
        _verify_saved_artifacts(root, rendered_bytes(snapshot), saved_identities)
        if OUTPUT in saved_identities and decisions._protected_file(root, OUTPUT) != saved_identities[OUTPUT]:
            raise ValueError("Stage 8 saved snapshot changed during validation")
    pinned.verify()


def validate_bundle(snapshot, artifacts, root):
    validate_stage8(snapshot, root)
    decisions._strict_equal(artifacts, rendered_bytes(snapshot))


def affected_targets(snapshot, changed_record_ids):
    """Pure impact report, not automatic replanning or permission to edit history."""
    if (type(changed_record_ids) not in (list, tuple) or not changed_record_ids
            or any(type(i) is not str for i in changed_record_ids)):
        raise ValueError("Impact analysis requires actual record IDs")
    dependencies = snapshot["state"]["affected_dependencies"]
    known = {i for r in dependencies for i in r["evidence_ids"]}
    if not set(changed_record_ids) <= known:
        raise ValueError("Changed record is outside this verified dependency graph")
    return sorted({(r["target_artifact_id"], r["target_locator"]) for r in dependencies
                   if set(r["evidence_ids"]) & set(changed_record_ids)})



def _read_saved(root, relative, expected, identity=None):
    """Reopen through no-follow descriptors; verify bytes, name and stable identity."""
    parts = decisions._parts(relative)
    with decisions._Directories(root, parts[:-1]) as directories:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                     dir_fd=directories.fds[-1])
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError("Stage 8 output must be a singly linked regular file")
            remaining = len(expected) + 1
            chunks = []
            while remaining:
                block = os.read(fd, min(65536, remaining))
                if not block:
                    break
                chunks.append(block)
                remaining -= len(block)
            saved = b"".join(chunks)
            after = os.fstat(fd)
            named = os.stat(parts[-1], dir_fd=directories.fds[-1], follow_symlinks=False)
            current = ("file", decisions._identity(after), hash_bytes(saved))
            if (decisions._identity(before) != decisions._identity(after)
                    or decisions._identity(after) != decisions._identity(named)
                    or saved != expected or (identity is not None and current != identity)):
                raise ValueError("Stage 8 saved bytes or output identity changed")
            directories.verify()
            return current
        finally:
            os.close(fd)


def _verify_saved_artifacts(root, artifacts, identities=None):
    return {path: _read_saved(root, path, payload, (identities or {}).get(path))
            for path, payload in artifacts.items()}


def _write_exclusive(root, relative, payload, directories):
    """Constrained kernel creation, complete writes, fsync, then independent reopen."""
    directories.verify()
    fd = decisions._exclusive_output(directories.fds[0], relative)
    try:
        def observe():
            directories.verify()
            current = os.fstat(fd)
            named = os.stat(decisions._parts(relative)[-1], dir_fd=directories.fds[-1], follow_symlinks=False)
            if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1
                    or decisions._identity(current) != decisions._identity(named)):
                raise ValueError("Stage 8 output identity changed")
            return decisions._identity(current)
        observe()
        pending = memoryview(payload)
        while pending:
            count = os.write(fd, pending)
            if type(count) is not int or count <= 0 or count > len(pending):
                raise ValueError("Stage 8 output write failed")
            pending = pending[count:]
        os.fsync(fd)
        identity = ("file", observe(), hash_bytes(payload))
        _read_saved(root, relative, payload, identity)
        if observe() != identity[1]:
            raise ValueError("Stage 8 output changed after reopening")
        os.fsync(directories.fds[-1])
        return identity
    finally:
        os.close(fd)


def write_snapshot(root: Path) -> tuple[Path, str]:
    """Write four drafts, verify saved bytes, then exclusively write Snapshot 08.

    Not a multi-file transaction. Failures leave evidence of partial work intact.
    Never retry over existing outputs; recovery requires separate human review.
    """
    root = Path(root)
    pinned = _PinnedInputs(root)
    with ExitStack() as stack:
        parents = {path: stack.enter_context(decisions._Directories(root, decisions._parts(path)[:-1]))
                   for path in (*ARTIFACT_PATHS, OUTPUT)}
        _check_outputs_absent(root)
        snapshot, artifacts = build_bundle(root)
        validate_bundle(snapshot, artifacts, root)
        identities = {}
        written_bytes = {}
        def verify_progress():
            for directories in parents.values():
                directories.verify()
            for path in (*ARTIFACT_PATHS, OUTPUT):
                if path in identities:
                    _read_saved(root, path, written_bytes[path], identities[path])
                else:
                    parts = decisions._parts(path)
                    try:
                        os.stat(parts[-1], dir_fd=parents[path].fds[-1], follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                    else:
                        raise FileExistsError("Stage 8 destination collision")
            pinned.verify()
        verify_progress()
        for path in ARTIFACT_PATHS:
            identities[path] = _write_exclusive(root, path, artifacts[path], parents[path])
            written_bytes[path] = artifacts[path]
            verify_progress()
        # Only saved-byte verification permits these metadata upgrades.
        snapshot = deepcopy(snapshot)
        snapshot["state"]["generation_mode"] = "saved-files-verified"
        for record in snapshot["state"]["artifact_drafts"]:
            record.update(validation_status="valid", saved_file_verified=True,
                          hash_scope="verified-saved-bytes", storage_state="verified-saved-file")
        validate_stage8(snapshot, root)
        verify_progress()
        content = (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        identities[OUTPUT] = _write_exclusive(root, OUTPUT, content, parents[OUTPUT])
        written_bytes[OUTPUT] = content
        verify_progress()
        saved, actual = _read_snapshot(root, OUTPUT)
        if actual != content:
            raise ValueError("Stage 8 saved snapshot differs from validated bytes")
        validate_stage8(saved, root)
        verify_progress()
        return root / OUTPUT, hash_bytes(actual)
