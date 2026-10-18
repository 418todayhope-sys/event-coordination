"""Saved-byte publication validation in isolated copies, never historical outputs."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from event_coordination import pipeline
from event_coordination.run_contract import InputSpec, RunSession, activate_run, pin_inputs
from event_coordination.sources import hash_bytes
from event_coordination.stages import drafts, publication
from event_coordination.validation import validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def basis(tmp_path_factory):
    target = tmp_path_factory.mktemp('stage9-copy') / 'run'
    supplied = os.environ.get('PROJECT_C_STAGE9_BASIS')
    if supplied:
        shutil.copytree(supplied, target)
    else:
        pipeline.run_stages(ROOT, target, through_stage=8)
    # Only copy-generated output is removed, to exercise the exclusive writer.
    output = target / publication.OUTPUT
    if output.exists():
        output.unlink()
    first = json.loads((target / pipeline.scope.OUTPUT).read_bytes())
    pin = pin_inputs(target, (InputSpec('schema', 'snapshot.schema.json', 'schema', drafts.SCHEMA_HASH),))[0]
    session = RunSession(target, first['state']['run_metadata'], pin)
    with activate_run(session):
        for module in pipeline.STAGE_MODULES:
            session.register(module.OUTPUT, hash_bytes((target / module.OUTPUT).read_bytes()))
        yield target


@pytest.fixture(scope='module')
def model(basis):
    return publication.build_snapshot(basis)


def test_valid_saved_bytes_schema_and_lineage(basis, model):
    validate_snapshot(model, basis)
    Draft202012Validator(json.loads((basis/'snapshot.schema.json').read_bytes()),
                        format_checker=FormatChecker()).validate(model)
    upstream = json.loads((basis/drafts.OUTPUT).read_bytes())
    assert model['sequence'] == 9 and model['run_id'] == upstream['run_id']
    assert model['predecessor'] == {'path': drafts.OUTPUT, 'snapshot_id': upstream['snapshot_id'],
                                    'sha256': hash_bytes((basis/drafts.OUTPUT).read_bytes())}
    assert len(model['state']['artifacts']) == 4
    assert all(hash_bytes((basis/a['path']).read_bytes()) == a['sha256'] for a in model['state']['artifacts'])
    assert model['unresolved'] == upstream['unresolved'] and len(model['unresolved']) == 88
    for key, count in [('approval_requirements',5),('retained_early_screening',4)]:
        assert model['state'][key] == upstream['state'][key] and len(model['state'][key]) == count
    assert model['state']['publication_status'] == 'blocked' and model['status'] == 'partial'
    assert model['state']['technical_validation_status'] == 'valid'
    assert model['state']['external_publication_status'] == 'not-published'
    assert model['state']['external_actions_authorized'] is False
    assert model['decisions'] == model['state']['learner_decisions'] == []


@pytest.mark.parametrize('change', ['artifact-hash','predecessor-hash','predecessor-id','run','approval','publication','boolean','check'])
def test_forged_snapshot_claims_rejected(basis, model, change):
    bad = deepcopy(model)
    if change == 'artifact-hash': bad['state']['artifacts'][0]['sha256'] = 'sha256:'+'0'*64
    if change == 'predecessor-hash': bad['predecessor']['sha256'] = 'sha256:'+'0'*64
    if change == 'predecessor-id': bad['predecessor']['snapshot_id'] = 'forged'
    if change == 'run': bad['run_id'] = 'forged'
    if change == 'approval': bad['state']['approval_requirements'][0]['status'] = 'approved'
    if change == 'publication': bad['state']['publication_status'] = 'validated'
    if change == 'boolean': bad['state']['external_actions_authorized'] = 0
    if change == 'check': bad['state']['validation_checks'][0]['status'] = 'failed'
    with pytest.raises(ValueError): validate_snapshot(bad, basis)


@pytest.mark.parametrize('problem', ['missing','tampered'])
def test_changed_saved_artifact_rejected(basis, model, problem):
    path = basis/drafts.ARTIFACT_PATHS[0]
    data = path.read_bytes()
    try:
        if problem == 'missing': path.unlink()
        else: path.write_bytes(data+b'forged content')
        with pytest.raises((OSError,ValueError)): validate_snapshot(model,basis)
    finally:
        path.write_bytes(data)


def test_exclusive_writer_readback_and_overwrite_refusal(basis):
    path, digest = publication.write_snapshot(basis)
    assert digest == hash_bytes(path.read_bytes())
    validate_snapshot(json.loads(path.read_bytes()), basis)
    with pytest.raises(FileExistsError): publication.write_snapshot(basis)
    assert hash_bytes(path.read_bytes()) == digest
