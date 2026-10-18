"""Focused venue-source registration checks; live network is never used here."""
import json
from pathlib import Path
from html.parser import HTMLParser
import httpx
from jsonschema import Draft202012Validator,FormatChecker

from event_coordination.capture import retrieve_source
from event_coordination.source_catalog import CATALOG
from event_coordination.source_inventory import load_inventory
from event_coordination.sources import hash_bytes

ROOT=Path(__file__).resolve().parents[1]


def test_assignment_disclosure_and_distinct_source_identity():
    s=CATALOG['official-plenary-hall']
    assert s.role=='venue-page' and s.publication_kind=='real-publication'
    assert s.url!=(CATALOG['official-floor-plan'].url)
    assert s.url in (ROOT/s.disclosure_path).read_text().splitlines()[s.disclosure_line-1]
    assert all(s.url not in p.read_text() for p in (ROOT/'interviews').glob('*.md'))


def test_registered_real_attempts_and_inspection_bytes():
    records=[json.loads(p.read_bytes()) for p in (ROOT/'evidence/captures').glob('capture-official-plenary-hall-*.json')]
    schema=json.loads((ROOT/'snapshot.schema.json').read_bytes())
    validator=Draft202012Validator({'$ref':'#/$defs/sourceRecord','$defs':schema['$defs']},format_checker=FormatChecker())
    for r in records:validator.validate(r)
    assert any(r['retrieval_status']=='unavailable' and r['content_hash'] is None for r in records)
    actual=[r for r in records if r['retrieval_status']=='retrieved']
    assert len(actual)==1
    r=actual[0];raw=(ROOT/r['local_reference']).read_bytes()
    assert hash_bytes(raw)==r['content_hash'] and r['version_metadata']['response_status']==200
    receipt=(ROOT/r['version_metadata']['request_receipt_path']).read_bytes()
    assert hash_bytes(receipt)==r['version_metadata']['request_receipt_sha256']
    assert json.loads(receipt)['id']==r['id']
    class Visible(HTMLParser):
        def __init__(self):super().__init__();self.text=[]
        def handle_data(self,data):self.text.append(data)
    visible=Visible();visible.feed(raw.decode('utf-8'));text=' '.join(visible.text)
    assert len(r['observations'])==5
    for o in r['observations']:
        assert all(fragment in text for fragment in o['source_excerpt'].split(' / '))
    assert all(o['id'].startswith('obs-plenary-') for o in r['observations'])


def test_exact_historical_scope_and_current_complete_inventory():
    old,_=load_inventory(ROOT)
    current,_=load_inventory(ROOT,include_all=True)
    assert len({c['source_identity'] for c in old})==7
    assert {c['source_identity'] for c in current}==set(CATALOG)
    assert len(current)==len(old)+2


def test_retrieval_uses_only_disclosed_url_without_credentials(tmp_path):
    requests=[]
    def respond(request):
        requests.append(request)
        assert str(request.url)==CATALOG['official-plenary-hall'].url
        assert 'authorization' not in request.headers and 'cookie' not in request.headers
        return httpx.Response(200,headers={'content-type':'text/html'},content=b'<html><title>Synthetic Plenary Hall test</title></html>')
    result=retrieve_source(tmp_path,'official-plenary-hall',transport=httpx.MockTransport(respond))
    assert len(requests)==1 and result['retrieval_status']=='retrieved'
    assert hash_bytes((tmp_path/result['local_reference']).read_bytes())==result['content_hash']
