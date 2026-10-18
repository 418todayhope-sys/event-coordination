"""Focused local execution/recovery tests. All source mutations are synthetic copies."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from event_coordination import execution, pipeline
from event_coordination.constraint_sources import NS
from event_coordination.input_changes import semantic_manifest, meaningful_changes, table_records, request_records
from event_coordination.sources import hash_bytes
from event_coordination.stages import drafts, publication

ROOT=Path(__file__).resolve().parents[1]
URI='http://schemas.openxmlformats.org/spreadsheetml/2006/main'


def copy_source(target):
    target.mkdir()
    for name in ('evidence','interviews'): shutil.copytree(ROOT/name,target/name)
    shutil.copyfile(ROOT/'snapshot.schema.json',target/'snapshot.schema.json')
    return target


def revise_vendor(root, *, delta=0, layout=False, bad=None):
    """Synthetic export/registration revision; never a real offer or retrieval."""
    capture_path=next((root/'evidence/captures').glob('capture-vendor*'))
    capture=json.loads(capture_path.read_bytes())
    workbook=root/capture['local_reference']
    before=workbook.read_bytes(); old_capture=capture_path.read_bytes()
    with ZipFile(workbook) as z: parts={p:z.read(p) for p in z.namelist()}
    tree=ET.fromstring(parts['xl/worksheets/sheet1.xml'])
    data=tree.find('s:sheetData',NS); rows=list(data)
    if delta:
        cell=rows[3].find("s:c[@r='E4']/s:v",NS)
        cell.text=str(float(cell.text)+delta)
    if bad=='value': rows[3].find("s:c[@r='E4']/s:v",NS).text='NaN'
    if bad=='duplicate':
        rows[3].find("s:c[@r='A4']",NS).clear()
        cell=rows[3].find('s:c',NS);cell.set('r','A4');cell.set('t','s')
        ET.SubElement(cell,'{'+URI+'}v').text=rows[2].find("s:c[@r='A3']/s:v",NS).text
    if bad=='missing-header':
        rows[0].remove(rows[0].find("s:c[@r='E1']",NS))
    if bad=='duplicate-header':
        header=rows[0].find("s:c[@r='E1']",NS)
        header.find('s:v',NS).text=rows[0].find("s:c[@r='A1']/s:v",NS).text
    if layout:
        data.clear()
        rows=[rows[0],*reversed(rows[1:])]
        for n,row in enumerate(rows,1):
            cells=list(row);row.clear();row.set('r',str(n))
            for k,cell in enumerate(reversed(cells)):
                cell.set('r',chr(65+k)+str(n));row.append(cell)
            extra=ET.SubElement(row,'{'+URI+'}c',{'r':'K'+str(n),'t':'inlineStr'})
            ET.SubElement(ET.SubElement(extra,'{'+URI+'}is'),'{'+URI+'}t').text='export_comment' if n==1 else 'unrelated fixture annotation'
            data.append(row)
    parts['xl/worksheets/sheet1.xml']=ET.tostring(tree)
    with ZipFile(workbook,'w') as z:
        for name,content in parts.items(): z.writestr(name,content)
    attempts=root/'evidence/attempts'/str(uuid4());attempts.mkdir(parents=True)
    (attempts/'prior-capture.json').write_bytes(old_capture)
    (attempts/workbook.name).write_bytes(before)
    capture['id']='capture-vendor-register-local-'+str(uuid4())
    capture['content_hash']=hash_bytes(workbook.read_bytes())
    capture['version_metadata']['size_bytes']=workbook.stat().st_size
    capture['retrieved_at']=datetime.now(timezone.utc).isoformat()
    capture['version_metadata']['registration_at']=capture['retrieved_at']
    capture['version_metadata']['prior_capture_path']=str((attempts/'prior-capture.json').relative_to(root))
    capture['version_metadata']['revision_origin']='SYNTHETIC TEST FIXTURE; not a real vendor quote or remote retrieval'
    if not bad:
        by_id={o['id']:o for o in capture['observations']}
        for row in table_records(root,capture):
            obs=by_id['obs-quote-'+row['identity'].lower()]
            obs['raw_cell_values']=row['raw']
            obs['locator']['value']=row['locator']
            obs['summary']='; '.join(k+': '+v for k,v in row['values'].items())
    capture_path.write_text(json.dumps(capture,indent=2))


@pytest.mark.parametrize('bad',['value','duplicate','missing-header','duplicate-header'])
def test_invalid_or_ambiguous_table_fails(tmp_path,bad):
    source=copy_source(tmp_path/'source');revise_vendor(source,bad=bad)
    with pytest.raises((ValueError,KeyError)): semantic_manifest(source)


def test_combined_row_header_and_extra_column_equivalence(tmp_path):
    source=copy_source(tmp_path/'source');old=semantic_manifest(source)
    revise_vendor(source,layout=True)
    assert meaningful_changes(old,semantic_manifest(source))==([],[])


def test_unsupported_approval_rejected(tmp_path):
    source=copy_source(tmp_path/'source')
    (source/'evidence/decision-requests.json').write_text(json.dumps([{'id':'request-approve','summary':'Synthetic','status':'approved'}]))
    with pytest.raises(ValueError,match='unsupported'): request_records(source)


def test_failure_receipt_and_interrupted_attempt_preserved(tmp_path,monkeypatch):
    source=copy_source(tmp_path/'source')
    def interrupted(src,dest,**kwargs):
        dest.mkdir();(dest/'partial.txt').write_text('synthetic partial task evidence')
        kwargs['progress'](4,kwargs['metadata']['run_id'])
        raise KeyboardInterrupt()
    monkeypatch.setattr(pipeline,'run_stages',interrupted)
    target=tmp_path/'run'
    with pytest.raises(ValueError): execution.execute(source,target)
    failure=json.loads((target/execution.FAILURE).read_bytes())
    assert failure['error']=='interrupted' and failure['affected_stage']==4
    assert set(('run_id','observed_at','error','affected_stage','available_evidence','affected_artifacts','next_owner','recovery_action'))<=failure.keys()
    assert (target/failure['attempt_workspace']/'partial.txt').read_text()=='synthetic partial task evidence'
    assert list((target/'deliverables/failures').glob('*.json'))
    with pytest.raises(ValueError): execution.execute(source,target)
    assert len(list((target/'deliverables/failures').glob('*.json')))>=2


def test_unmanaged_workspace_and_symlink_refused(tmp_path):
    source=copy_source(tmp_path/'source')
    target=tmp_path/'unmanaged';target.mkdir();(target/'valuable.txt').write_text('preserve')
    with pytest.raises(ValueError): execution.execute(source,target)
    alias=tmp_path/'alias';alias.symlink_to(target,target_is_directory=True)
    with pytest.raises(ValueError): execution.execute(source,alias)
    assert (target/'valuable.txt').read_text()=='preserve'


def test_real_changed_rerun_history_and_corrupt_output_recovery(tmp_path):
    supplied=os.environ.get('PROJECT_C_EXECUTION_BASIS')
    target=tmp_path/'run'
    if supplied: shutil.copytree(supplied,target)
    else: execution.execute(ROOT,target)
    first=json.loads((target/execution.MANIFEST).read_bytes())
    source=copy_source(tmp_path/'source')
    revise_vendor(source,layout=True)
    unchanged=execution.execute(source,target)
    assert unchanged['execution_status']=='unchanged-equivalent-inputs' and unchanged['run_id']==first['run_id']
    # A real semantic revision, combined with all three harmless layout changes.
    source2=copy_source(tmp_path/'revision')
    revise_vendor(source2,delta=1000,layout=True)
    (source2/'evidence/decision-requests.json').write_text(json.dumps([
        {'id':'request-review-cost','summary':'Synthetic review request only; not a learner approval.','status':'proposed'}]))
    changed=execution.execute(source2,target)
    assert changed['run_id']!=first['run_id'] and changed['supersedes_run_id']==first['run_id']
    assert changed['changed_source_ids']==['vendor-register'] and changed['changed_decision_ids']==['request-review-cost']
    archive=target/changed['history']
    for p,h in first['files'].items(): assert hash_bytes((archive/p).read_bytes())==h
    s1=json.loads((target/pipeline.scope.OUTPUT).read_bytes())
    assert s1['state']['run_metadata']['supersedes_run_id']==first['run_id']
    assert s1['state']['decision_requests'][0]['status']=='proposed'
    import csv
    rows=list(csv.DictReader((target/drafts.ARTIFACT_PATHS[0]).open()))
    assert [r['cost_twd'] for r in rows if r['row_type']=='candidate']==['495000','512000']
    valid=json.loads((target/execution.MANIFEST).read_bytes())
    victim=target/drafts.ARTIFACT_PATHS[0];victim.write_bytes(b'synthetic corruption')
    with pytest.raises(ValueError): execution.execute(source2,target)
    failure=json.loads((target/execution.FAILURE).read_bytes())
    assert failure['status']=='failed' and victim.read_bytes()==b'synthetic corruption'
    recovered=execution.execute(source2,target,recover=True)
    assert recovered['execution_status']=='recovered' and recovered['run_id']!=changed['run_id']
    assert recovered['supersedes_run_id']==changed['run_id']
    partial=target/recovered['history']
    assert json.loads((partial/'archive.json').read_bytes())['integrity_status']=='incomplete-or-corrupt-copy'
    assert (partial/drafts.ARTIFACT_PATHS[0]).read_bytes()==b'synthetic corruption'
    assert [r['cost_twd'] for r in csv.DictReader(victim.open()) if r['row_type']=='candidate']==['495000','512000']
    execution.validate_run(target,json.loads((target/execution.MANIFEST).read_bytes()))
    assert all(g['status']=='pending' for g in json.loads((target/publication.OUTPUT).read_bytes())['state']['approval_requirements'])
    # Missing output is also detected; no silently trusted current manifest.
    missing=tmp_path/'missing-output-copy';shutil.copytree(target,missing)
    (missing/drafts.ARTIFACT_PATHS[0]).unlink()
    with pytest.raises(ValueError): execution.execute(source2,missing)
    assert not (missing/drafts.ARTIFACT_PATHS[0]).exists() and json.loads((missing/execution.FAILURE).read_bytes())['status']=='failed'
    assert victim.is_file()


def test_changed_interview_is_not_hidden_by_spreadsheet_equivalence(tmp_path):
    source=copy_source(tmp_path/'source')
    m=semantic_manifest(source)
    path='interviews/project-c-event-coordination-20261016-2056.md'
    previous={'semantic_inputs':m,'files':{path:hash_bytes((source/path).read_bytes())}}
    with (source/path).open('ab') as stream: stream.write(b'\nSynthetic test evidence change')
    changed_sources,changed_decisions=execution.detect_changes(previous,source,semantic_manifest(source))
    assert changed_sources==[] and len(changed_decisions)==1


def test_dead_lock_requires_explicit_recovery_and_is_preserved(tmp_path,monkeypatch):
    import socket
    source=copy_source(tmp_path/'source');target=tmp_path/'run';target.mkdir()
    pipeline._mkdir(target,'deliverables')
    attempt={'attempt_id':str(uuid4()),'run_id':str(uuid4()),'candidate':'.attempts/synthetic/candidate',
             'status':'running','affected_stage':3}
    execution._save(target,execution.JOURNAL,attempt)
    pipeline._copy_bytes(target,'.execution-lock',json.dumps({'pid':123456789,'host':socket.gethostname()}).encode())
    def dead(pid,sig): raise ProcessLookupError()
    monkeypatch.setattr(os,'kill',dead)
    with pytest.raises(ValueError): execution.execute(source,target)
    def stop(*args,**kwargs): raise ValueError('synthetic_failure')
    monkeypatch.setattr(pipeline,'run_stages',stop)
    with pytest.raises(ValueError): execution.execute(source,target,recover=True)
    assert list((target/'.attempts').glob('stale-lock-*.json'))
    assert not (target/'.execution-lock').exists()
    assert json.loads((target/execution.FAILURE).read_bytes())['status']=='failed'


def test_unrelated_formula_column_is_not_evaluated(tmp_path):
    source=copy_source(tmp_path/'source');before=semantic_manifest(source)
    revise_vendor(source,layout=True)
    cp=next((source/'evidence/captures').glob('capture-vendor*'));c=json.loads(cp.read_bytes());p=source/c['local_reference']
    with ZipFile(p) as z: parts={n:z.read(n) for n in z.namelist()}
    tree=ET.fromstring(parts['xl/worksheets/sheet1.xml'])
    cell=tree.find("s:sheetData/s:row/s:c[@r='K2']",NS)
    # ElementTree path above traverses all rows; identify by coordinate, not order.
    if cell is None: cell=next(c for c in tree.findall('.//s:c',NS) if c.get('r')=='K2')
    cell.clear();cell.set('r','K2');ET.SubElement(cell,'{'+URI+'}f').text='1+1'
    parts['xl/worksheets/sheet1.xml']=ET.tostring(tree)
    with ZipFile(p,'w') as z:
        for n,b in parts.items(): z.writestr(n,b)
    c['content_hash']=hash_bytes(p.read_bytes());c['version_metadata']['size_bytes']=p.stat().st_size;cp.write_text(json.dumps(c))
    assert meaningful_changes(before,semantic_manifest(source))==([],[])


def test_unmodeled_approval_column_is_not_silently_accepted(tmp_path):
    source=copy_source(tmp_path/'source');revise_vendor(source,layout=True)
    cp=next((source/'evidence/captures').glob('capture-vendor*'));c=json.loads(cp.read_bytes());p=source/c['local_reference']
    with ZipFile(p) as z: parts={n:z.read(n) for n in z.namelist()}
    tree=ET.fromstring(parts['xl/worksheets/sheet1.xml'])
    header=next(c for c in tree.findall('.//s:c',NS) if c.get('r')=='K1')
    header.find('s:is/s:t',NS).text='approval_status'
    parts['xl/worksheets/sheet1.xml']=ET.tostring(tree)
    with ZipFile(p,'w') as z:
        for n,b in parts.items(): z.writestr(n,b)
    c['content_hash']=hash_bytes(p.read_bytes());c['version_metadata']['size_bytes']=p.stat().st_size;cp.write_text(json.dumps(c))
    with pytest.raises(ValueError,match='unmodeled_business_field'): semantic_manifest(source)
