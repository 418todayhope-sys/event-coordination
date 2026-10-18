"""Semantic source comparison: layouts are not business changes; no retrieval."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

from event_coordination.constraint_sources import workbook_rows
from event_coordination.run_contract import _json, _read, relative_path
from event_coordination.sources import hash_bytes
from event_coordination.source_inventory import load_inventory

TABLES = {
 'budget-allocations': ('Budget','category',('category','planned_amount_twd','approval_limit_twd','committed_amount_twd','owner','record_version')),
 'attendee-signals': ('Attendee Signals','signal_id',('signal_id','source','segment','signal','value','unit','observed_at','confidence')),
 'vendor-register': ('Vendor Quotes','quote_id',('quote_id','vendor','category','option','quote_amount_twd','capacity','available_date','valid_until','status','notes')),
 'calendar-constraints': ('Calendar Constraints','constraint_id',('constraint_id','owner','constraint_type','start_at','end_at','priority','notes','record_version')),
}
DECISION_PATH = 'evidence/decision-requests.json'


def table_records(root, capture):
    identity = capture['source_identity']
    sheet, key, required = TABLES[identity]
    rows = workbook_rows(Path(root), capture, sheet, selected_headers=required)
    if not rows: raise ValueError('table_empty')
    headers = {}
    for cell, value in rows[0]['values'].items():
        if value is None: continue
        if type(value) is not str or not value.strip() or value in headers.values():
            raise ValueError('ambiguous_headers')
        headers[re.sub(r'\d+$','',cell)] = value
    if not set(required) <= set(headers.values()): raise ValueError('missing_required_headers')
    if any(any(term in h.casefold() for term in ('approv','authoriz','selected','booking','decision'))
           for h in set(headers.values())-set(required)):
        raise ValueError('unmodeled_business_field_requires_review')
    result, seen = [], set()
    for row in rows[1:]:
        decoded = {headers.get(re.sub(r'\d+$','',cell)): value for cell,value in row['values'].items()}
        values = {name: decoded.get(name) for name in required}
        if any(type(v) is not str or not v.strip() for v in values.values()):
            raise ValueError('missing_required_value')
        identifier = values[key]
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', identifier) or identifier in seen:
            raise ValueError('ambiguous_record_identity')
        seen.add(identifier)
        for name,value in values.items():
            if name.endswith('_twd') or name in ('capacity','value'):
                try: amount=Decimal(value)
                except InvalidOperation: raise ValueError('invalid_numeric_value') from None
                if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
                    raise ValueError('invalid_numeric_value')
            if name in ('available_date','valid_until','observed_at'): date.fromisoformat(value)
            if name in ('start_at','end_at'):
                if datetime.fromisoformat(value).utcoffset() is None: raise ValueError('missing_timezone')
        if identity=='vendor-register' and values['status'] not in ('available','held','conditional'):
            raise ValueError('incompatible_quote_status')
        if identity=='calendar-constraints' and values['priority'] not in ('hard','soft'):
            raise ValueError('incompatible_priority')
        required_cells={c:v for c,v in row['raw'].items() if headers.get(re.sub(r'\d+$','',c)) in required}
        row_numbers={re.search(r'\d+$',c)[0] for c in required_cells}
        if len(row_numbers)!=1: raise ValueError('ambiguous_cell_row')
        number=next(iter(row_numbers))
        # Explicit list of actual cells remains valid under column reordering.
        locator=f"'{sheet}'!" + ','.join(required_cells)
        result.append({'identity':identifier, 'values':values, 'raw':required_cells,
                       'locator':locator, 'row_number':int(number)})
    if not result: raise ValueError('table_empty')
    return sorted(result,key=lambda r:r['identity'])


def request_records(root):
    root=Path(root)
    if not (root/DECISION_PATH).exists(): return []
    content,_=_read(root,DECISION_PATH)
    records=_json(content)
    if type(records) is not list: raise ValueError('invalid_decision_requests')
    seen=set()
    for r in records:
        if (type(r) is not dict or set(r)!={'id','summary','status'} or r['status']!='proposed'
                or type(r['id']) is not str or not re.fullmatch(r'request-[A-Za-z0-9_-]+',r['id'])
                or r['id'] in seen or type(r['summary']) is not str or not r['summary'].strip()):
            raise ValueError('unsupported_decision_or_approval_claim')
        seen.add(r['id'])
    return sorted(records,key=lambda r:r['id'])


def semantic_manifest(root):
    root=Path(root)
    captures,_=load_inventory(root,include_all=True)
    sources={}
    for identity in sorted({c['source_identity'] for c in captures}):
        selected=[c for c in captures if c['source_identity']==identity and c['local_reference']]
        if identity in TABLES:
            if len(selected)!=1: raise ValueError('ambiguous_table_representation')
            rows=table_records(root,selected[0]); records=[]
            prefixes={'vendor-register':'obs-quote-', 'attendee-signals':'obs-attendee-', 'calendar-constraints':'obs-calendar-'}
            if identity in prefixes:
                index={o['id']:o for o in selected[0]['observations']}
                for row in rows:
                    obs=index.get(prefixes[identity]+row['identity'].lower())
                    raw=None if obs is None else obs.get('raw_cell_values',obs.get('original_cell_values'))
                    if raw is None or any(raw.get(k)!=v for k,v in row['raw'].items()):
                        raise ValueError('registered_observations_do_not_match_workbook')
            for row in rows:
                v=dict(row['values'])
                for k in v:
                    if k.endswith('_twd') or k in ('capacity','value'): v[k]=str(Decimal(v[k]).quantize(Decimal(1)))
                records.append(v)
            if identity=='budget-allocations':
                for row in rows:
                    v=row['values']
                    expected=(f"Category {v['category']}; planned TWD {v['planned_amount_twd']}; approval limit TWD {v['approval_limit_twd']}; "
                              f"committed TWD {v['committed_amount_twd']}; owner {v['owner']}; record version {v['record_version']}.")
                    matches=[o for o in selected[0]['observations'] if o['summary']==expected]
                    if len(matches)!=1: raise ValueError('registered_observations_do_not_match_workbook')
            body={'records':records}
        else:
            body={'representations':sorted((c['local_reference'],c['content_hash']) for c in selected)}
        # Retrieval/provenance changes matter; coordinate and export-layout changes do not.
        body['limitations'] = sorted((json.dumps({k:c['version_metadata'].get(k) for k in
            ('reason','limitations','conditions','completeness','online_equivalence','privacy','possible_interpretations_not_resolutions')},sort_keys=True)
            for c in captures if c['source_identity']==identity))
        body['retrieval_states']=sorted((c['retrieval_status'],c['version_metadata']['publication_kind'])
                                         for c in captures if c['source_identity']==identity)
        sources[identity]={'sha256':hash_bytes(json.dumps(body,sort_keys=True,separators=(',',':')).encode())}
    requests=request_records(root)
    decisions={r['id']:hash_bytes(json.dumps(r,sort_keys=True,separators=(',',':')).encode()) for r in requests}
    return {'version':1,'sources':sources,'decisions':decisions}


def meaningful_changes(old,new):
    if type(old) is not dict or old.get('version')!=1 or new.get('version')!=1:
        raise ValueError('unsupported_manifest')
    def diff(kind):
        return sorted(k for k in old[kind].keys()|new[kind].keys() if old[kind].get(k)!=new[kind].get(k))
    return diff('sources'),diff('decisions')
