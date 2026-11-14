import hashlib
import json
import pytest
from fastapi.testclient import TestClient
from lab.adapters import normalize, decode
from lab.store import Store
from lab.app import create_app


def summary():
    return {"schema":"nbsr-sphere-controlled-load-summary-v1", "date":"2026-10-19",
        "shape":{"aggregate_offered_operations_per_second":8000,"request_bytes":1024,"response_bytes":1024},
        "measurement":{"measurement_seconds":300,"offered_operations":2400000,"completed_operations":2397718,
            "missed_offer_slots":2282,"errors":0,"timeouts":0,
            "median_window_quantiles_us":{"p99":212.049},"capacity":"NOT_ESTABLISHED"}}


def test_summary_counts_and_boundaries():
    run = normalize(summary())[0]
    assert run['counts']['offered'] == '2400000'
    assert run['counts']['completed'] == '2397718'
    assert run['counts']['unstarted'] == '2282'
    assert run['counts']['started'] is None
    assert run['counts']['incomplete'] is None
    assert run['latency']['p99_us'] == 212.049
    assert run['evidence'] == 'summary_only'
    assert 'window' in run['latency']['scope']
    assert run['capacity'] == 'NOT_ESTABLISHED'


def test_bad_counts_not_accepted():
    obj = summary(); obj['measurement']['completed_operations'] = 2400001
    run = normalize(obj)[0]
    assert any(g['status'] == 'fail' for g in run['gates'])


def test_missing_is_not_zero():
    obj = summary(); del obj['measurement']['errors']
    assert normalize(obj)[0]['counts']['failed'] is None


@pytest.mark.parametrize('raw', [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b'[]'])
def test_unsafe_json(raw):
    with pytest.raises(ValueError): decode(raw)


def test_store_deduplicates_and_preserves_bytes(tmp_path):
    store = Store(tmp_path); raw = json.dumps(summary(),indent=2).encode()
    a = store.ingest(raw, 'fixture.json'); b = store.ingest(raw, 'again.json')
    assert a['sha256'] == b['sha256'] == hashlib.sha256(raw).hexdigest()
    assert len(store.runs()) == 1
    assert store.artifact(a['sha256']) == raw


def test_unknown_schema_retained(tmp_path):
    store = Store(tmp_path); raw = b'{"schema":"future-v99"}'
    result = store.ingest(raw, 'future.json')
    assert result['status'] == 'quarantined'
    assert store.artifact(result['sha256']) == raw
    assert store.runs() == []


def test_tampered_raw_detected(tmp_path):
    store = Store(tmp_path); result = store.ingest(json.dumps(summary()).encode(),'a.json')
    sha=result['sha256']; (tmp_path/'sha256'/sha[:2]/sha).write_bytes(b'changed')
    with pytest.raises(ValueError,match='integrity'): store.artifact(sha)


def test_sampling_not_invented_and_zero_duration_preserved():
    run = normalize(summary())[0]
    assert 'not recorded' in run['latency']['scope']
    run = normalize({'schema':'nbsr-p2a-repeat-v2','path':'direct','measured_ns':0})[0]
    assert run['duration_s'] == 0


def test_legacy_summary_quantiles_use_container_unit():
    obj=summary(); del obj['measurement']['median_window_quantiles_us']
    obj['measurement']['latency_median_of_window_quantiles_us']={'p99_latency_ns':224.847}
    obj['measurement']['drift_flags']=[{'reason':'p99','window':30}]
    run=normalize(obj)[0]
    assert run['latency']['p99_us'] == 224.847
    assert any(g['name']=='Latency drift' and g['status']=='warn' for g in run['gates'])


def test_p2a_has_no_invented_offered():
    run = normalize({'schema':'nbsr-p2a-repeat-v2','path':'direct','completed_operations':12,'measured_ns':1000000000,'p99_latency_ns':250000})[0]
    assert run['counts']['offered'] is None
    assert run['counts']['completed'] == '12'
    assert run['latency']['p99_us'] == 250
    assert run['implementation'] == 'Direct QUIC'


@pytest.mark.parametrize('field,value', [('date',{}),('topology',[]),('shape',None)])
def test_bad_presentation_types_quarantined(tmp_path, field, value):
    obj = summary(); obj[field] = value
    assert Store(tmp_path).ingest(json.dumps(obj).encode(), 'bad.json')['status'] == 'quarantined'


def test_null_resources_quarantined(tmp_path):
    obj = summary(); obj['measurement']['interface_and_resource_guards'] = None
    assert Store(tmp_path).ingest(json.dumps(obj).encode(), 'bad.json')['status'] == 'quarantined'


def test_api_import_and_origin_boundary(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get('/api/v1/runs').json()['runs'] == []
    response = client.post('/api/v1/ingestions',content=json.dumps(summary()),headers={'content-type':'application/json'})
    assert response.status_code == 200
    assert len(client.get('/api/v1/runs').json()['runs']) == 1
    blocked = client.post('/api/v1/ingestions',content='{}',headers={'origin':'https://evil.example','content-type':'application/json'})
    assert blocked.status_code == 403
    assert client.get('/api/v1/artifacts/../../README.md').status_code == 404
