"""Stage 7 initial review model: comparisons, never selections or approvals."""

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import ctypes
import hashlib
import os
import stat
import sys
import json
from pathlib import Path
from uuid import uuid4

from event_coordination.sources import hash_bytes
from event_coordination.run_contract import read_predecessor, bound_run_id, bound_snapshot_id
from event_coordination.stages.feasibility import OUTPUT as PREDECESSOR_PATH

PREDECESSOR_ID = "44873e26-9404-4411-971f-e4f0a0ee0513"
PREDECESSOR_HASH = "sha256:57b5be2bde9d3c5a66316b2b1e0239a8c55e39de5ff54b859bf644fe74542fe1"
RUN_ID = "988f5ccf-4aeb-44d7-984d-777b1a2412e1"
BUSINESS_CLOCK = "2026-08-26T12:00:00+08:00"
OUTPUT = "deliverables/snapshots/07-decision-and-approval.json"
ANCESTOR_PATHS = (
    "deliverables/snapshots/01-scope-and-approval-gates.json",
    "deliverables/snapshots/02-source-capture.json",
    "deliverables/snapshots/03-constraint-model.json",
    "deliverables/snapshots/04-planning-baseline.json",
    "deliverables/snapshots/05-option-generation.json",
)
RECORD_ARRAYS = ("candidate_reviews", "tradeoffs", "approval_requirements",
                 "retained_early_screening", "ancestor_references", "review_policy")



INPUT_DIRECTORIES = ("interviews", "evidence", "deliverables/snapshots/evidence")
INPUT_FILES = ("snapshot.schema.json", *ANCESTOR_PATHS, PREDECESSOR_PATH)


def _identity(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid,
            st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _directory_identity(st):
    # Creating our output changes parent timestamps, but not identity/permissions.
    return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid)


def _parts(relative):
    if (not isinstance(relative, str) or relative.startswith("/") or "\\" in relative
            or any(p in ("", ".", "..") for p in relative.split("/"))):
        raise ValueError("Stage 7 requires canonical relative paths")
    return relative.split("/")


class _Directories:
    """Pin a canonical root and no-follow directory chain; never reopen aliases."""

    def __init__(self, root, parts):
        self.root = Path(root).absolute()
        self.parts = parts
        self.fds = []
        self.prefix_fds = []
        self.links = []

    def __enter__(self):
        try:
            if self.root.resolve(strict=True) != self.root:
                raise ValueError("Stage 7 project root must not contain symlink aliases")
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
            self.root_identity = _directory_identity(self.root.lstat())
            # Walk absolute root components too: O_NOFOLLOW on only the final
            # root component would still follow a raced symlink in its prefix.
            fd = os.open(self.root.anchor, flags)
            self.prefix_fds.append(fd)
            for part in self.root.parts[1:]:
                child = os.open(part, flags, dir_fd=fd)
                self.prefix_fds.append(child)
                self.links.append((fd, part, child, _directory_identity(os.fstat(child))))
                fd = child
            self.fds.append(self.prefix_fds.pop())
            for part in self.parts:
                child = os.open(part, flags, dir_fd=fd)
                self.fds.append(child)
                self.links.append((fd, part, child, _directory_identity(os.fstat(child))))
                fd = child
            self.verify()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def verify(self):
        if (_directory_identity(self.root.lstat()) != self.root_identity
                or _directory_identity(os.fstat(self.fds[0])) != self.root_identity):
            raise ValueError("Stage 7 project directory changed")
        for parent, name, child, identity in self.links:
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (_directory_identity(named) != identity
                    or _directory_identity(os.fstat(child)) != identity):
                raise ValueError("Stage 7 destination/input directory changed")

    def __exit__(self, *args):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds.clear()
        for fd in reversed(self.prefix_fds):
            os.close(fd)
        self.prefix_fds.clear()


def _protected_file(root, relative):
    parts = _parts(relative)
    with _Directories(root, parts[:-1]) as directories:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                     dir_fd=directories.fds[-1])
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("Stage 7 input must be a regular file")
            digest = hashlib.sha256()
            remaining = before.st_size
            while remaining:
                block = os.read(fd, min(65536, remaining))
                if not block:
                    raise ValueError("Stage 7 input changed during observation")
                digest.update(block)
                remaining -= len(block)
            after = os.fstat(fd)
            named = os.stat(parts[-1], dir_fd=directories.fds[-1], follow_symlinks=False)
            if _identity(before) != _identity(after) or _identity(after) != _identity(named):
                raise ValueError("Stage 7 input identity changed during observation")
            directories.verify()
            return ("file", _identity(after), "sha256:" + digest.hexdigest())
        finally:
            os.close(fd)


