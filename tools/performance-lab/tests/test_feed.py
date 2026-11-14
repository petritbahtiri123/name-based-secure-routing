import json
import time
import pytest
from fastapi.testclient import TestClient
from lab.feed import Inbox, export
from lab.store import Store
from lab.app import create_app
from lab.adapters import normalize
from tests.test_grouped import snapshot, progress, final


def publish(tmp_path, records, experiment='synthetic-test-only'):
    source=tmp_path/'reviewed.json'
    source.write_text(json.dumps(snapshot(records)),encoding='utf-8')
    export(source,tmp_path/'inbox',experiment)
    return source


def test_delivery_advances_deduplicates_finalizes_and_retains_bytes(tmp_path):
    inbox=Inbox(Store(tmp_path/'data'),tmp_path/'inbox')
    source=publish(tmp_path,[progress()]); raw=source.read_bytes()
    inbox.scan()
    assert inbox.status()['feeds'][0]['state']=='waiting'
    assert inbox.store.artifact(inbox.status()['feeds'][0]['sha256'])==raw
    assert export(source,tmp_path/'inbox','synthetic-test-only') is False
    publish(tmp_path,[progress(),progress(2)]);inbox.scan()
    assert inbox.status()['feeds'][0]['state']=='receiving'
    with inbox.store.connect() as db: db.execute('UPDATE deliveries SET received=?',(time.time()-40,))
    assert inbox.status()['feeds'][0]['state']=='stale'
    publish(tmp_path,[progress(),progress(2),final()]);inbox.scan()
    assert inbox.status()['feeds'][0]['state']=='final'
    inbox.scan()
    assert inbox.status()['feeds'][0]['updates']==3
    assert len(inbox.store.runs())==3


def test_changed_prefix_rejected_and_bad_packet_does_not_block_valid(tmp_path):
    inbox=Inbox(Store(tmp_path/'data'),tmp_path/'inbox')
    publish(tmp_path,[progress()]);inbox.scan()
    publish(tmp_path,[progress(p50_latency_ns=90000),progress(2)])
    (tmp_path/'inbox'/'bad.packet').write_text('garbage')
    publish(tmp_path,[progress()],'other-test')
    inbox.scan()
    assert inbox.error
    assert len(inbox.status()['feeds'])==2
    assert all(f['updates']==1 for f in inbox.status()['feeds'])


def test_hash_conflict_and_partial_export_rejected(tmp_path):
    inbox=Inbox(Store(tmp_path/'data'),tmp_path/'inbox')
    source=publish(tmp_path,[progress()])
    packet=json.loads(next((tmp_path/'inbox').glob('*.packet')).read_bytes())
    packet['sha256']='0'*64
    with pytest.raises(ValueError,match='hash'): inbox.accept(json.dumps(packet).encode())
    source.write_bytes(json.dumps(progress()).encode()+b'\n{"schema":')
    with pytest.raises(ValueError): export(source,tmp_path/'inbox','partial')
    assert inbox.status()['feeds']==[]


def test_lifespan_consumes_local_inbox_without_http_write(tmp_path):
    publish(tmp_path,[progress()])
    with TestClient(create_app(tmp_path/'data',tmp_path/'inbox')) as client:
        for _ in range(100):
            result=client.get('/api/v1/feed').json()
            if result['feeds']: break
            time.sleep(.02)
        assert result['feeds'][0]['state']=='waiting'
        assert len(client.get('/api/v1/runs').json()['runs'])==1


def test_legacy_provenance_is_mapped_without_invented_start_count():
    obj=dict(schema='nbsr-sphere-controlled-load-summary-v1',measured_source_base='base',
             measured_sender_patch_sha256='patch',provenance_note='source note',
             measurement=dict(raw_sha256={'source':'digest'},completed_operations=2))
    run=normalize(obj)[0]
    assert run['provenance']['measured_source_base']=='base'
    assert run['provenance']['measured_sender_patch_sha256']=='patch'
    assert run['provenance']['referenced_raw_sha256_unverified']=={'source':'digest'}
    assert run['counts']['started'] is None and run['counts']['incomplete'] is None


def test_invalid_measurement_is_delivered_and_not_hidden(tmp_path):
    inbox=Inbox(Store(tmp_path/'data'),tmp_path/'inbox')
    publish(tmp_path,[progress()]);inbox.scan()
    publish(tmp_path,[progress(),progress(2,errors=1,evidence_valid=False)])
    inbox.scan()
    assert inbox.status()['feeds'][0]['state']=='invalid'
    assert inbox.status()['feeds'][0]['updates']==2
    assert inbox.store.runs()[0]['stream']['validity']=='invalid'


def test_unchanged_packets_are_not_read_again(tmp_path,monkeypatch):
    inbox=Inbox(Store(tmp_path/'data'),tmp_path/'inbox')
    publish(tmp_path,[progress()]);inbox.scan()
    monkeypatch.setattr('lab.feed.read_bounded',lambda *args:pytest.fail('Unchanged packet reread'))
    inbox.scan()
    assert inbox.error is None
