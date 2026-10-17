"""Stage 7 tests use temporary evidence copies; no business decisions or retrieval."""

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import shutil

from jsonschema import ValidationError
import pytest

from event_coordination.sources import hash_bytes
from event_coordination.stages import decisions
from event_coordination.validation import validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_external_actions(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Stage 7 must not retrieve sources or execute commands")
    monkeypatch.setattr("socket.socket.connect", deny)
    monkeypatch.setattr("subprocess.Popen", deny)


@pytest.fixture(scope="module")
def basis(tmp_path_factory):
    root = tmp_path_factory.mktemp("stage7-preserved-basis")
    for directory in ("interviews", "evidence"):
        shutil.copytree(ROOT / directory, root / directory)
    shutil.copyfile(ROOT / "snapshot.schema.json", root / "snapshot.schema.json")
    dest = root / "deliverables/snapshots"; dest.mkdir(parents=True)
    shutil.copytree(ROOT / "deliverables/snapshots/evidence", dest / "evidence")
    for path in (*decisions.ANCESTOR_PATHS, decisions.PREDECESSOR_PATH):
        shutil.copyfile(ROOT / path, root / path)
    return root


@pytest.fixture(scope="module")
def model(basis):
    return decisions.build_snapshot(basis)


@pytest.fixture
def project(basis, tmp_path):
    shutil.copytree(basis, tmp_path, dirs_exist_ok=True)
    return tmp_path


def previous(root):
    return json.loads((root / decisions.PREDECESSOR_PATH).read_bytes())


def test_valid_in_memory_model_preserves_scope(basis, model):
    validate_snapshot(model, basis)
    source = previous(basis)
    assert model['predecessor'] == {'snapshot_id': decisions.PREDECESSOR_ID, 'path': decisions.PREDECESSOR_PATH, 'sha256': decisions.PREDECESSOR_HASH}
    assert model['run_id'] == source['run_id'] == decisions.RUN_ID
    assert model['stage'] == 'decision-and-approval' and model['sequence'] == 7
    assert model['status'] == 'partial' and model['state']['output_status'] == 'draft'
    assert model['state']['recommendation'] == 'option-oct17-green-table'
    assert model['state']['learner_decisions'] == model['decisions'] == []
    assert model['unresolved'] == source['unresolved'] and len(model['unresolved']) == 88
    assert model['state']['approval_requirements'] == source['state']['approval_requirements']
    assert len(model['state']['approval_requirements']) == 5
    assert all(g['status'] == 'pending' for g in model['state']['approval_requirements'])
    assert model['state']['retained_early_screening'] == source['state']['retained_early_screening']
    assert len(model['state']['retained_early_screening']) == 4
    assert not (basis / decisions.OUTPUT).exists()


def test_arithmetic_and_service_specific_tradeoffs(model):
    green, city = model['state']['candidate_reviews']
    for row, subtotal, total, capacity, margin, headroom in [(green,429000,494000,260,15,26000),(city,447000,512000,300,55,8000)]:
        costs = row['costs']
        assert sum(map(Decimal,costs['quoted_by_category'].values())) == Decimal(subtotal)
        assert sum(map(Decimal,costs['retained_allowances'].values())) == Decimal(65000)
        assert Decimal(costs['planning_total']) == Decimal(total)
        assert Decimal(row['remaining_ceiling']) == Decimal(headroom)
        assert Decimal(row['catering']['capacity']) == Decimal(capacity)
        assert Decimal(row['catering']['planning_demand']) == Decimal(245)
        assert Decimal(row['catering']['margin']) == Decimal(margin)
        assert Decimal(row['category_budget']['security']['allocation_variance']) == Decimal(3000)
        assert row['spending_authorized'] is False and row['selected'] is False
        assert row['feasibility'] == 'conditional' and row['authorization_status'] == 'pending'
    assert Decimal(city['category_budget']['catering']['allocation_variance']) == Decimal(11000)
    assert Decimal(green['category_budget']['catering']['allocation_variance']) == Decimal(-7000)
    assert {r['id'] for r in model['state']['tradeoffs']} == {'tradeoff-cost-and-headroom','tradeoff-catering-capacity','tradeoff-category-allocation-review','tradeoff-conditions-and-screened-alternatives'}


def test_traceability_and_ancestor_ownership(basis, model):
    upstream = previous(basis)
    upstream_ids = set(upstream['produced_record_ids'])
    refs = model['state']['ancestor_references']
    external = set()
    for ref in refs:
        data = (basis / ref['snapshot_path']).read_bytes(); ancestor=json.loads(data)
        assert hash_bytes(data) == ref['snapshot_sha256']
        assert ref['snapshot_id'] == ancestor['snapshot_id']
        assert ref['stage'] == ancestor['stage']
        assert ref['record_id'] in ancestor['produced_record_ids']
        assert ref['evidence_ids'] == [ref['record_id']]
        external.add(ref['record_id'])
    assert upstream_ids | external == set(model['consumed_record_ids'])
    records = [r for key in decisions.RECORD_ARRAYS for r in model['state'][key]] + model['unresolved']
    ids=[r['id'] for r in records]
    assert ids == model['produced_record_ids'] and len(ids)==len(set(ids))
    assert all(r['evidence_ids'] and set(r['evidence_ids']) <= upstream_ids | external | set(ids) for r in records)
    assert any(r['record_id']=='obs-brief-text-approvals' and r['stage']=='source-capture' for r in refs)
    for review in model['state']['candidate_reviews']:
        result=next(r for r in upstream['state']['option_results'] if r['id']==review['source_result_id'])
        assert review['check_ids']==result['check_ids']
        assert review['blocking_check_ids']==result['blocking_check_ids']
        assert review['schedule_witness_id']==result['schedule_witness_id']


def test_stable_ids_and_actual_execution_timestamps(basis, model):
    start=datetime.now(timezone.utc)
    other=decisions.build_snapshot(basis)
    assert other['produced_record_ids']==model['produced_record_ids']
    assert other['state']==model['state'] and other['snapshot_id']!=model['snapshot_id']
    assert start <= datetime.fromisoformat(other['created_at']) <= datetime.now(timezone.utc)
    assert other['created_at']!=other['state']['business_clock']


def test_provisional_policy_reconstructs_comparison(basis, model):
    source = previous(basis)
    checks = {c['id']: c for c in source['state']['checks']}
    reviews = model['state']['candidate_reviews']
    policy = model['state']['review_policy'][0]
    actual = decisions._recommendation_policy(reviews, checks)
    assert all(policy[k] == v for k, v in actual.items())
    assert policy['recommendation_status'] == 'provisional'
    assert policy['basis'] == 'planner-policy-not-stakeholder-rule'
    assert policy['recommended_candidate_id'] == model['state']['recommendation']
    green, city = sorted(policy['evaluations'], key=lambda r: r['planning_total'])
    assert Decimal(city['planning_total']) - Decimal(green['planning_total']) == Decimal(18000)
    assert Decimal(city['catering_capacity']) - Decimal(green['catering_capacity']) == Decimal(40)
    assert green['hard_dependencies'] == city['hard_dependencies'] == ['walkthrough-prerequisite']
    assert set(green['unresolved_requirements']) < set(city['unresolved_requirements'])
    assert policy['external_actions_authorized'] is False
    assert decisions._recommendation_policy(list(reversed(reviews)), checks) == actual


@pytest.mark.parametrize('winner_name', ['green-table', 'city-pantry'])
@pytest.mark.parametrize('capacity_relation', ['less', 'equal', 'more'])
@pytest.mark.parametrize('feasibility', ['conditional', 'feasible'])
def test_rationale_tracks_actual_winner_and_capacity(basis, model, winner_name, capacity_relation, feasibility):
    # Synthetic policy-only scenarios; these do not replace verified source inputs.
    reviews = deepcopy(model['state']['candidate_reviews'])
    checks = {c['id']: deepcopy(c) for c in previous(basis)['state']['checks']}
    winner = next(r for r in reviews if r['candidate_id'] == 'option-oct17-' + winner_name)
    alternative = next(r for r in reviews if r is not winner)
    if winner_name == 'city-pantry':
        winner['costs']['quoted_by_category']['catering'] = '100000.0'
        winner['costs']['quoted_subtotal'] = '421000.0'
        winner['costs']['planning_total'] = '486000.0'
        winner['remaining_ceiling'] = '34000.0'
        c = checks['check-oct17-city-pantry-allocation-policy-catering']
        winner['condition_ids'].remove(c['condition_ids'][0])
        c.update(condition_ids=[], outcome='pass')
    capacity = Decimal(alternative['catering']['capacity'])
    capacity += {'less': Decimal(-10), 'equal': Decimal(0), 'more': Decimal(10)}[capacity_relation]
    winner['catering'].update(capacity=str(capacity), margin=str(capacity - Decimal(245)))
    if feasibility == 'feasible':
        for r in reviews:
            c = checks['check-' + r['candidate_id'].removeprefix('option-') + '-walkthrough-prerequisite']
            r['condition_ids'].remove(c['condition_ids'][0])
            c.update(condition_ids=[], outcome='pass')
            r['feasibility'] = 'feasible'
    result = decisions._recommendation_policy(reviews, checks)
    assert result['recommended_candidate_id'] == winner['candidate_id']
    for r in reviews:
        assert (f"{r['candidate_id']}: {feasibility}, planning cost TWD {r['costs']['planning_total']}, "
                f"budget headroom TWD {r['remaining_ceiling']}, catering capacity {r['catering']['capacity']}") in result['rationale']
    summary = result['tradeoff_summary']
    assert summary.startswith(winner['candidate_id'] + ' costs TWD ')
    saving = Decimal(alternative['costs']['planning_total']) - Decimal(winner['costs']['planning_total'])
    assert f'TWD {saving} less' in summary
    if capacity_relation == 'equal':
        assert f"equal at {capacity} people" in summary
        assert 'more catering places' not in summary
    else:
        larger, smaller = (winner, alternative) if capacity_relation == 'more' else (alternative, winner)
        assert f"{larger['candidate_id']} offers 10" in summary
        assert f"than {smaller['candidate_id']}" in summary
    assert decisions._recommendation_policy(list(reversed(reviews)), checks) == result


@pytest.mark.parametrize('case', ['capacity', 'ceiling', 'fail', 'unknown', 'extra-condition',
                                  'different-dependency', 'tie', 'different-demand'])
def test_policy_defers_when_cost_advantage_is_not_sufficient(basis, model, case):
    # Synthetic assessments exercise policy branches; never alter preserved inputs.
    reviews = deepcopy(model['state']['candidate_reviews'])
    checks = {c['id']: deepcopy(c) for c in previous(basis)['state']['checks']}
    green, city = reviews
    if case == 'capacity':
        green['catering'].update(capacity='244', margin='-1')
    elif case == 'ceiling':
        green['costs']['planning_total'] = '520001'
        green['remaining_ceiling'] = '-1'
    elif case in ('fail', 'unknown'):
        checks['check-oct17-green-table-safety']['outcome'] = case
        green['feasibility'] = 'infeasible' if case == 'fail' else 'unverified'
    elif case in ('extra-condition', 'different-dependency'):
        c = checks['check-oct17-green-table-safety']
        c['condition_ids'] = ['synthetic-safety-condition']
        c['outcome'] = 'conditional'
        c['hard_requirement'] = case == 'different-dependency'
        green['condition_ids'].append('synthetic-safety-condition')
    elif case == 'tie':
        city['costs']['planning_total'] = green['costs']['planning_total']
        city['remaining_ceiling'] = green['remaining_ceiling']
    else:
        city['catering'].update(planning_demand='246', margin='54')
    result = decisions._recommendation_policy(reviews, checks)
    assert result['recommendation_status'] == 'deferred'
    assert result['recommended_candidate_id'] is None
    assert result['rationale'] and all(r['check_ids'] for r in result['evaluations'])
    for r in reviews:
        assert r['candidate_id'] + ': ' + r['feasibility'] in result['rationale']
        assert 'planning cost TWD ' + r['costs']['planning_total'] in result['rationale']
        assert 'catering capacity ' + r['catering']['capacity'] in result['rationale']
    assert result['tradeoff_summary'] in result['rationale']


@pytest.mark.parametrize('case', ['missing-check', 'wrong-candidate', 'boolean-number',
                                  'classification', 'missing-condition', 'selected', 'spending', 'arithmetic'])
def test_policy_rejects_inconsistent_or_authorized_assessments(basis, model, case):
    reviews = deepcopy(model['state']['candidate_reviews'])
    checks = {c['id']: deepcopy(c) for c in previous(basis)['state']['checks']}
    green = reviews[0]
    c = checks['check-oct17-green-table-safety']
    if case == 'missing-check': green['check_ids'].remove(c['id'])
    elif case == 'wrong-candidate': c['candidate_id'] = reviews[1]['candidate_id']
    elif case == 'boolean-number': c['hard_requirement'] = 1
    elif case == 'classification': green['feasibility'] = 'feasible'
    elif case == 'missing-condition': green['condition_ids'].pop()
    elif case == 'selected': green['selected'] = True
    elif case == 'spending': green['spending_authorized'] = True
    else: green['remaining_ceiling'] = '999'
    with pytest.raises(ValueError):
        decisions._recommendation_policy(reviews, checks)


@pytest.mark.parametrize('case', ['other-candidate', 'invented-candidate', 'erased', 'status',
                                  'rationale', 'tradeoff-wording', 'evaluation', 'criteria', 'policy-version', 'authority'])
def test_unsupported_recommendation_mutations_rejected(basis, model, case):
    snapshot = deepcopy(model)
    policy = snapshot['state']['review_policy'][0]
    if case == 'other-candidate':
        snapshot['state']['recommendation'] = policy['recommended_candidate_id'] = 'option-oct17-city-pantry'
    elif case == 'invented-candidate': snapshot['state']['recommendation'] = 'invented'
    elif case == 'erased': snapshot['state']['recommendation'] = None
    elif case == 'status': policy['recommendation_status'] = 'approved'
    elif case == 'rationale': policy['rationale'] = 'Lowest price automatically approves spending'
    elif case == 'tradeoff-wording': policy['tradeoff_summary'] = 'The recommended vendor has 999 extra places'
    elif case == 'evaluation': policy['evaluations'][0]['eligible'] = 1
    elif case == 'criteria': policy['criteria'] = ['lowest-cost-only']
    elif case == 'policy-version': policy['policy_version'] = 'forged'
    else: policy['external_actions_authorized'] = True
    with pytest.raises((ValueError, ValidationError)):
        validate_snapshot(snapshot, basis)


@pytest.mark.parametrize('mutation',[
    'recommendation','learner-decision','top-decision','approval','gate-missing','gate-owner','gate-applicability',
    'unresolved-missing','unresolved-edit','unresolved-duplicate','condition-id','selected','spending',
    'selected-number','spending-number','policy-number','feasibility','total','subtotal','allowance',
    'headroom','capacity','demand','margin','allocation','approval-limit','commitment','missing-check',
    'evidence','empty-evidence','ancestor-owner','ancestor-hash','ancestor-record','duplicate-id',
    'consumed','produced','screening','predecessor-id','predecessor-hash','predecessor-path','run',
    'status','audience','clock','sequence-float','unsupported-field','snapshot-id','timestamp-clock',
])
def test_semantic_mutations_fail_closed(basis, model, mutation):
    s=deepcopy(model);state=s['state'];r=state['candidate_reviews'][0]
    if mutation=='recommendation':state['recommendation']='Choose a vendor'
    elif mutation=='learner-decision':state['learner_decisions']=[{'id':'forged','summary':'forged','evidence_ids':[],'rationale':'forged','tradeoffs':['forged']}]
    elif mutation=='top-decision':s['decisions']=[{'id':'forged','summary':'forged','evidence_ids':[],'rationale':'forged','tradeoffs':['forged']}]
    elif mutation=='approval':state['approval_requirements'][0]['status']='approved'
    elif mutation=='gate-missing':state['approval_requirements'].pop()
    elif mutation=='gate-owner':state['approval_requirements'][0]['owner']='Unsupported actor'
    elif mutation=='gate-applicability':state['approval_requirements'][2]['applies_if']='never'
    elif mutation=='unresolved-missing':s['unresolved'].pop()
    elif mutation=='unresolved-edit':s['unresolved'][0]['summary']='Resolved without evidence'
    elif mutation=='unresolved-duplicate':s['unresolved'].append(deepcopy(s['unresolved'][0]))
    elif mutation=='condition-id':r['condition_ids']=[]
    elif mutation=='selected':r['selected']=True
    elif mutation=='spending':r['spending_authorized']=True
    elif mutation=='selected-number':r['selected']=0
    elif mutation=='spending-number':r['spending_authorized']=0
    elif mutation=='policy-number':state['review_policy'][0]['approval_evidence_required']=1
    elif mutation=='feasibility':r['feasibility']='feasible'
    elif mutation=='total':r['costs']['planning_total']='493999.0'
    elif mutation=='subtotal':r['costs']['quoted_subtotal']='1'
    elif mutation=='allowance':r['costs']['retained_allowances'].pop('contingency')
    elif mutation=='headroom':r['remaining_ceiling']='999999'
    elif mutation=='capacity':r['catering']['capacity']='999'
    elif mutation=='demand':r['catering']['planning_demand']='180'
    elif mutation=='margin':r['catering']['margin']='999'
    elif mutation=='allocation':r['category_budget']['security']['allocation_variance']='0'
    elif mutation=='approval-limit':r['category_budget']['security']['approval_limit']='999999'
    elif mutation=='commitment':r['category_budget']['security']['recorded_commitment']='28000'
    elif mutation=='missing-check':r['check_ids'].pop()
    elif mutation=='evidence':state['tradeoffs'][0]['evidence_ids']=['nonexistent']
    elif mutation=='empty-evidence':state['tradeoffs'][0]['evidence_ids']=[]
    elif mutation=='ancestor-owner':state['ancestor_references'][0]['stage']='feasibility-testing'
    elif mutation=='ancestor-hash':state['ancestor_references'][0]['snapshot_sha256']='sha256:'+'0'*64
    elif mutation=='ancestor-record':state['ancestor_references'][0]['record_id']='unsupported'
    elif mutation=='duplicate-id':state['tradeoffs'][1]['id']=state['tradeoffs'][0]['id']
    elif mutation=='consumed':s['consumed_record_ids'].pop()
    elif mutation=='produced':s['produced_record_ids'].pop()
    elif mutation=='screening':state['retained_early_screening'].pop()
    elif mutation=='predecessor-id':s['predecessor']['snapshot_id']='wrong'
    elif mutation=='predecessor-hash':s['predecessor']['sha256']='sha256:'+'0'*64
    elif mutation=='predecessor-path':s['predecessor']['path']='elsewhere.json'
    elif mutation=='run':s['run_id']='wrong'
    elif mutation=='status':s['status']='complete'
    elif mutation=='audience':state['audience']='public'
    elif mutation=='clock':state['business_clock']=s['created_at']
    elif mutation=='sequence-float':s['sequence']=7.0
    elif mutation=='unsupported-field':s['spending_approved']=True
    elif mutation=='snapshot-id':s['snapshot_id']=s['predecessor']['snapshot_id']
    elif mutation=='timestamp-clock':s['created_at']='2026-08-26T04:00:00+00:00'
    with pytest.raises((ValueError,ValidationError)):
        validate_snapshot(s,basis)


@pytest.mark.parametrize('kind',['stage6','stage5','workbook','capture','missing-source'])
def test_missing_or_tampered_inputs_rejected(project,kind):
    paths={
        'stage6':decisions.PREDECESSOR_PATH,'stage5':decisions.ANCESTOR_PATHS[-1],
        'workbook':'evidence/originals/Project C — Vendor Quotes.xlsx',
        'capture':'evidence/captures/capture-vendor-register-local-2b362101-8c3e-4a3c-841e-399236c00259.json',
        'missing-source':'evidence/originals/Project C — Attendee Signals.xlsx',
    }
    path=project/paths[kind]
    if kind=='missing-source':path.unlink()
    else:path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises((ValueError,OSError,ValidationError)):
        decisions.build_snapshot(project)
    assert not (project/decisions.OUTPUT).exists()


def test_late_predecessor_change_rejected(project,monkeypatch):
    import event_coordination.validation as validation
    original=validation.validate_snapshot;changed=[]
    def validate(snapshot,root):
        original(snapshot,root)
        if snapshot['stage']=='feasibility-testing' and not changed:
            changed.append(True)
            path=root/decisions.PREDECESSOR_PATH;path.write_bytes(path.read_bytes()+b'\n')
    monkeypatch.setattr(validation,'validate_snapshot',validate)
    with pytest.raises(ValueError,match='changed during evaluation'):
        decisions.build_snapshot(project)


def test_exclusive_writer_only_in_temporary_project(project):
    before={str(p.relative_to(project)):p.read_bytes() for p in project.rglob('*') if p.is_file()}
    path,digest=decisions.write_snapshot(project)
    saved=path.read_bytes();snapshot=json.loads(saved)
    validate_snapshot(snapshot,project)
    assert hash_bytes(saved)==digest and snapshot['stage']=='decision-and-approval'
    for name,content in before.items():assert (project/name).read_bytes()==content
    with pytest.raises(FileExistsError):decisions.write_snapshot(project)
    assert path.read_bytes()==saved


@pytest.mark.parametrize('kind',['file','directory','dangling-symlink','fifo'])
def test_writer_refuses_existing_output(project,kind):
    path=project/decisions.OUTPUT
    if kind=='file':path.write_bytes(b'sentinel')
    elif kind=='directory':path.mkdir()
    elif kind=='fifo':
        import os
        os.mkfifo(path)
    else:path.symlink_to(project/'absent')
    with pytest.raises(FileExistsError):decisions.write_snapshot(project)
    if kind=='file':assert path.read_bytes()==b'sentinel'
    elif kind=='directory':assert path.is_dir()
    elif kind=='fifo':
        import stat
        assert stat.S_ISFIFO(path.lstat().st_mode)
    else:assert path.is_symlink()


@pytest.mark.parametrize('fault', ['short-write', 'zero-write', 'write-error', 'readback-error'])
def test_writer_io_faults_fail_closed_and_preserve_outputs(project, monkeypatch, fault):
    import errno
    import os
    import event_coordination.validation as validation

    output = project / decisions.OUTPUT
    before = {p.relative_to(project): p.read_bytes()
              for p in project.rglob('*') if p.is_file()}
    original_open = decisions._exclusive_output
    original_write, original_read = os.write, os.read
    original_validate = validation.validate_snapshot
    output_fds, writes, readbacks, saved_validations = [], [], [], []

    def open_output(fd, relative):
        result = original_open(fd, relative)
        output_fds.append(result)
        return result

    def write(fd, data):
        if fd not in output_fds:
            return original_write(fd, data)
        writes.append(len(data))
        if fault == 'zero-write':
            return 0
        if fault == 'write-error':
            if len(writes) == 1:
                return original_write(fd, data[:64])
            raise OSError(errno.EIO, 'synthetic output write failure')
        return original_write(fd, data[:4096] if fault == 'short-write' else data)

    def read(fd, count):
        if fd in output_fds:
            readbacks.append(count)
            if fault == 'readback-error':
                raise OSError(errno.EIO, 'synthetic output readback failure')
        return original_read(fd, count)

    def validate(snapshot, root):
        if snapshot['stage'] == 'decision-and-approval' and output.exists():
            saved_validations.append(True)
        return original_validate(snapshot, root)

    monkeypatch.setattr(decisions, '_exclusive_output', open_output)
    monkeypatch.setattr(os, 'write', write)
    monkeypatch.setattr(os, 'read', read)
    monkeypatch.setattr(validation, 'validate_snapshot', validate)
    if fault == 'short-write':
        path, digest = decisions.write_snapshot(project)
        assert path == output and hash_bytes(path.read_bytes()) == digest
        assert len(writes) > 1 and readbacks and saved_validations == [True]
    elif fault == 'zero-write':
        with pytest.raises(ValueError, match='output write failed'):
            decisions.write_snapshot(project)
        assert writes and not readbacks and not saved_validations
        assert output.stat().st_size == 0
    else:
        with pytest.raises(OSError, match='synthetic output') as error:
            decisions.write_snapshot(project)
        assert error.value.errno == errno.EIO and not saved_validations
        if fault == 'write-error':
            assert len(writes) == 2 and not readbacks
            assert output.stat().st_size == 64
        else:
            assert writes and readbacks

    assert len(output_fds) == 1
    assert output.resolve().is_relative_to(project.resolve())
    for name, content in before.items():
        assert (project / name).read_bytes() == content
    assert {p.relative_to(project) for p in project.rglob('*') if p.is_file()} == set(before) | {Path(decisions.OUTPUT)}
    # Even a failed attempt's partial output must never be overwritten on retry.
    saved = output.read_bytes()
    with pytest.raises(FileExistsError):
        decisions.write_snapshot(project)
    assert output.read_bytes() == saved and len(output_fds) == 1


def test_exclusive_open_rejects_late_collision(project,model,monkeypatch):
    def collision(root):
        (root/decisions.OUTPUT).write_bytes(b'late sentinel')
        return deepcopy(model)
    monkeypatch.setattr(decisions,'build_snapshot',collision)
    with pytest.raises(FileExistsError):decisions.write_snapshot(project)
    assert (project/decisions.OUTPUT).read_bytes()==b'late sentinel'


@pytest.mark.parametrize('value',[True,0,1,1.0,None,'NaN','Infinity','-1'])
def test_invalid_derived_quantities_rejected(value):
    with pytest.raises(ValueError):decisions._amount(value)


LATE_INPUTS = {
    'vendor': 'evidence/originals/Project C — Vendor Quotes.xlsx',
    'capture': 'evidence/captures/capture-vendor-register-local-2b362101-8c3e-4a3c-841e-399236c00259.json',
    'interview': 'interviews/project-c-event-coordination-20261016-2056.md',
    'schema': 'snapshot.schema.json',
    'ancestor': decisions.ANCESTOR_PATHS[0],
    'media-copy': 'deliverables/snapshots/evidence/f1710485827023.pdf',
    'original-pdf': 'evidence/originals/f1710485827023.pdf',
}


@pytest.mark.parametrize('phase',['last-upstream-pass','before-build-return'])
@pytest.mark.parametrize('kind',list(LATE_INPUTS)+['delete','same-bytes-replace','restore','new-entry','new-directory','symlink'])
def test_late_protected_input_changes_fail_closed(project,monkeypatch,phase,kind):
    import event_coordination.validation as validation
    original=validation.validate_snapshot; calls=[]; mutated=[]
    def mutate():
        p=project/LATE_INPUTS.get(kind,LATE_INPUTS['vendor'])
        if kind=='delete':p.unlink()
        elif kind=='same-bytes-replace':
            replacement=p.with_name('synthetic-replacement');replacement.write_bytes(p.read_bytes());replacement.replace(p)
        elif kind=='restore':
            content=p.read_bytes();p.write_bytes(content+b'X');p.write_bytes(content)
        elif kind=='new-entry':(project/'evidence/captures/unexpected.json').write_bytes(b'{}')
        elif kind=='new-directory':(project/'interviews/new-empty-directory').mkdir()
        elif kind=='symlink':
            content=p.read_bytes();other=p.with_name('synthetic-linked-source');other.write_bytes(content);p.unlink();p.symlink_to(other)
        else:p.write_bytes(p.read_bytes()+b'\n')
        mutated.append(True)
    def validate(snapshot,root):
        original(snapshot,root)
        if snapshot['stage']=='feasibility-testing':calls.append(True)
        if not mutated and ((phase=='last-upstream-pass' and snapshot['stage']=='feasibility-testing' and len(calls)==2)
                            or (phase=='before-build-return' and snapshot['stage']=='decision-and-approval')):
            mutate()
    monkeypatch.setattr(validation,'validate_snapshot',validate)
    with pytest.raises((ValueError,OSError,ValidationError)):
        decisions.build_snapshot(project)
    assert mutated and not (project/decisions.OUTPUT).exists()


def test_shared_validation_pins_schema_before_parsing(project,model,monkeypatch):
    from jsonschema import Draft202012Validator
    original=Draft202012Validator.validate;changed=[]
    def validate(self,instance,*args,**kwargs):
        result=original(self,instance,*args,**kwargs)
        if instance is model and not changed:
            changed.append(True)
            p=project/'snapshot.schema.json';p.write_bytes(p.read_bytes()+b'\n')
        return result
    monkeypatch.setattr(Draft202012Validator,'validate',validate)
    with pytest.raises(ValueError,match='protected inputs changed'):
        validate_snapshot(model,project)
    assert changed


def test_protected_observation_rejects_unstable_reads(project,monkeypatch):
    import os
    path=project/'snapshot.schema.json';original=os.read;changed=[]
    def read(fd,count):
        result=original(fd,count)
        if not changed:
            changed.append(True);path.write_bytes(path.read_bytes()+b'\n')
        return result
    monkeypatch.setattr(os,'read',read)
    with pytest.raises(ValueError,match='changed during observation'):
        decisions._protected_file(project,'snapshot.schema.json')


def test_manifest_fails_closed_on_unreadable_traversal(project,monkeypatch):
    import os
    original=os.listdir
    def listing(fd):
        if isinstance(fd,int) and os.readlink(f'/proc/self/fd/{fd}')==str(project/'interviews'):
            raise PermissionError('synthetic unreadable input directory')
        return original(fd)
    monkeypatch.setattr(os,'listdir',listing)
    with pytest.raises(PermissionError):decisions.build_snapshot(project)


@pytest.mark.parametrize('parent',['deliverables','deliverables/snapshots'])
def test_writer_rejects_symlinked_parents_without_escape(project,parent):
    source=project/parent;outside=project.parent/('outside-'+project.name)
    source.rename(outside);source.symlink_to(outside,target_is_directory=True)
    with pytest.raises((OSError,ValueError)):decisions.write_snapshot(project)
    assert not (project/decisions.OUTPUT).exists()
    assert not list(outside.rglob('07-*'))


def test_writer_rejects_root_alias(project):
    alias=project.parent/('alias-'+project.name);alias.symlink_to(project,target_is_directory=True)
    with pytest.raises(ValueError,match='symlink aliases'):decisions.write_snapshot(alias)
    assert not (project/decisions.OUTPUT).exists()


@pytest.mark.parametrize('boundary',['after-build','before-kernel-open'])
@pytest.mark.parametrize('replacement',['symlink','directory'])
def test_writer_rejects_late_parent_swaps(project,monkeypatch,boundary,replacement):
    outside=project.parent/('moved-'+project.name);swapped=[]
    def swap():
        p=project/'deliverables/snapshots';p.rename(outside)
        if replacement=='symlink':p.symlink_to(outside,target_is_directory=True)
        else:p.mkdir()
        swapped.append(True)
    if boundary=='after-build':
        original=decisions.build_snapshot
        def build(root):
            result=original(root);swap();return result
        monkeypatch.setattr(decisions,'build_snapshot',build)
    else:
        original=decisions._exclusive_output
        def create(fd,relative):
            swap();return original(fd,relative)
        monkeypatch.setattr(decisions,'_exclusive_output',create)
    with pytest.raises((OSError,ValueError)):decisions.write_snapshot(project)
    assert swapped and not list(outside.rglob('07-*'))
    # Even if a regular replacement directory wins the kernel lookup, it is
    # detected before any snapshot bytes are written; no valid result is returned.
    candidate=project/decisions.OUTPUT
    if candidate.is_file():assert candidate.read_bytes()==b''


def test_safe_writer_has_no_unsupported_kernel_fallback(project,monkeypatch):
    import errno
    from types import SimpleNamespace
    from unittest.mock import Mock
    fake=Mock(return_value=-1)
    monkeypatch.setattr(decisions.ctypes,'CDLL',lambda *a,**k:SimpleNamespace(syscall=fake))
    monkeypatch.setattr(decisions.ctypes,'get_errno',lambda:errno.ENOSYS)
    with pytest.raises(OSError) as error:decisions.write_snapshot(project)
    assert error.value.errno==errno.ENOSYS and fake.call_count==1
    assert not (project/decisions.OUTPUT).exists()


def test_output_is_rechecked_after_saved_snapshot_validation(project,monkeypatch):
    import event_coordination.validation as validation
    original=validation.validate_snapshot;changed=[]
    def validate(snapshot,root):
        original(snapshot,root)
        p=root/decisions.OUTPUT
        if snapshot['stage']=='decision-and-approval' and p.exists() and not changed:
            changed.append(True);p.write_bytes(b'synthetic changed output')
    monkeypatch.setattr(validation,'validate_snapshot',validate)
    with pytest.raises(ValueError,match='output changed during validation'):
        decisions.write_snapshot(project)
    assert changed


@pytest.mark.parametrize('replacement',['symlink','directory'])
def test_root_prefix_replacement_during_open_is_rejected(tmp_path,monkeypatch,replacement):
    import os
    prefix=tmp_path/'prefix';root=prefix/'repository';root.mkdir(parents=True)
    outside=tmp_path/'moved-prefix';original=os.open;swapped=[]
    def opened(path,flags,*args,**kwargs):
        if path=='prefix' and not swapped and 'dir_fd' in kwargs and os.readlink(f"/proc/self/fd/{kwargs['dir_fd']}")==str(tmp_path):
            prefix.rename(outside)
            if replacement=='symlink':prefix.symlink_to(outside,target_is_directory=True)
            else:(prefix/'repository').mkdir(parents=True)
            swapped.append(True)
        return original(path,flags,*args,**kwargs)
    monkeypatch.setattr(os,'open',opened)
    with pytest.raises((OSError,ValueError)):
        with decisions._Directories(root,[]):
            pytest.fail('unsafe root prefix was accepted')
    assert swapped and not list(outside.rglob('07-*'))
