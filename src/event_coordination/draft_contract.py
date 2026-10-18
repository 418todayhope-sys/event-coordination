"""Published draft contract, version 1. Pure formatting and content checks only.

Assignment source: published starter README c724104, lines 104–110. Context must
come from the stage's verified inputs; these helpers do not authenticate sources.
"""

import csv
from decimal import Decimal, InvalidOperation
import io
import json
import re

from icalendar import Calendar

VERSION = "assignment-drafts/1"
REQUIRED_CSV_COLUMNS = (
    "option_id", "quote_ids", "planning_people", "cost_twd", "currency", "feasibility",
    "availability_status", "evidence_ids", "tradeoffs", "unresolved", "approval_status",
)
ADDED_CSV_COLUMNS = tuple(c for c in REQUIRED_CSV_COLUMNS if c not in {"quote_ids", "evidence_ids"})
MESSAGES = (
    ("Operations review", "Operations", "Review the proposed plan, date, venue and outstanding conditions.", "gate-operations"),
    ("Category budget owners", "Category budget owners", "Review category amounts, allocation variances and spending requests.", "gate-spending"),
    ("Vendors", "Vendors (contacts not verified)", "Request verification of quoted scope, dates and prerequisites; no order or acceptance.", "gate-external-actions"),
    ("Staff", "Staff (distribution list not verified)", "Prepare provisional programme, accessibility and safety coordination.", "gate-external-actions"),
    ("Attendees", "Attendees (distribution list not verified)", "Prepare provisional information; individual arrangements remain private.", "gate-external-actions"),
)


def whole_twd(value):
    """Canonical integer text; reject fractions, unknowns, Booleans and floats."""
    if type(value) not in (str, int, Decimal):
        raise ValueError("A whole-number TWD value is required")
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount != amount.to_integral_value():
            raise ValueError("A whole-number TWD value is required")
        return "0" if amount == 0 else format(amount.quantize(Decimal(1)), "f")
    except (InvalidOperation, TypeError):
        raise ValueError("A whole-number TWD value is required") from None


def monetary_prose(text):
    """Format derived policy prose only. Never apply to original source notes."""
    return re.sub(r"\bTWD\s+(-?\d+(?:\.\d+)?)", lambda m: "TWD " + whole_twd(m[1]), text)


def _array(items):
    return json.dumps(list(items), ensure_ascii=False, separators=(",", ":"))


def _gates(context):
    gates = context["upstream"]["state"]["approval_requirements"]
    if any(g["status"] != "pending" for g in gates):
        raise ValueError("No new approval evidence is supported by this draft contract")
    return {g["id"]: g for g in gates}


def option_fields(context, row_type, record):
    """Allowlisted meanings: package costs differ from individual service quotes."""
    _gates(context)
    result = {"option_id": record["id"], "planning_people": "", "cost_twd": "",
              "currency": "TWD", "feasibility": "unverified", "availability_status": "unverified",
              "approval_status": "pending"}
    if row_type == "candidate":
        option = context["options"][record["candidate_id"]]
        if (record["selected"] is not False or record["spending_authorized"] is not False
                or record["authorization_status"] != "pending"):
            raise ValueError("Draft comparison cannot promote authorization or selection")
        result.update(option_id=record["candidate_id"],
                      planning_people=whole_twd(record["catering"]["planning_demand"]),
                      cost_twd=whole_twd(record["costs"]["planning_total"]),
                      feasibility=record["feasibility"])
        summary = (f"Planning cost TWD {result['cost_twd']}; remaining ceiling TWD "
                   f"{whole_twd(record['remaining_ceiling'])}; catering capacity "
                   f"{whole_twd(record['catering']['capacity'])} people for planning demand "
                   f"{result['planning_people']}. Capacity is service-specific; attendance includes a forecast.")
        result["tradeoffs"] = _array([summary, *(t["summary"] for t in context["upstream"]["state"]["tradeoffs"])])
        result["unresolved"] = _array(record["condition_ids"])
        if len(option["component_quote_ids"]) != len(set(option["component_quote_ids"])):
            raise ValueError("Duplicate constituent offer")
    elif row_type == "quote":
        result["cost_twd"] = whole_twd(record["values"]["quote_amount_twd"])
        result["tradeoffs"] = _array(["Quoted service only; not a complete event package. Capacity has the quoted service's meaning."])
        result["unresolved"] = _array(["Standalone feasibility and live availability are unverified; no whole-event planning quantity is assigned."])
    elif row_type == "screening":
        if record["authorization_status"] != "pending":
            raise ValueError("Screening is not authorization")
        result["cost_twd"] = whole_twd(record["planning_total"]) if "planning_total" in record else ""
        result["tradeoffs"] = _array(record["screening_reasons"])
        result["unresolved"] = _array([
            "Retained early screening, not a fully tested package; see the evidence-linked reasons.",
            *([] if result["cost_twd"] else ["No complete package total is evidenced; cost remains blank."]),
            *record["reconsideration_requirements"],
        ])
    else:
        raise ValueError("Unknown comparison row kind")
    return result


