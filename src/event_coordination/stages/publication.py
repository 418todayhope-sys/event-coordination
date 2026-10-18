"""Stage 09: technical validation of saved drafts, never external publication."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import UUID, uuid4

from jsonschema import Draft202012Validator, FormatChecker

from event_coordination import draft_contract
from event_coordination.run_contract import read_predecessor, _read
from event_coordination.sources import hash_bytes
from event_coordination.stages import drafts, decisions

OUTPUT = 'deliverables/snapshots/09-publication-validation.json'
PREDECESSOR_PATH = drafts.OUTPUT


class _Inputs:
    def __init__(self, root):
        self.root = root
        self.earlier = drafts._PinnedInputs(root)
        self.paths = (PREDECESSOR_PATH, *drafts.ARTIFACT_PATHS)
        self.pins = {p: decisions._protected_file(root, p) for p in self.paths}

    def verify(self):
        self.earlier.verify()
        if any(decisions._protected_file(self.root, p) != v for p, v in self.pins.items()):
            raise ValueError('Stage 09 saved input changed')


def _expected(root):
    from event_coordination.validation import validate_snapshot
    pins = _Inputs(root)
    content = read_predecessor(root, PREDECESSOR_PATH, drafts.HISTORICAL_SNAPSHOT_HASH)
    upstream = json.loads(content)
    validate_snapshot(upstream, root)
    state = upstream['state']
    if (state.get('draft_contract_version') != draft_contract.VERSION
            or state.get('generation_mode') != 'saved-files-verified'):
        raise ValueError('Stage 09 requires saved assignment-drafts/1 outputs')
    artifacts, saved = [], {}
    for record in state['artifact_drafts']:
        data, _ = _read(root, record['path'])
        digest = hash_bytes(data)
        if digest != record['sha256'] or record['saved_file_verified'] is not True:
            raise ValueError('Stage 09 artifact hash is incorrect')
        saved[record['path']] = data
        artifacts.append({'id': 'validated-' + record['id'], 'path': record['path'],
                          'sha256': digest, 'validation_status': 'valid',
                          'hash_scope': 'verified-saved-bytes', 'evidence_ids': [record['id']],
                          'draft_only': True})
    if set(saved) != set(drafts.ARTIFACT_PATHS):
        raise ValueError('Stage 09 requires exactly four saved artifacts')
    # Parse the actual saved bytes independently of renderer reconstruction.
    # This checker verifies assignment fields, source costs and delivery boundaries.
    draft_contract.validate_artifacts(drafts._context(root), saved, drafts.ARTIFACT_PATHS)
    consumed = sorted(upstream['produced_record_ids'])
    checks = [
        {'id': 'validation-' + name, 'summary': summary, 'evidence_ids': evidence,
         'status': 'passed', 'scope': 'technical-local-drafts-only'}
        for name, summary, evidence in (
            ('lineage', 'Saved Stage 08 and full upstream lineage validated.', consumed),
            ('saved-bytes', 'Four actual artifact paths and SHA-256 hashes verified.', [r['id'] for r in state['artifact_drafts']]),
            ('assignment-content', 'Saved draft content and source-backed calculations validated.', consumed),
            ('approval-boundaries', 'Unsent drafts retain pending approvals; no external action authorized.', [g['id'] for g in state['approval_requirements']]),
        )]
    result_state = {key: deepcopy(state[key]) for key in (
        'approval_requirements', 'retained_early_screening', 'recommendation', 'learner_decisions')}
    result_state.update(business_clock=drafts.BUSINESS_CLOCK, draft_contract_version=draft_contract.VERSION,
        artifacts=artifacts, validation_checks=checks, publication_status='blocked',
        technical_validation_status='valid', external_publication_status='not-published',
        external_actions_authorized=False,
        publication_status_reason='Technical draft validation passed. Business approvals and operational verification remain pending; external publication is blocked.')
    unresolved = deepcopy(upstream['unresolved'])
    produced = sorted({r['id'] for r in (*artifacts, *checks, *unresolved,
                        *state['approval_requirements'], *state['retained_early_screening'])})
    pins.verify()
    return {'run_id': upstream['run_id'], 'stage': 'publication-validation', 'sequence': 9,
            'status': 'partial', 'predecessor': {'snapshot_id': upstream['snapshot_id'],
                'path': PREDECESSOR_PATH, 'sha256': hash_bytes(content)},
            'consumed_record_ids': consumed, 'produced_record_ids': produced,
            'state': result_state, 'unresolved': unresolved, 'decisions': []}


def build_snapshot(root):
    root = Path(root)
    snapshot = _expected(root)
    snapshot.update(schema_version='event-coordination-stage-snapshot/2',
                    snapshot_id=str(uuid4()), created_at=datetime.now(timezone.utc).isoformat())
    return snapshot


def validate_stage9(snapshot, root):
    root = Path(root)
    pins = _Inputs(root)
    data, _ = _read(root, 'snapshot.schema.json')
    if hash_bytes(data) != drafts.SCHEMA_HASH:
        raise ValueError('Stage 09 schema changed')
    Draft202012Validator(json.loads(data), format_checker=FormatChecker()).validate(snapshot)
    UUID(snapshot['snapshot_id'])
    drafts._timestamp(snapshot['created_at'])
    expected = _expected(root)
    if snapshot.keys() != expected.keys() | {'schema_version', 'snapshot_id', 'created_at'}:
        raise ValueError('Stage 09 envelope mismatch')
    for key, value in expected.items():
        decisions._strict_equal(snapshot[key], value)
    for stage in range(1, 9):
        paths = list((root / 'deliverables/snapshots').glob(f'{stage:02}-*.json'))
        if len(paths) != 1 or json.loads(_read(root, str(paths[0].relative_to(root)))[0])['snapshot_id'] == snapshot['snapshot_id']:
            raise ValueError('Stage 09 snapshot identity is not new')
    pins.verify()


def write_snapshot(root):
    root = Path(root)
    pins = _Inputs(root)
    with decisions._Directories(root, decisions._parts(OUTPUT)[:-1]) as parent:
        # Exclusive creation is the final collision guard; never delete partial output.
        if (root / OUTPUT).exists() or (root / OUTPUT).is_symlink():
            raise FileExistsError('Stage 09 output already exists')
        snapshot = build_snapshot(root)
        validate_stage9(snapshot, root)
        pins.verify()
        content = (json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        identity = drafts._write_exclusive(root, OUTPUT, content, parent)
        saved, _ = _read(root, OUTPUT)
        if saved != content:
            raise ValueError('Stage 09 readback mismatch')
        validate_stage9(json.loads(saved), root)
        drafts._read_saved(root, OUTPUT, content, identity)
        pins.verify()
        parent.verify()
        return root / OUTPUT, hash_bytes(saved)
