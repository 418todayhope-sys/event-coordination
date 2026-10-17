"""Stage 8 Part 1 tests: temporary evidence copies, no real deliverables."""

from copy import deepcopy
import csv
from datetime import datetime, timezone
from decimal import Decimal
import io
import json
from pathlib import Path
import shutil

from icalendar import Calendar
from jsonschema import ValidationError
import pytest

from event_coordination.sources import hash_bytes
from event_coordination.stages import drafts
from event_coordination.validation import validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_external_actions(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Draft foundation cannot execute or contact anyone")
    monkeypatch.setattr("socket.socket.connect", deny)
    monkeypatch.setattr("subprocess.Popen", deny)


@pytest.fixture(scope="module")
def basis(tmp_path_factory):
    root = tmp_path_factory.mktemp("stage8-preserved-inputs")
    for directory in ("interviews", "evidence"):
        shutil.copytree(ROOT / directory, root / directory)
    shutil.copyfile(ROOT / "snapshot.schema.json", root / "snapshot.schema.json")
    (root / "deliverables/snapshots").mkdir(parents=True)
    shutil.copytree(ROOT / "deliverables/snapshots/evidence", root / "deliverables/snapshots/evidence")
    for relative in (*drafts.ANCESTOR_PATHS, drafts.PREDECESSOR_PATH):
        shutil.copyfile(ROOT / relative, root / relative)
    return root


@pytest.fixture(scope="module")
def context(basis):
    return drafts._context(basis)


@pytest.fixture(scope="module")
def model(basis):
    return drafts.build_snapshot(basis)


@pytest.fixture
def project(basis, tmp_path):
    shutil.copytree(basis, tmp_path, dirs_exist_ok=True)
    return tmp_path


def file_hashes(root):
    return {str(p.relative_to(root)): hash_bytes(p.read_bytes()) for p in root.rglob('*') if p.is_file()}


def test_valid_model_is_memory_only(basis, model):
    before = file_hashes(basis)
    validate_snapshot(model, basis)
    assert file_hashes(basis) == before
    assert model['sequence'] == 8 and model['status'] == 'partial'
    assert model['run_id'] == drafts.RUN_ID
    assert model['predecessor'] == {'snapshot_id': drafts.PREDECESSOR_ID, 'path': drafts.PREDECESSOR_PATH, 'sha256': drafts.PREDECESSOR_HASH}
    assert all(not (basis / p).exists() for p in (*drafts.ARTIFACT_PATHS, drafts.OUTPUT))
    upstream = json.loads((basis / drafts.PREDECESSOR_PATH).read_bytes())
    assert model['unresolved'] == upstream['unresolved'] and len(model['unresolved']) == 88
    for key, size in [('approval_requirements', 5), ('retained_early_screening', 4)]:
        assert model['state'][key] == upstream['state'][key] and len(model['state'][key]) == size
    assert model['state']['recommendation'] == 'option-oct17-green-table'
    assert model['state']['learner_decisions'] == model['decisions'] == []
    assert model['state']['external_actions_authorized'] is False
    artifacts = drafts.rendered_bytes(model)
    for record in model['state']['artifact_drafts']:
        assert hash_bytes(artifacts[record['path']]) == record['sha256']
        assert record['hash_scope'] == 'rendered-in-memory-bytes'
        assert record['validation_status'] == 'not-produced'
        assert record['render_validation_status'] == 'valid'
        assert record['saved_file_verified'] is False and record['selected'] is False


def test_renderers_are_deterministic(context, model):
    expected = drafts.rendered_bytes(model)
    assert drafts.render_artifacts(context, model['created_at']) == expected
    assert drafts.render_artifacts(deepcopy(context), model['created_at']) == expected


def test_bundle_api_has_no_writes(project):
    before = file_hashes(project)
    snapshot, artifacts = drafts.build_bundle(project)
    drafts.validate_bundle(snapshot, artifacts, project)
    assert set(artifacts) == set(drafts.ARTIFACT_PATHS)
    assert file_hashes(project) == before


def test_csv_preserves_quotes_and_separates_package_arithmetic(context, model):
    rows = list(csv.DictReader(io.StringIO(drafts.rendered_bytes(model)[drafts.ARTIFACT_PATHS[0]].decode())))
    quotes = [r for r in rows if r['row_type'] == 'quote']
    assert {r['quote_ids'] for r in quotes} == {f'Q-{i:03d}' for i in range(1, 11)}
    original = {r['values']['quote_id']: r for r in context['quotes']}
    for r in quotes:
        q = original[r['quote_ids']]
        assert Decimal(r['quoted_amount_twd']) == Decimal(q['values']['quote_amount_twd'])
        assert r['source_locator'] == q['source_observation']['locator']['value']
        assert r['source_sha256'] == q['source_fact']['provenance'][0]['sha256']
        assert r['source_status'] == q['values']['status']
        assert r['capacity_meaning'] == q['capacity']['interpretation']
        assert r['valid_until'] == q['values']['valid_until']
    candidates = [r for r in rows if r['row_type'] == 'candidate']
    assert [(Decimal(r['quoted_amount_twd']), Decimal(r['allowances_twd']), Decimal(r['planning_total_twd'])) for r in candidates] == [(Decimal(429000), Decimal(65000), Decimal(494000)), (Decimal(447000), Decimal(65000), Decimal(512000))]
    assert len([r for r in rows if r['row_type'] == 'screening']) == 4


def test_plan_budget_headcount_and_privacy(model, context):
    plan = drafts.rendered_bytes(model)[drafts.ARTIFACT_PATHS[1]].decode()
    assert 'Registered people: 180.0' in plan and 'Required onsite personnel: 30.0' in plan
    assert 'Forecast walk-ins (uncertain): 35.0' in plan and '245.0' in plan
    assert 'planned allocations: TWD 510000.0' in plan and 'Overall ceiling: TWD 520000' in plan
    assert 'spending authorization' in plan and 'security variance' in plan and 'catering variance' in plan
    # Private attendee source fields are deliberately outside all renderer selections.
    modified = deepcopy(context)
    for identifier, record in modified['baseline'].items():
        if identifier.startswith('baseline-needs-'):
            record['values'] = {'private': 'SYNTHETIC-MEDICAL-DETAIL person@example.invalid'}
    for payload in drafts.render_artifacts(modified, model['created_at']).values():
        assert b'SYNTHETIC-MEDICAL-DETAIL' not in payload and b'person@example.invalid' not in payload
    assert '4F Floor Plan' in plan and 'Page 1' in plan


def test_calendar_exact_witness_times_and_tentative_behavior(model, context):
    calendar = Calendar.from_ical(drafts.rendered_bytes(model)[drafts.ARTIFACT_PATHS[2]])
    assert calendar.get('METHOD') is None and len(calendar.walk('VTIMEZONE')) == 1
    events = calendar.walk('VEVENT')
    expected = drafts._calendar_entries(context)
    assert len(events) == len(expected)
    assert len({str(e['UID']) for e in events}) == len(events)
    actual_stamp = datetime.fromisoformat(model['created_at']).replace(microsecond=0)
    for event, (_, label, start, end, lane, evidence) in zip(events, expected, strict=True):
        assert event.decoded('DTSTART') == datetime.fromisoformat(start)
        if start != end: assert event.decoded('DTEND') == datetime.fromisoformat(end)
        else: assert event.get('DTEND') is None and event.get('DURATION') is None
        assert event.decoded('DTSTAMP') == actual_stamp
        assert str(event['STATUS']) == 'TENTATIVE' and str(event['TRANSP']) == 'TRANSPARENT'
        assert event.get('ATTENDEE') is None and event.get('ORGANIZER') is None
        assert not event.subcomponents
        assert str(event['X-RESOURCE-LANE']) == lane and str(event['X-EVIDENCE-ID']) == evidence
    assert sum(str(e['SUMMARY']) == 'DRAFT: demo' for e in events) == 12
    assert sum(str(e['SUMMARY']) == 'DRAFT: changeover' for e in events) == 12
    assert sum((e.decoded('DTEND')-e.decoded('DTSTART')).total_seconds() for e in events if str(e['SUMMARY']) in ('DRAFT: demo', 'DRAFT: changeover')) == 156*60
    programme = [e for e in events if str(e['X-RESOURCE-LANE']) == 'programme']
    for left, right in zip(programme, programme[1:]): assert left.decoded('DTEND') <= right.decoded('DTSTART')


def test_communications_are_unsent_and_do_not_invent_recipients(model):
    content = drafts.rendered_bytes(model)[drafts.ARTIFACT_PATHS[3]].decode()
    assert content.count('UNSENT') == 5
    assert '@' not in content and 'not verified recipients' in content
    assert 'not an order, acceptance, booking or payment authorization' in content
    assert 'Programme gate applies only to roster/duration changes' in content
    assert 'no accommodation is guaranteed' in content


def test_dependencies_have_actual_owners_and_resolvable_targets(basis, model):
    upstream = json.loads((basis / drafts.PREDECESSOR_PATH).read_bytes())
    upstream_ids = set(upstream['produced_record_ids'])
    ancestor_ids = set()
    for ref in model['state']['ancestor_references']:
        content = (basis / ref['snapshot_path']).read_bytes();s = json.loads(content)
        assert hash_bytes(content) == ref['snapshot_sha256']
        assert s['snapshot_id'] == ref['snapshot_id'] and s['stage'] == ref['stage']
        assert ref['record_id'] in s['produced_record_ids']
        ancestor_ids.add(ref['record_id'])
    assert set(model['consumed_record_ids']) == upstream_ids | ancestor_ids
    records = [r for key in drafts.RECORD_ARRAYS for r in model['state'][key]] + model['unresolved']
    ids = [r['id'] for r in records]
    assert model['produced_record_ids'] == ids and len(ids) == len(set(ids))
    assert all(set(r['evidence_ids']) <= upstream_ids | ancestor_ids | set(ids) for r in records)
    refs = {r['record_id']: r for r in model['state']['ancestor_references']}
    assert refs['witness-oct17-green-table']['stage'] == 'feasibility-testing'
    assert refs['option-source-Q-003']['stage'] == 'option-generation'
    impacts = drafts.affected_targets(model, ['obs-quote-q-003'])
    assert {artifact for artifact, _ in impacts} == set(drafts.ARTIFACT_IDS)
    assert ('draft-vendor-comparison', 'row-Q-003') in impacts
    assert any(artifact == 'draft-event-calendar' and locator.startswith('uid-') for artifact, locator in impacts)


@pytest.mark.parametrize('bad', [[], ['unknown'], [True], 'obs-quote-q-003'])
def test_unknown_change_scope_rejected(model, bad):
    with pytest.raises(ValueError): drafts.affected_targets(model, bad)


@pytest.mark.parametrize('mutation', ['hash', 'content', 'path', 'saved', 'saved-number', 'status', 'approval',
    'recommendation', 'decisions', 'gate', 'unresolved', 'screen', 'dependency', 'ancestor', 'consumed',
    'produced', 'clock', 'sequence', 'external', 'extra-field', 'timestamp', 'snapshot-id', 'byte-length'])
def test_snapshot_mutations_fail_closed(basis, model, mutation):
    s = deepcopy(model);state = s['state'];r = state['artifact_drafts'][0]
    if mutation == 'hash': r['sha256'] = 'sha256:' + '0'*64
    elif mutation == 'content': r['rendered_text'] += '\nApproved'
    elif mutation == 'path': r['path'] = '../outside.csv'
    elif mutation == 'saved': r['saved_file_verified'] = True
    elif mutation == 'saved-number': r['saved_file_verified'] = 0
    elif mutation == 'status': r['validation_status'] = 'valid'
    elif mutation == 'approval': state['approval_requirements'][0]['status'] = 'approved'
    elif mutation == 'recommendation': state['recommendation'] = 'option-oct17-city-pantry'
    elif mutation == 'decisions': state['learner_decisions'] = [{'id':'forged'}]
    elif mutation == 'gate': state['approval_requirements'].pop()
    elif mutation == 'unresolved': s['unresolved'].pop()
    elif mutation == 'screen': state['retained_early_screening'].pop()
    elif mutation == 'dependency': state['affected_dependencies'][0]['source_record_ids'] = []
    elif mutation == 'ancestor': state['ancestor_references'][0]['snapshot_sha256'] = 'sha256:' + '0'*64
    elif mutation == 'consumed': s['consumed_record_ids'].pop()
    elif mutation == 'produced': s['produced_record_ids'].pop()
    elif mutation == 'clock': state['business_clock'] = s['created_at']
    elif mutation == 'sequence': s['sequence'] = 8.0
    elif mutation == 'external': state['external_actions_authorized'] = True
    elif mutation == 'extra-field': s['approved'] = True
    elif mutation == 'timestamp': s['created_at'] = drafts.BUSINESS_CLOCK
    elif mutation == 'snapshot-id': s['snapshot_id'] = drafts.PREDECESSOR_ID
    else: r['byte_length'] += 1
    with pytest.raises((ValueError, ValidationError)):
        validate_snapshot(s, basis)


def test_rehashed_unsupported_content_is_rejected(basis, model):
    snapshot = deepcopy(model)
    r = snapshot['state']['artifact_drafts'][1]
    r['rendered_text'] += '\nBooked and approved.\n'
    payload = r['rendered_text'].encode();r['sha256'] = hash_bytes(payload);r['byte_length'] = len(payload)
    with pytest.raises(ValueError): validate_snapshot(snapshot, basis)


def test_mismatched_bundle_bytes_rejected(basis, model):
    artifacts = drafts.rendered_bytes(model)
    artifacts[drafts.ARTIFACT_PATHS[0]] += b'forged'
    with pytest.raises(ValueError): drafts.validate_bundle(model, artifacts, basis)


@pytest.mark.parametrize('relative', ['snapshot.schema.json', drafts.PREDECESSOR_PATH,
    drafts.ANCESTOR_PATHS[0], 'interviews/project-c-event-coordination-20261016-2056.md',
    'evidence/originals/Project C — Vendor Quotes.xlsx',
    'deliverables/snapshots/evidence/f1710485827023.pdf'])
def test_changed_protected_input_rejected(project, relative):
    p = project / relative;p.write_bytes(p.read_bytes() + b'\n')
    with pytest.raises((ValueError, ValidationError)): drafts.build_snapshot(project)


@pytest.mark.parametrize('target', [*drafts.ARTIFACT_PATHS, drafts.OUTPUT])
@pytest.mark.parametrize('kind', ['file', 'directory', 'dangling-link'])
def test_output_collision_is_refused_without_writes(project, target, kind):
    p = project / target
    if kind == 'file': p.write_bytes(b'existing')
    elif kind == 'directory': p.mkdir()
    else: p.symlink_to(project / 'missing')
    before = file_hashes(project) if kind != 'dangling-link' else None
    with pytest.raises(FileExistsError): drafts.build_snapshot(project)
    if before is not None: assert file_hashes(project) == before
    else: assert p.is_symlink()


def test_parent_symlink_refused(project):
    p = project / 'deliverables';outside = project.parent / ('outside-' + project.name)
    p.rename(outside);p.symlink_to(outside, target_is_directory=True)
    with pytest.raises((ValueError, OSError)): drafts.build_snapshot(project)
    assert not list(outside.glob('*.csv'))


@pytest.mark.parametrize('relative', [drafts.PREDECESSOR_PATH, 'evidence/originals/Project C — Vendor Quotes.xlsx',
    'interviews/project-c-event-coordination-20261016-2056.md', 'snapshot.schema.json'])
def test_late_input_mutation_before_return_rejected(project, monkeypatch, relative):
    original = drafts.validate_stage8
    def validate(snapshot, root):
        original(snapshot, root)
        p = root / relative;p.write_bytes(p.read_bytes() + b'\n')
    monkeypatch.setattr(drafts, 'validate_stage8', validate)
    with pytest.raises(ValueError): drafts.build_snapshot(project)


def test_late_output_collision_rejected(project, monkeypatch):
    original = drafts.validate_stage8
    def validate(snapshot, root):
        original(snapshot, root)
        (root / drafts.ARTIFACT_PATHS[0]).mkdir()
    monkeypatch.setattr(drafts, 'validate_stage8', validate)
    with pytest.raises(FileExistsError): drafts.build_snapshot(project)


@pytest.mark.parametrize('text', ['=SUM(A1:A2)', '+cmd', '-cmd', '@cmd', '  =cmd', '\tcmd', '\r\ncmd'])
def test_csv_formula_guard(text):
    assert drafts._csv_cell(text) == "'" + text
    assert drafts._csv_cell('Green Table') == 'Green Table'


def test_markdown_escapes_untrusted_markup():
    assert '<script>' not in drafts._md('<script>|\nunsafe')
    assert '\\|' in drafts._md('|') and '\n' not in drafts._md('a\nb')


def _source_quote_cells(basis):
    # Read the preserved workbook through a separate extraction path, not renderer context.
    from event_coordination.constraint_sources import workbook_rows
    captured = json.loads((basis / drafts.ANCESTOR_PATHS[1]).read_bytes())
    source = next(r for r in captured['state']['sources'] if r['source_identity'] == 'vendor-register')
    rows = workbook_rows(basis, source, 'Vendor Quotes')
    cells = [{key.rstrip('0123456789'): value for key, value in r['values'].items()} for r in rows[1:]]
    return {r['A']: r for r in cells}


def test_csv_explicit_fictional_provenance_and_untouched_source_notes(basis, model):
    rows = list(csv.DictReader(io.StringIO(drafts.rendered_bytes(model)[drafts.ARTIFACT_PATHS[0]].decode())))
    source = _source_quote_cells(basis)
    for row in rows:
        if row['row_type'] in ('quote', 'candidate'):
            assert row['provenance_classification'] == 'fictional exercise evidence'
            assert row['real_world_availability'] == 'unverified; exercise availability is not live vendor confirmation'
        if row['row_type'] == 'quote':
            assert row['conditions'] == source[row['quote_ids']]['J']


@pytest.mark.parametrize('candidate,catering,subtotal,total', [
    ('option-oct17-green-table', 'Q-003', '429000', '494000'),
    ('option-oct17-city-pantry', 'Q-004', '447000', '512000'),
])
def test_csv_candidate_membership_dates_and_independent_workbook_totals(basis, model, candidate, catering, subtotal, total):
    rows = list(csv.DictReader(io.StringIO(drafts.rendered_bytes(model)[drafts.ARTIFACT_PATHS[0]].decode())))
    row = next(r for r in rows if r['row_type'] == 'candidate' and r['vendor_or_candidate'] == candidate)
    expected = ['Q-001', catering, 'Q-005', 'Q-006', 'Q-009', 'Q-010']
    assert row['quote_ids'].split(';') == expected
    source = _source_quote_cells(basis)
    assert row['service_date'] == '2026-10-17'
    assert all(source[q]['G'] == row['service_date'] for q in expected)
    amount = sum(Decimal(source[q]['E']) for q in expected)
    assert amount == Decimal(subtotal) == Decimal(row['quoted_amount_twd'])
    assert amount + Decimal('25000') + Decimal('40000') == Decimal(total) == Decimal(row['planning_total_twd'])


@pytest.mark.parametrize('candidate', ['option-oct17-green-table', 'option-oct17-city-pantry'])
def test_plan_has_evidence_linked_candidate_hard_coverage_without_private_inputs(basis, model, candidate):
    plan = drafts.rendered_bytes(model)[drafts.ARTIFACT_PATHS[1]].decode()
    assert 'Proposed quiet room: V.I.P. Room' in plan
    assert 'not a confirmed operational arrangement' in plan
    assert '[baseline-accessibility-space-limits; option-source-Q-001]' in plan
    section = plan.split('### ' + candidate + '\n', 1)[1].split('\n### ', 1)[0].split('## Registered floor-plan', 1)[0]
    saved = json.loads((basis / drafts.ANCESTOR_PATHS[5]).read_bytes())
    checks = [r for r in saved['state']['checks'] if r['candidate_id'] == candidate and r['hard_requirement'] is True]
    table = [line.split(' | ') for line in section.splitlines() if line.startswith('| ') and not line.startswith('| Requirement')]
    assert len(table) == len(checks)
    for check, cells in zip(checks, table, strict=True):
        assert cells[0] == '| ' + check['requirement']
        assert cells[1]  # Actual proposed scope, not just an outcome.
        assert cells[2] == check['outcome']
        assert check['id'] in cells[5]
        assert all(identifier in cells[5] for identifier in check['evidence_ids'])
        assert all(condition in cells[3] for condition in check['condition_ids'])
        assert 'not live operational verification' in cells[4]
    assert 'Q-005 live captions and transcript' in section
    assert 'Q-006 AV package with hearing loop' in section
    assert 'Q-009 security and first-aid staffing' in section
    assert 'Venue confirmation required before CAL-006' in section
    # No raw attendee requests, identifiers from their fields, or private inputs are serialized.
    assert 'severe_allergy_follow_up' not in plan and 'relevant_needs' not in plan
    assert 'These are preserved Stage 6 fictional-exercise assessments, not fulfillment or approvals.' in plan