def message_fields(context, title):
    item = next(m for m in MESSAGES if m[0] == title)
    _, audience, purpose, gate_id = item
    gate = _gates(context)[gate_id]
    owner = gate["owner"]
    return {
        "Audience": audience,
        "Purpose": purpose,
        "Conditions": ("Review only. Relevant approvals and service verification remain pending; "
                       "no sending, booking or spending is authorized."),
        "Approval owner": (f"{owner} (role only; approval pending) [{gate_id}]" if owner else
                           f"Unresolved: release authorization owner is not established; do not send [{gate_id}]"),
    }


def validate_artifacts(context, artifacts, paths):
    """Independent published-field checks in addition to Stage 8 reconstruction."""
    reader = csv.DictReader(io.StringIO(artifacts[paths[0]].decode("utf-8")))
    if (reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames))
            or not set(REQUIRED_CSV_COLUMNS) <= set(reader.fieldnames)):
        raise ValueError("Published vendor comparison columns are missing or ambiguous")
    rows = list(reader)
    quotes = {q["values"]["quote_id"]: q for q in context["quotes"]}
    reviews = {r["candidate_id"]: r for r in context["upstream"]["state"]["candidate_reviews"]}
    screens = {r["id"]: r for r in context["upstream"]["state"]["retained_early_screening"]}
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Malformed CSV row")
        for key, value in row.items():
            if key.endswith("_twd") and value and (not re.fullmatch(r"-?(0|[1-9][0-9]*)", value)
                                                   or whole_twd(value) != value):
                raise ValueError("CSV TWD amounts must be whole-number text")
        if row["row_type"] == "candidate":
            review = reviews[row["vendor_or_candidate"]]
            expected = option_fields(context, "candidate", review)
            option = context["options"][review["candidate_id"]]
            subtotal = sum(Decimal(quotes[q]["values"]["quote_amount_twd"]) for q in option["component_quote_ids"])
            total = subtotal + sum(Decimal(v) for v in option["retained_allowances"].values())
            if Decimal(row["cost_twd"]) != total or row["cost_twd"] != row["planning_total_twd"]:
                raise ValueError("Published package cost does not match evidenced offers and allowances")
        elif row["row_type"] == "quote":
            expected = option_fields(context, "quote", quotes[row["quote_ids"]])
        elif row["row_type"] == "screening":
            expected = option_fields(context, "screening", screens[row["record_id"]])
        else:
            raise ValueError("Unknown comparison row kind")
        if any(row[key] != value for key, value in expected.items()):
            raise ValueError("Published option meaning, trade-off or approval differs from evidence")
        for key in ("tradeoffs", "unresolved"):
            values = json.loads(row[key])
            if type(values) is not list or not values or any(type(v) is not str or not v for v in values):
                raise ValueError("Comparison lists require explicit supported entries")
    for path in (paths[1], paths[3]):
        if re.search(r"\bTWD\s+-?\d+\.\d+", artifacts[path].decode("utf-8")):
            raise ValueError("Derived TWD prose must use whole-number amounts")
    calendar = Calendar.from_ical(artifacts[paths[2]])
    if str(calendar.get("VERSION")) != "2.0" or str(calendar.get("METHOD")) != "PUBLISH":
        raise ValueError("Published draft calendar requires VERSION:2.0 and METHOD:PUBLISH")
    for event in calendar.walk("VEVENT"):
        if (any(key not in event for key in ("UID", "DTSTAMP", "DTSTART"))
                or str(event.get("STATUS")) != "TENTATIVE" or event.get("ATTENDEE") is not None
                or event.get("ORGANIZER") is not None or event.subcomponents):
            raise ValueError("Calendar is not a tentative, non-delivery draft")
    communications = artifacts[paths[3]].decode("utf-8")
    for title, *_ in MESSAGES:
        heading = f"## {title} — UNSENT DRAFT\n"
        if communications.count(heading) != 1:
            raise ValueError("Every message must be explicitly labelled UNSENT DRAFT")
        section = communications.split(heading, 1)[1].split("\n## ", 1)[0]
        for key, value in message_fields(context, title).items():
            if f"- {key}: {value}\n" not in section:
                raise ValueError("Message audience, purpose, conditions or approval owner is unsupported")