def _input_manifest(root):
    """Observe complete protected trees, including additions and unsafe entries."""
    result = {}
    def visit(relative):
        with _Directories(root, _parts(relative)) as directories:
            fd = directories.fds[-1]
            before = _identity(os.fstat(fd))
            names = sorted(os.listdir(fd))
            for name in names:
                child = relative + "/" + name
                entry = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(entry.st_mode):
                    visit(child)
                elif stat.S_ISREG(entry.st_mode):
                    result[child] = _protected_file(root, child)
                else:
                    raise ValueError("Stage 7 input trees must not contain links or special files")
            if before != _identity(os.fstat(fd)) or names != sorted(os.listdir(fd)):
                raise ValueError("Stage 7 input directory changed during observation")
            directories.verify()
            result[relative] = ("directory", before)
    for relative in INPUT_DIRECTORIES:
        visit(relative)
    for relative in INPUT_FILES:
        result[relative] = _protected_file(root, relative)
    return result


class _PinnedInputs:
    def __init__(self, root):
        self.root = root
        self.manifest = _input_manifest(root)

    def verify(self):
        if _input_manifest(self.root) != self.manifest:
            raise ValueError("Stage 7 protected inputs changed during evaluation")


def _exclusive_output(root_fd, relative):
    """Linux openat2 resolves the whole path beneath root, without symlinks.

    A leaf open against a previously pinned parent alone could write outside root
    if that parent was moved away. Do not fall back to that weaker operation.
    """
    _parts(relative)
    if sys.platform != "linux" or os.uname().machine != "x86_64":
        raise ValueError("Stage 7 exclusive writing requires Linux x86_64 openat2")
    class OpenHow(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("flags", "mode", "resolve")]
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    how = OpenHow(flags, 0o600, 0x08 | 0x04 | 0x02)  # BENEATH, NO_SYMLINKS, NO_MAGICLINKS
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    fd = libc.syscall(ctypes.c_long(437), ctypes.c_int(root_fd), ctypes.c_char_p(relative.encode()),
                      ctypes.byref(how), ctypes.c_size_t(ctypes.sizeof(how)))
    if fd < 0:
        raise OSError(ctypes.get_errno(), "Stage 7 safe exclusive output creation failed")
    return fd


def _strict_equal(actual, expected):
    """Supplement the permissive public schema, including Boolean type safety."""
    if type(actual) is not type(expected):
        raise ValueError("Stage 7 value has an unsupported type")
    if isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise ValueError("Stage 7 record structure differs from evidence")
        for key in expected:
            _strict_equal(actual[key], expected[key])
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError("Stage 7 records differ from evidence")
        for a, e in zip(actual, expected, strict=True):
            _strict_equal(a, e)
    elif actual != expected:
        raise ValueError("Stage 7 value differs from evidence or provisional review policy")


def _amount(value):
    if type(value) is not str:
        raise ValueError("Stage 7 quantities must preserve upstream decimal strings")
    result = Decimal(value)
    if not result.is_finite() or result < 0:
        raise ValueError("Stage 7 quantities must be finite and nonnegative")
    return result


