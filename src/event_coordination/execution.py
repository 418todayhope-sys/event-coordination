"""Managed local runs: stage in private attempts, preserve history, then promote.

No approvals, retrieval, Git actions or publication. A dedicated external workspace
is mandatory. A crash journal is not a successful run or an approval record.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import stat
from uuid import uuid4, UUID

from event_coordination import pipeline
from event_coordination.input_changes import semantic_manifest, meaningful_changes
from event_coordination.run_contract import (InputSpec, RunSession, activate_run, new_run_metadata,
    pin_inputs, _read, _json, relative_path)
from event_coordination.sources import hash_bytes
from event_coordination.stages import decisions, drafts, publication

MANIFEST='deliverables/run-manifest.json'
JOURNAL='deliverables/attempt.json'
FAILURE='deliverables/failure.json'


def now(): return datetime.now(timezone.utc).isoformat()


def _json_file(root,path): return _json(_read(root,path)[0])


def _save(root,path,value):
    """Atomic replacement of technical receipts only, never historical evidence."""
    data=(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    _install(root,path,data)


def _install(root,path,data):
    parts=relative_path(path).split('/')
    if len(parts)>1: pipeline._mkdir(root,'/'.join(parts[:-1]))
    temporary='/'.join([*parts[:-1],'.pending-'+str(uuid4())])
    pipeline._copy_bytes(root,temporary,data)
    with decisions._Directories(root,parts[:-1]) as directory:
        try:
            item=os.stat(parts[-1],dir_fd=directory.fds[-1],follow_symlinks=False)
            if not stat.S_ISREG(item.st_mode): raise ValueError('unsafe_existing_destination')
        except FileNotFoundError: pass
        directory.verify()
        os.replace(Path(temporary).name,parts[-1],src_dir_fd=directory.fds[-1],dst_dir_fd=directory.fds[-1])
        os.fsync(directory.fds[-1]);directory.verify()
    if _read(root,path)[0]!=data: raise ValueError('promotion_readback_failed')


def _safe_files(root):
    """Observe only active run data; never include nested history or attempts."""
    result={}
    if (root/'evidence').exists() and (root/'interviews').exists() and (root/'snapshot.schema.json').exists():
        for path,entry in pipeline._inputs(root).items():
            if entry[0]=='file': result[path]=entry[2]
    for path in ('snapshot.schema.json', MANIFEST, FAILURE, JOURNAL):
        if (root/path).exists(): result[path]=hash_bytes(_read(root,path)[0])
    deliverables=root/'deliverables'
    if deliverables.exists():
        def visit(path):
            with decisions._Directories(root,path.split('/')) as parent:
                for name in sorted(os.listdir(parent.fds[-1])):
                    if path=='deliverables' and name in ('history','failures'): continue
                    child=path+'/'+name
                    item=os.stat(name,dir_fd=parent.fds[-1],follow_symlinks=False)
                    if stat.S_ISDIR(item.st_mode): visit(child)
                    elif stat.S_ISREG(item.st_mode): result[child]=hash_bytes(_read(root,child)[0])
                    else: raise ValueError('unsafe_active_output')
                parent.verify()
        visit('deliverables')
    return result


def _check_manifest(value):
    if type(value) is not dict or type(value.get('execution_contract_version')) is not int or value['execution_contract_version']!=1:
        raise ValueError('unsupported_execution_manifest')
    if str(UUID(value['run_id']))!=value['run_id'] or type(value.get('files')) is not dict: raise ValueError('invalid_manifest_identity')
    for path,digest in value['files'].items():
        relative_path(path)
        if not (path=='snapshot.schema.json' or path.startswith(('evidence/','interviews/','deliverables/snapshots/')) or path in drafts.ARTIFACT_PATHS):
            raise ValueError('manifest_path_out_of_scope')
        if type(digest) is not str or len(digest)!=71 or not digest.startswith('sha256:'):
            raise ValueError('invalid_manifest_hash')
    return value


def detect_changes(previous, source, incoming):
    changed_sources, changed_decisions = meaningful_changes(previous['semantic_inputs'], incoming)
    # Interview/brief decisions are not covered by spreadsheet layout equivalence.
    for path,digest in previous['files'].items():
        if path.startswith('interviews/') or path=='snapshot.schema.json':
            try: changed=hash_bytes(_read(source,path)[0])!=digest
            except (OSError,ValueError): changed=True
            if changed: changed_decisions.append('decision-evidence-'+hash_bytes(path.encode())[7:23])
    return changed_sources, sorted(set(changed_decisions))


def validate_run(root, manifest):
    manifest=_check_manifest(manifest)
    for path,digest in manifest['files'].items():
        if hash_bytes(_read(root,path)[0])!=digest: raise ValueError('saved_run_file_changed')
    first=_json_file(root,pipeline.scope.OUTPUT)
    if first['run_id']!=manifest['run_id']: raise ValueError('manifest_run_mismatch')
    schema=pin_inputs(root,(InputSpec('schema','snapshot.schema.json','schema',drafts.SCHEMA_HASH),))[0]
    session=RunSession(root,first['state']['run_metadata'],schema)
    with activate_run(session):
        for module in (*pipeline.STAGE_MODULES,publication):
            if module.OUTPUT not in manifest['files']: raise ValueError('incomplete_run_manifest')
            session.register(module.OUTPUT,manifest['files'][module.OUTPUT])
    if semantic_manifest(root)!=manifest['semantic_inputs']: raise ValueError('stale_semantic_manifest')
    if _safe_files(root).keys()-manifest['files'].keys()-{MANIFEST,FAILURE,JOURNAL}:
        raise ValueError('unexpected_active_outputs')


def _preserve(root,base,expected=None):
    """Exclusive verified copies. Missing/corrupt prior files are reported honestly."""
    actual=_safe_files(root)
    if (root/base).exists(): raise FileExistsError('archive_collision')
    pipeline._mkdir(root,base)
    for path,digest in sorted(actual.items()):
        data,_=_read(root,path)
        if hash_bytes(data)!=digest: raise ValueError('active_run_changed_while_archiving')
        pipeline._copy_bytes(root,base+'/'+path,data)
    differences=[]
    for path,digest in (expected or {}).items():
        if actual.get(path)!=digest: differences.append({'path':path,'expected_sha256':digest,'observed_sha256':actual.get(path)})
    _save(root,base+'/archive.json',{'observed_at':now(),'files':actual,
        'integrity_status':'valid-copy' if not differences else 'incomplete-or-corrupt-copy',
        'differences':differences})
    return actual


def _failure(root,attempt,code,source,stage):
    observed=[]
    try:
        observed=[{'path':p,'sha256':v[2],'verification':'observed-local-bytes-only'}
                  for p,v in pipeline._inputs(source).items() if v[0]=='file']
    except (OSError,ValueError): pass
    receipt={'run_id':attempt['run_id'],'attempt_id':attempt['attempt_id'],'observed_at':now(),
        'status':'failed','error':code,'affected_stage':stage,
        'affected_stage_name':'preflight' if stage==0 else (*pipeline.STAGE_MODULES,publication)[stage-1].OUTPUT,
        'available_evidence':observed,
        'affected_artifacts':list(drafts.ARTIFACT_PATHS)+[publication.OUTPUT],
        'next_owner':'Local workflow operator; business approvals remain pending',
        'recovery_action':('Preserve incomplete/conflicting history unchanged; the local operator must review archive integrity before another attempt.'
            if code in ('archive_incomplete_requires_review','archive_collision','archive_changed') else
            'Preserve attempt and history. Correct registered inputs or rerun execute with --recover after reviewing this receipt.'),
        'attempt_workspace':attempt['candidate'],'external_actions_authorized':False}
    pipeline._copy_bytes(root,'deliverables/failures/'+str(uuid4())+'.json',
                         (json.dumps(receipt,indent=2)+'\n').encode())
    _save(root,FAILURE,receipt)
    return receipt


@contextmanager
def _lock(root,recover):
    relative='.execution-lock'
    try:
        old=_json_file(root,relative)
    except FileNotFoundError: old=None
    except ValueError:
        if (root/relative).exists(): raise ValueError('invalid_execution_lock') from None
        old=None
    if old is not None:
        if type(old) is not dict or set(old)!={'pid','host'}: raise ValueError('invalid_execution_lock')
        if not recover or type(old.get('pid')) is not int or old['pid']<=1 or old.get('host')!=socket.gethostname():
            raise ValueError('execution_locked')
        try: os.kill(old['pid'],0)
        except ProcessLookupError: pass
        else: raise ValueError('execution_still_running')
        pipeline._copy_bytes(root,'.attempts/stale-lock-'+str(uuid4())+'.json',_read(root,relative)[0])
        with decisions._Directories(root,[]) as parent:
            os.unlink(relative,dir_fd=parent.fds[-1]);parent.verify()
    data=json.dumps({'pid':os.getpid(),'host':socket.gethostname()}).encode()
    pipeline._copy_bytes(root,relative,data)
    identity=decisions._protected_file(root,relative)
    try: yield
    finally:
        if decisions._protected_file(root,relative)!=identity: raise ValueError('execution_lock_changed')
        with decisions._Directories(root,[]) as parent:
            os.unlink(relative,dir_fd=parent.fds[-1]);parent.verify()


def execute(source_root,workspace,*,recover=False):
    """Only dedicated external workspaces; historical repository is never replaced."""
    source=Path(source_root).absolute(); root=Path(workspace).absolute()
    if type(recover) is not bool or source.resolve()!=source or root.is_relative_to(source) or source.is_relative_to(root):
        raise ValueError('dedicated_external_workspace_required')
    with decisions._Directories(root.parent,[]) as parent:
        if not root.exists(): os.mkdir(root.name,mode=0o700,dir_fd=parent.fds[-1])
        parent.verify()
    with decisions._Directories(root,[]) as directory:
        # An existing unrelated workspace, repository or audited run is never adopted.
        names=set(os.listdir(directory.fds[-1]))
        if names & {'.git','.entire','.codex','.aws','.ssh'}: raise ValueError('repository_workspace_refused')
        if names and not (root/JOURNAL).exists() and not (root/MANIFEST).exists():
            raise ValueError('unmanaged_workspace_refused')
        with _lock(root,recover):
            return _execute_locked(source,root,recover)


def _execute_locked(source,root,recover):
    attempt={'attempt_id':str(uuid4()),'run_id':str(uuid4())}
    attempt['candidate']='.attempts/'+attempt['attempt_id']+'/candidate'
    stage=0
    try:
        previous=_check_manifest(_json_file(root,MANIFEST)) if (root/MANIFEST).exists() else None
        journal=_json_file(root,JOURNAL) if (root/JOURNAL).exists() else None
        interrupted=journal is not None and journal.get('status') in ('running','promoting','failed')
        if interrupted and not recover:
            stage=journal.get('affected_stage',0)
            raise ValueError('interrupted_attempt_requires_recovery')
        if interrupted:
            _failure(root,journal,'previous_attempt_incomplete',source,journal.get('affected_stage',0))
        observed_source=pipeline._inputs(source)
        incoming=semantic_manifest(source)
        pipeline._verify(source,observed_source)
        stale=False
        if previous:
            try: validate_run(root,previous)
            except (OSError,ValueError,KeyError):
                stale=True
                stage=9
                _failure(root,attempt,'prior_outputs_missing_corrupt_or_stale',source,9)
                if not recover: raise ValueError('recovery_required') from None
        changed_sources,changed_decisions=detect_changes(previous,source,incoming) if previous else ([],[])
        if previous and not changed_sources and not changed_decisions and not stale and not interrupted:
            incoming_archive='.attempts/'+attempt['attempt_id']+'/equivalent-inputs'
            observed=pipeline._inputs(source)
            for p,entry in observed.items():
                if entry[0]=='file': pipeline._copy_bytes(root,incoming_archive+'/'+p,_read(source,p)[0])
            pipeline._verify(source,observed)
            return {'incoming_input_archive':incoming_archive,'run_id':previous['run_id'],'execution_status':'unchanged-equivalent-inputs',
                    'validation_status':'valid','publication_status':'blocked','status':'partial',
                    'external_actions_authorized':False}
        reasons=[{'kind':'source','id':i,'reason':'Registered semantic source content or retrieval state changed; all stages recomputed.',
                  'evidence_ids':['source-group-'+i]} for i in changed_sources]
        reasons += [{'kind':'decision','id':i,'reason':'Preserved decision/advisory evidence changed; see input manifests and archived bytes. No approval inferred; all stages recomputed.',
                     'evidence_ids':['scope-gates']} for i in changed_decisions]
        if previous and not reasons:
            reasons=[{'kind':'recovery','id':'recover-saved-run','reason':'Rebuild missing, corrupt, stale or interrupted local outputs; preserve prior files.',
                      'evidence_ids':['scope-gates']}]
        metadata=new_run_metadata(supersedes_run_id=previous['run_id'] if previous else None,
            changed_source_ids=tuple(changed_sources),changed_decision_ids=tuple(changed_decisions),
            change_reasons=tuple(sorted(reasons,key=lambda r:(r['kind'],r['id']))))
        attempt['run_id']=metadata['run_id']
        attempt.update(status='running',affected_stage=0,observed_at=now())
        _save(root,JOURNAL,attempt)
        pipeline._mkdir(root,'.attempts/'+attempt['attempt_id'])
        def progress(number,run_id):
            nonlocal stage
            stage=number;attempt.update(affected_stage=number,observed_at=now())
            _save(root,JOURNAL,attempt)
        candidate=root/attempt['candidate']
        report=pipeline.run_stages(source,candidate,metadata=metadata,progress=progress)
        report['limitations']=['Local source copies remain unverified against live sources.',
            'Approval ingestion and fundamental event-scope changes require human review.',
            'Incomplete or conflicting history archives require human review; never overwritten.']
        if semantic_manifest(source)!=incoming: raise ValueError('source_changed_during_execution')
        files=_safe_files(candidate)
        manifest={'execution_contract_version':1,'run_id':metadata['run_id'],
                  'semantic_inputs':incoming,'files':files,'report':report}
        validate_run(candidate,manifest)
        if previous:
            archive='deliverables/history/'+previous['run_id']
            if not (root/archive).exists():
                before=_preserve(root,archive,previous['files'])
            else:
                # Never replace an archive left by a previous interrupted promotion.
                if not (root/archive/'archive.json').is_file():
                    raise ValueError('archive_incomplete_requires_review')
                saved=_json_file(root,archive+'/archive.json')
                archived=_check_manifest(_json_file(root,archive+'/'+MANIFEST))
                if archived['run_id']!=previous['run_id'] or archived['files']!=previous['files']:
                    raise ValueError('archive_collision')
                for p,h in saved['files'].items():
                    if hash_bytes(_read(root,archive+'/'+p)[0])!=h: raise ValueError('archive_changed')
                before=_preserve(root,'deliverables/failures/'+attempt['attempt_id']+'/partial-current',previous['files'])
        else: before={}
        attempt['status']='promoting';_save(root,JOURNAL,attempt)
        # Nothing is replaced until candidate validation and archive verification pass.
        # Preserve obsolete or interrupted temporary active files outside the new run.
        for path in sorted(before.keys()-files.keys()-{MANIFEST,FAILURE,JOURNAL}):
            if hash_bytes(_read(root,path)[0])!=before[path]: raise ValueError('superseded_file_changed')
            target='deliverables/failures/'+attempt['attempt_id']+'/superseded-files/'+path
            pipeline._mkdir(root,str(Path(target).parent))
            with decisions._Directories(root,relative_path(path).split('/')[:-1]) as a, decisions._Directories(root,relative_path(target).split('/')[:-1]) as b:
                a.verify();b.verify()
                if (root/target).exists(): raise FileExistsError('quarantine_collision')
                os.rename(Path(path).name,Path(target).name,src_dir_fd=a.fds[-1],dst_dir_fd=b.fds[-1])
                a.verify();b.verify()
        for path in sorted(files):
            if path in before and hash_bytes(_read(root,path)[0])!=before[path]:
                raise ValueError('active_output_changed_after_archive')
            _install(root,path,_read(candidate,path)[0])
        _save(root,MANIFEST,manifest)
        validate_run(root,manifest)
        attempt.update(status='completed',observed_at=now());_save(root,JOURNAL,attempt)
        return {**report,'workspace':str(root),'execution_status':'recovered' if stale or interrupted else 'generated',
                'supersedes_run_id':metadata['supersedes_run_id'],'changed_source_ids':changed_sources,
                'changed_decision_ids':changed_decisions,'history':None if not previous else 'deliverables/history/'+previous['run_id']}
    except (Exception,KeyboardInterrupt) as exc:
        attempt.update(status='failed',affected_stage=stage,observed_at=now())
        # Error names are controlled: never persist raw source data or exception text.
        codes={'recovery_required','interrupted_attempt_requires_recovery','registered_observations_do_not_match_workbook','unsupported_decision_or_approval_claim','missing_required_headers','ambiguous_record_identity','invalid_numeric_value','missing_required_value','incompatible_quote_status','incompatible_priority','archive_incomplete_requires_review','archive_collision','archive_changed'}
        code='interrupted' if isinstance(exc,KeyboardInterrupt) else str(exc) if str(exc) in codes else 'execution_failed_'+type(exc).__name__
        _failure(root,attempt,code,source,stage)
        _save(root,JOURNAL,attempt)
        raise ValueError('execution_failed; inspect deliverables/failure.json and preserved attempt') from None