def _recommendation_policy(reviews, checks):
    """Planner policy v1, applied only after upstream evidence validation.

    Capacity is an adequacy gate, not a fabricated forecast or safety buffer.
    Cost/headroom can break the tradeoff only with comparable hard dependencies
    and no additional unresolved requirement for the proposed candidate.
    """
    evaluations = []
    if len(reviews) != 2 or len({r['candidate_id'] for r in reviews}) != 2:
        raise ValueError('Recommendation requires two distinct verified candidates')
    for review in sorted(reviews, key=lambda r: r['candidate_id']):
        candidate_checks = [checks[i] for i in review['check_ids']]
        if not candidate_checks or len({c['requirement'] for c in candidate_checks}) != len(candidate_checks):
            raise ValueError('Recommendation checks are missing or duplicated')
        for c in candidate_checks:
            if (c['candidate_id'] != review['candidate_id'] or type(c['hard_requirement']) is not bool
                    or c['outcome'] not in ('pass', 'fail', 'conditional', 'unknown', 'not-applicable')):
                raise ValueError('Recommendation check identity/type/outcome is invalid')
        required = {'budget-ceiling', 'attendance-basis', 'capacity-catering', 'programme', 'safety'}
        if not required <= {c['requirement'] for c in candidate_checks}:
            raise ValueError('Recommendation lacks required assessment evidence')
        total = _amount(review['costs']['planning_total'])
        ceiling = _amount(review['budget_ceiling'])
        capacity = _amount(review['catering']['capacity'])
        demand = _amount(review['catering']['planning_demand'])
        headroom = ceiling - total
        if (headroom != Decimal(review['remaining_ceiling'])
                or capacity - demand != Decimal(review['catering']['margin'])):
            raise ValueError('Recommendation arithmetic is inconsistent')
        hard = [c for c in candidate_checks if c['hard_requirement'] and c['outcome'] != 'not-applicable']
        if not hard:
            raise ValueError('Recommendation lacks applicable hard checks')
        outcomes = {c['outcome'] for c in hard}
        classification = ('infeasible' if 'fail' in outcomes else 'unverified' if 'unknown' in outcomes
                          else 'conditional' if 'conditional' in outcomes else 'feasible')
        if classification != review['feasibility']:
            raise ValueError('Recommendation classification disagrees with hard checks')
        if (review['selected'] is not False or review['spending_authorized'] is not False
                or review['authorization_status'] != 'pending'):
            raise ValueError('Recommendation cannot ingest or grant authorization')
        condition_ids = {i for c in candidate_checks for i in c['condition_ids']}
        if condition_ids != set(review['condition_ids']):
            raise ValueError('Recommendation condition coverage is incomplete')
        reasons = []
        if classification not in ('feasible', 'conditional'):
            reasons.append('hard-checks-failed-or-unverified')
        if capacity < demand or demand <= 0:
            reasons.append('catering-demand-not-supported')
        if total > ceiling:
            reasons.append('overall-ceiling-exceeded')
        evaluations.append({
            'candidate_id': review['candidate_id'], 'eligible': not reasons,
            'ineligibility_reasons': reasons, 'feasibility': classification,
            'planning_total': str(total), 'budget_ceiling': str(ceiling),
            'remaining_ceiling': str(headroom), 'planning_demand': str(demand),
            'catering_capacity': str(capacity), 'catering_margin': str(capacity - demand),
            'hard_dependencies': sorted(c['requirement'] for c in hard if c['outcome'] != 'pass'),
            'unresolved_requirements': sorted(c['requirement'] for c in candidate_checks if c['condition_ids']),
            'condition_ids': sorted(condition_ids), 'check_ids': sorted(c['id'] for c in candidate_checks),
        })
    a, b = evaluations
    comparable = (all(r['eligible'] for r in evaluations)
                  and a['planning_demand'] == b['planning_demand']
                  and a['budget_ceiling'] == b['budget_ceiling']
                  and a['feasibility'] == b['feasibility']
                  and a['hard_dependencies'] == b['hard_dependencies'])
    preferred = []
    if comparable:
        for candidate, other in ((a, b), (b, a)):
            if (Decimal(candidate['planning_total']) < Decimal(other['planning_total'])
                    and Decimal(candidate['remaining_ceiling']) > Decimal(other['remaining_ceiling'])
                    and set(candidate['unresolved_requirements']) <= set(other['unresolved_requirements'])):
                preferred.append(candidate['candidate_id'])
    recommendation = preferred[0] if len(preferred) == 1 else None
    comparison = '; '.join(
        f"{r['candidate_id']}: {r['feasibility']}, planning cost TWD {r['planning_total']}, "
        f"budget headroom TWD {r['remaining_ceiling']}, catering capacity {r['catering_capacity']} "
        f"people for planning demand {r['planning_demand']} (nominal margin {r['catering_margin']})"
        for r in evaluations)
    capacity_delta = Decimal(a['catering_capacity']) - Decimal(b['catering_capacity'])
    if capacity_delta == 0:
        capacity_comparison = f"Catering capacities are equal at {a['catering_capacity']} people."
    else:
        larger, smaller = (a, b) if capacity_delta > 0 else (b, a)
        capacity_comparison = (f"{larger['candidate_id']} offers {abs(capacity_delta)} more catering places "
                               f"than {smaller['candidate_id']}.")
    if recommendation:
        winner = next(r for r in evaluations if r['candidate_id'] == recommendation)
        alternative = next(r for r in evaluations if r['candidate_id'] != recommendation)
        saving = Decimal(alternative['planning_total']) - Decimal(winner['planning_total'])
        extra_headroom = Decimal(winner['remaining_ceiling']) - Decimal(alternative['remaining_ceiling'])
        tradeoff = (f"{winner['candidate_id']} costs TWD {saving} less and leaves TWD {extra_headroom} "
                    f"more budget headroom than {alternative['candidate_id']}. {capacity_comparison}")
        rationale = (f"Provisionally recommend {recommendation} for human review. {comparison}. "
                     f"Both cover the stated demand with comparable hard dependencies and no additional "
                     f"unresolved requirement types for the recommended candidate. {tradeoff} "
                     "Capacity beyond the stated demand is a disclosed trade-off, not an invented "
                     "required buffer or attendance probability. This is not selection or authorization.")
    else:
        tradeoff = capacity_comparison
        rationale = (f"Defer: the evidence does not establish a unique candidate under the stated adequacy, "
                     f"dependency, uncertainty and headroom criteria. {comparison}. {tradeoff} "
                     "Human review of the tradeoff is required; no selection or authorization is inferred.")
    return {
        'policy_version': 'adequacy-then-headroom/1', 'basis': 'planner-policy-not-stakeholder-rule',
        'recommendation_status': 'provisional' if recommendation else 'deferred',
        'recommended_candidate_id': recommendation, 'evaluations': evaluations,
        'criteria': ['verified-hard-checks-and-capacity-adequacy', 'same-demand-ceiling-and-hard-dependencies',
                     'no-additional-unresolved-requirements', 'lower-cost-and-greater-headroom'],
        'rationale': rationale, 'tradeoff_summary': tradeoff,
        'limitations': ['Draft exercise recommendation only; conditional does not mean ready to book.',
                        'Capacity margin is nominal; forecast growth requires upstream reevaluation.',
                        'Local source copies and exercise confirmations are not live operational verification.'],
    }


def _inputs(root: Path) -> dict:
    from event_coordination.validation import validate_snapshot

    data = read_predecessor(root, PREDECESSOR_PATH, PREDECESSOR_HASH)
    predecessor_hash = hash_bytes(data)
    predecessor_id = bound_snapshot_id(root, PREDECESSOR_PATH, PREDECESSOR_ID)
    run_id = bound_run_id(root, RUN_ID)
    upstream = json.loads(data)
    if (upstream["snapshot_id"] != predecessor_id or upstream["run_id"] != run_id
            or upstream["state"]["business_clock"] != BUSINESS_CLOCK):
        raise ValueError("Stage 6 predecessor identity/run/clock mismatch")
    validate_snapshot(upstream, root)  # Includes original sources and the full chain.
    buffers = {PREDECESSOR_PATH: data}
    ancestors = []
    child = upstream
    for sequence, path in reversed(list(enumerate(ANCESTOR_PATHS, 1))):
        content = (root / path).read_bytes()
        parent = json.loads(content)
        if (child["predecessor"] != {"snapshot_id": parent["snapshot_id"], "path": path, "sha256": hash_bytes(content)}
                or parent["run_id"] != run_id or parent["sequence"] != sequence):
            raise ValueError("Stage 7 ancestor ownership/lineage mismatch")
        ancestors.append((parent, path, content))
        buffers[path] = content
        child = parent

    state = {key: [] for key in RECORD_ARRAYS}
    upstream_ids = set(upstream["produced_record_ids"])
    consumed = set(upstream_ids)
    unresolved = deepcopy(upstream["unresolved"])
    state["approval_requirements"] = deepcopy(upstream["state"]["approval_requirements"])
    state["retained_early_screening"] = deepcopy(upstream["state"]["retained_early_screening"])
    # These carried records keep their original evidence IDs. Declare actual
    # ancestor ownership rather than relabelling Stage 2 observations as Stage 6.
    needed = {e for r in unresolved + state["approval_requirements"] + state["retained_early_screening"] for e in r["evidence_ids"]} - upstream_ids
    for identifier in sorted(needed):
        owner = next(((s, p, b) for s, p, b in ancestors if identifier in s["produced_record_ids"]), None)
        if owner is None:
            raise ValueError("Stage 7 inherited reference has no verified ancestor")
        snapshot, path, content = owner
        state["ancestor_references"].append({
            "id": "decision-ancestor-" + identifier,
            "summary": "Verified historical record ownership; source verification is not upgraded.",
            "evidence_ids": [identifier], "record_id": identifier,
            "snapshot_id": snapshot["snapshot_id"], "snapshot_path": path,
            "snapshot_sha256": hash_bytes(content), "stage": snapshot["stage"],
            "run_id": snapshot["run_id"], "verification": "inherits-upstream-limitations",
        })
        consumed.add(identifier)

    checks = {r["id"]: r for r in upstream["state"]["checks"]}
    results = upstream["state"]["option_results"]
    from event_coordination.run_contract import current_run
    fresh = current_run(root) is not None
    if len(results) != 2 or (not fresh and len(unresolved) != 88) or len(state["approval_requirements"]) != 5:
        raise ValueError("Stage 7 requires the approved two-candidate review basis")
    if any(g["status"] != "pending" for g in state["approval_requirements"]):
        raise ValueError("Initial Stage 7 has no evidence granting approval")

    def add(category, identifier, summary, evidence, **extra):
        if not evidence or not set(evidence) <= upstream_ids:
            raise ValueError("New Stage 7 evidence must resolve to Stage 6 produced records")
        record = {"id": identifier, "summary": summary, "evidence_ids": list(dict.fromkeys(evidence)), **extra}
        state[category].append(record)
        return record

    for result in results:
        if (result["selected"] is not False or result["feasibility"] not in (
                ("feasible", "conditional", "infeasible", "unverified") if fresh else ("conditional",))):
            raise ValueError("Approved Stage 6 candidates must remain conditional and unselected")
        name = result["id"].removeprefix("result-oct17-")
        prefix = "check-oct17-" + name + "-"
        def check(suffix):
            c = checks[prefix + suffix]
            if c["id"] not in result["check_ids"] or c["candidate_id"] != result["candidate_id"]:
                raise ValueError("Stage 7 check belongs to a different candidate")
            return c
        costs = deepcopy(result["reconstructed_costs"])
        subtotal = sum((_amount(v) for v in costs["quoted_by_category"].values()), Decimal(0))
        total = subtotal + sum((_amount(v) for v in costs["retained_allowances"].values()), Decimal(0))
        if subtotal != _amount(costs["quoted_subtotal"]) or total != _amount(costs["planning_total"]):
            raise ValueError("Stage 7 cost arithmetic is inconsistent")
        ceiling = _amount(check("budget-ceiling")["inputs"]["ceiling"])
        catering = check("capacity-catering")["inputs"]
        capacity, demand = _amount(catering["capacity"]), _amount(catering["applicable_demand"])
        categories = {c["requirement"].removeprefix("category-"): deepcopy(c["inputs"])
                      for c in (checks[i] for i in result["check_ids"]) if c["requirement"].startswith("category-")}
        add("candidate_reviews", "decision-review-oct17-" + name,
            (f"{result['feasibility'].capitalize()} exercise candidate for draft comparison; no selection or authorization." if fresh else
             "Conditional exercise candidate for draft comparison; no selection or authorization."),
            [result["id"], *result["check_ids"], result["schedule_witness_id"],
             *result["applicable_condition_ids"], *result["approval_requirement_ids"]],
            candidate_id=result["candidate_id"], source_result_id=result["id"],
            feasibility=result["feasibility"], assessment_scope=result["assessment_scope"],
            check_ids=deepcopy(result["check_ids"]), blocking_check_ids=deepcopy(result["blocking_check_ids"]),
            condition_ids=deepcopy(result["applicable_condition_ids"]),
            schedule_witness_id=result["schedule_witness_id"], costs=costs,
            budget_ceiling=str(ceiling), remaining_ceiling=str(ceiling - total), currency="TWD",
            catering={"capacity": catering["capacity"], "planning_demand": catering["applicable_demand"],
                      "margin": str(capacity - demand), "unit": "people", "meaning": "catering service capacity; forecast is not confirmed attendance"},
            category_budget=categories, selected=False, spending_authorized=False,
            authorization_status="pending", live_operational_verification="not-established",
            approval_requirement_ids=deepcopy(result["approval_requirement_ids"]))

    evidence = [r["id"] for r in results]
    values = state["candidate_reviews"]
    add("tradeoffs", "tradeoff-cost-and-headroom", "Lower proposed cost leaves more overall ceiling headroom; it does not confer spending authority.",
        evidence + [c["id"] for c in checks.values() if c["requirement"] in ("quote-subtotal", "planning-total", "budget-ceiling")],
        basis="derived", currency="TWD", candidates=[{"candidate_id": r["candidate_id"], "quoted_subtotal": r["costs"]["quoted_subtotal"],
        "planning_total": r["costs"]["planning_total"], "remaining_ceiling": r["remaining_ceiling"]} for r in values],
        calculation="sum quoted categories + retained communications and contingency; ceiling minus planning total")
    add("tradeoffs", "tradeoff-catering-capacity",
        ("Compare each evidenced catering margin and cost independently; both use the same uncertain population without adding overlapping needs." if fresh else
         "Larger nominal catering margin costs more; both use the same uncertain planning population without adding overlapping needs."),
        evidence + [c["id"] for c in checks.values() if c["requirement"] in ("capacity-catering", "attendance-basis")],
        basis="derived", candidates=[{"candidate_id": r["candidate_id"], **r["catering"]} for r in values],
        calculation="catering service capacity minus planning demand; not extra audience seating")
    add("tradeoffs", "tradeoff-category-allocation-review",
        ("Allocations, approval limits, recorded commitments and spending permission remain separate; positive allocation variances require review."
         if fresh and any(Decimal(c["recorded_commitment"]) != 0 for r in values for c in r["category_budget"].values()) else
         "Allocations, approval limits, zero recorded commitments and spending permission remain separate; positive allocation variances require review."),
        evidence + [c["id"] for c in checks.values() if c["requirement"].startswith(("category-", "allocation-policy-"))] + ["gate-spending"],
        basis="derived", candidates=[{"candidate_id": r["candidate_id"], "category_budget": r["category_budget"]} for r in values],
        allocation_transfer_policy="unresolved", spending_authorized=False)
    add("tradeoffs", "tradeoff-conditions-and-screened-alternatives", "Neither candidate removes the shared venue prerequisite, evidence limitations or pending approvals; retain screened alternatives without invented remedies.",
        evidence + [r["id"] for r in upstream["state"]["unresolved_conditions"]]
        + [r["id"] for r in state["retained_early_screening"]] + [r["id"] for r in upstream["state"]["screening_checks"]],
        basis="evidence-summary", condition_ids=[r["id"] for r in unresolved],
        early_screening_ids=[r["id"] for r in state["retained_early_screening"]])
    policy = _recommendation_policy(values, checks)
    add("review_policy", "decision-policy-initial-review", "Provisional planner recommendation or explicit deferral; never a learner decision or approval.",
        evidence + list(checks) + [r["id"] for r in state["approval_requirements"]] + ["policy-stage6-aggregation"],
        **policy, approval_evidence_required=True, external_actions_authorized=False)
    state.update(recommendation=policy['recommended_candidate_id'], learner_decisions=[], business_clock=BUSINESS_CLOCK,
                 business_timezone="Asia/Taipei", output_status="draft", audience="internal-evidence-review",
                 inherited_unresolved_ids=[r["id"] for r in unresolved])
    records = [r for key in RECORD_ARRAYS for r in state[key]] + unresolved
    ids = [r["id"] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Stage 7 produced IDs must be unique")
    allowed = upstream_ids | set(ids) | needed
    if any(e not in allowed for r in records for e in r["evidence_ids"]):
        raise ValueError("Stage 7 record evidence does not resolve")
    for path, content in buffers.items():
        if (root / path).read_bytes() != content:
            raise ValueError("Stage 7 pinned inputs changed during evaluation")
    return {"run_id": run_id, "predecessor": {"snapshot_id": predecessor_id, "path": PREDECESSOR_PATH, "sha256": predecessor_hash},
            "consumed_record_ids": sorted(consumed), "produced_record_ids": ids, "state": state,
            "unresolved": unresolved, "status": "partial", "decisions": []}


def build_snapshot(root: Path) -> dict:
    """Construct and validate in memory; no source retrieval or filesystem writes."""
    from event_coordination.validation import validate_snapshot
    pinned = _PinnedInputs(root)
    snapshot = {"schema_version": "event-coordination-stage-snapshot/2", "snapshot_id": str(uuid4()),
                "stage": "decision-and-approval", "sequence": 7,
                "created_at": datetime.now(timezone.utc).isoformat(), **_inputs(root)}
    validate_snapshot(snapshot, root)
    pinned.verify()  # Includes mutations made just after semantic validation returns.
    return snapshot


def validate_stage7(snapshot: dict, root: Path) -> None:
    """Revalidate every input through the end of semantic/schema checking."""
    pinned = _PinnedInputs(root)
    from jsonschema import Draft202012Validator, FormatChecker
    schema = json.loads((root / "snapshot.schema.json").read_bytes())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(snapshot)
    _validate_stage7_contents(snapshot, root)
    pinned.verify()


def _validate_stage7_contents(snapshot: dict, root: Path) -> None:
    """Reconstruct comparisons and provisional policy from verified evidence.

    Approval/decision arrays are checked separately by exact reconstruction; the
    recommended candidate never changes selection, feasibility or authority.
    """
    from jsonschema import Draft202012Validator, FormatChecker
    expected = _inputs(root)
    envelope = {"schema_version", "snapshot_id", "stage", "sequence", "created_at"}
    if snapshot.keys() != expected.keys() | envelope or type(snapshot["sequence"]) is not int:
        raise ValueError("Unsupported Stage 7 envelope")
    for key, value in expected.items():
        _strict_equal(snapshot.get(key), value)
    ancestor_ids = {json.loads((root / p).read_bytes())["snapshot_id"] for p in (*ANCESTOR_PATHS, PREDECESSOR_PATH)}
    if snapshot["snapshot_id"] in ancestor_ids:
        raise ValueError("Stage 7 requires a distinct snapshot ID")
    created = datetime.fromisoformat(snapshot["created_at"])
    if created.utcoffset() != timezone.utc.utcoffset(created) or created == datetime.fromisoformat(BUSINESS_CLOCK):
        raise ValueError("Stage 7 requires an actual UTC execution timestamp, separate from the business clock")
    schema = json.loads((root / "snapshot.schema.json").read_bytes())
    validator = Draft202012Validator({"$ref": "#/$defs/record", "$defs": schema["$defs"]}, format_checker=FormatChecker())
    for key in RECORD_ARRAYS:
        for record in snapshot["state"][key]:
            validator.validate(record)


def write_snapshot(root: Path) -> tuple[Path, str]:
    """No-follow exclusive writer, for a separately authorized generation step.

    Stage 6's existing destination parents are required. No parent creation or
    unsafe-platform fallback is performed. Output bytes are read through the same
    descriptor used to create them, not a reopened pathname.
    """
    from event_coordination.validation import validate_snapshot
    parts = _parts(OUTPUT)
    with _Directories(root, parts[:-1]) as directories:
        try:
            os.stat(parts[-1], dir_fd=directories.fds[-1], follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(root / OUTPUT)
        pinned = _PinnedInputs(root)
        snapshot = build_snapshot(root)
        content = (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        pinned.verify()
        directories.verify()
        # Resolve from ROOT again in one constrained kernel lookup, protecting
        # against a swap after the preceding directory identity observation.
        fd = _exclusive_output(directories.fds[0], OUTPUT)
        try:
            def check_output():
                directories.verify()
                current = os.fstat(fd)
                named = os.stat(parts[-1], dir_fd=directories.fds[-1], follow_symlinks=False)
                if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1
                        or _identity(current) != _identity(named)):
                    raise ValueError("Stage 7 output identity changed")
                return _identity(current)
            check_output()
            pending = memoryview(content)
            while pending:
                count = os.write(fd, pending)
                if count <= 0:
                    raise ValueError("Stage 7 output write failed")
                pending = pending[count:]
            identity = check_output()
            os.lseek(fd, 0, os.SEEK_SET)
            chunks = []
            remaining = len(content) + 1
            while remaining:
                block = os.read(fd, min(65536, remaining))
                if not block:
                    break
                chunks.append(block)
                remaining -= len(block)
            saved = b"".join(chunks)
            if saved != content or identity != check_output():
                raise ValueError("Saved Stage 7 bytes changed")
            validate_snapshot(json.loads(saved), root)
            pinned.verify()
            if identity != check_output():
                raise ValueError("Stage 7 output changed during validation")
            return root / OUTPUT, hash_bytes(saved)
        finally:
            os.close(fd)
