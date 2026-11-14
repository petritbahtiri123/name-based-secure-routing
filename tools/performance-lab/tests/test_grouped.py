"""Schema-derived synthetic fixtures. Never seed these into the real Lab database."""
import copy
import json
import pytest
from fastapi.testclient import TestClient
from lab.app import create_app
from lab.store import Store

SCHEMA = 'nbsr-performance-lab-snapshot-v1'


def progress(index=1, **overrides):
    completed = index * 128
    counters = dict(offered=completed+2, reserved=completed, issued=completed,
                    completed=completed, missed=2, unreserved_current=0)
    row = dict(schema='nbsr-b5-grouped-progress-v1',event='b5_grouped_progress',window_index=index,
        phase='steady',elapsed_ns=index*1_000_000_000,interval_start_ns=(index-1)*1_000_000_000,
        issue_deadline_ns=2_000_000_000,interval_end_ns=index*1_000_000_000,
        **counters,group_counters=[dict(group_id=0,**counters)],goodput_bytes_per_second=128*2048,
        sample_count=2,sample_stride=64,sample_capacity=100,sample_overflow_count=0,
        p50_latency_ns=100000,p95_latency_ns=200000,p99_latency_ns=200000,
        max_reservation_lateness_ns=0,errors=0,timeouts=0,evidence_valid=True)
    row.update(overrides)
    return row


def final():
    p=progress(2)
    return dict(schema='nbsr-b5-grouped-final-v1',groups=1,payload_bytes=1024,
        streams_per_group=2,outstanding_per_stream=1,measurement_duration_ns=2_000_000_000,
        drain_duration_ns=0,**{k:p[k] for k in ('offered','reserved','issued','completed','missed','unreserved_current','group_counters')},
        max_outstanding_observed=2,errors=0,timeouts=0,collector_overflow_count=0,
        all_groups_joined=True,source_cleanup={},evidence_valid=True)


def snapshot(records=None):
    return dict(schema=SCHEMA,metadata={'label':'Synthetic test fixture — not a measurement','implementation':'rust-rust','payload_bytes':1024},
                records=records if records is not None else [progress(),progress(2),final()])


def ingest(tmp_path, obj):
    store=Store(tmp_path)
    result=store.ingest(json.dumps(obj).encode(),'test-only.json')
    return result,store


def test_final_counts_boundaries_and_lineage(tmp_path):
    result,store=ingest(tmp_path,snapshot())
    assert result['status']=='imported'
    run=store.runs()[0]
    assert run['stream']['state']=='final'
    assert run['stream']['validity']=='valid'
    assert run['counts']['completed']=='256'
    assert run['counts']['unstarted']=='2'
    assert run['counts']['started'] is None and run['counts']['incomplete'] is None
    assert run['stream']['source_counters']['issued']=='256'
    assert run['stream']['windows'][0]['record_number']==1
    assert run['stream']['windows'][0]['goodput_mbps_bidirectional']==2.097152
    assert run['goodput_mbps'] is None  # cannot silently reuse per-direction summary metric
    assert run['stream']['windows'][0]['p99_us']==200
    assert any(g['name']=='Cleanup' and g['status']=='unknown' for g in run['gates'])


def test_partial_snapshot_is_not_a_live_or_failed_run(tmp_path):
    _,store=ingest(tmp_path,snapshot([progress()]))
    run=store.runs()[0]
    assert run['stream']['state']=='partial'
    assert run['stream']['elapsed_ns']=='1000000000'
    assert run['duration_s'] is None
    assert run['counts']['unstarted'] is None
    assert run['capacity']=='NOT_ESTABLISHED'


def test_raw_ndjson_final_and_exact_bytes(tmp_path):
    raw=b''.join(json.dumps(r).encode()+b'\n' for r in snapshot()['records'])
    store=Store(tmp_path); result=store.ingest(raw,'test-only.ndjson')
    assert result['status']=='imported'
    run=store.runs()[0]
    assert run['implementation']=='Unknown path'
    assert run['stream']['state']=='final'
    assert store.artifact(result['sha256'])==raw


def test_truncated_tail_retains_complete_lines(tmp_path):
    raw=json.dumps(progress()).encode()+b'\n'+b'{"schema":'
    store=Store(tmp_path); result=store.ingest(raw,'test-only.ndjson')
    assert result['status']=='imported'
    run=store.runs()[0]
    assert run['stream']['state']=='partial'
    assert run['stream']['truncated_tail'] is True
    assert any(g['name']=='Framing' and g['status']=='warn' for g in run['gates'])
    assert store.artifact(result['sha256'])==raw


@pytest.mark.parametrize('tail',[b'{"x":1,"x":2}',b'{"x":NaN}',b'garbage'])
def test_invalid_complete_tail_is_not_silently_dropped(tmp_path,tail):
    raw=json.dumps(progress()).encode()+b'\n'+tail
    result=Store(tmp_path).ingest(raw,'bad.ndjson')
    assert result['status']=='quarantined'


@pytest.mark.parametrize('change', ['counter','sequence','phase','sampling','goodput','group','final_total','post_final'])
def test_semantic_violations_retained_as_invalid(tmp_path,change):
    obj=snapshot()
    if change=='counter': obj['records'][0]['offered']=1
    if change=='sequence': obj['records'][1]['window_index']=3
    if change=='phase': obj['records'][0]['phase']='drain'
    if change=='sampling': obj['records'][0]['sample_count']=3
    if change=='goodput': obj['records'][0]['goodput_bytes_per_second']=123
    if change=='group': obj['records'][0]['group_counters'][0]['completed']=1
    if change=='final_total': obj['records'][2]['completed']=255
    if change=='post_final': obj['records'].append(progress(3))
    result,store=ingest(tmp_path,obj)
    assert result['status']=='imported'
    run=store.runs()[0]
    assert run['stream']['validity']=='invalid'
    assert any(g['status']=='fail' for g in run['gates'])
    assert run['stream']['windows']==[]  # invalid series must not draw plausible trend


def test_failures_and_overflow_are_not_dropped(tmp_path):
    obj=snapshot(); obj['records'][0].update(errors=1,sample_overflow_count=1,evidence_valid=False)
    _,store=ingest(tmp_path,obj)
    run=store.runs()[0]
    assert run['stream']['validity']=='invalid'
    assert run['counts']['failed'] is None


@pytest.mark.parametrize('mutation', ['bool_count','object_phase','unknown_schema','private_metadata'])
def test_unsafe_shapes_quarantined(tmp_path,mutation):
    obj=snapshot()
    if mutation=='bool_count': obj['records'][0]['offered']=True
    if mutation=='object_phase': obj['records'][0]['phase']={}
    if mutation=='unknown_schema': obj['records'][0]['schema']='nbsr-b5-grouped-progress-v99'
    if mutation=='private_metadata': obj['metadata']['ssh_key']='not-a-real-key'
    result,store=ingest(tmp_path,obj)
    assert result['status']=='quarantined'
    assert store.runs()==[]


def test_api_ndjson_and_old_artifacts_survive(tmp_path):
    store=Store(tmp_path); store.ingest(b'{"schema":"future-v99"}','old.json')
    raw=b''.join(json.dumps(r).encode()+b'\n' for r in snapshot()['records'])
    client=TestClient(create_app(tmp_path))
    response=client.post('/api/v1/ingestions',content=raw,headers={'content-type':'application/x-ndjson','x-artifact-name':'test-only.ndjson'})
    assert response.status_code==200
    assert len(client.get('/api/v1/artifacts').json()['artifacts'])==2
    client.post('/api/v1/ingestions',content=raw,headers={'content-type':'application/x-ndjson'})
    assert len(store.runs())==1
    assert client.get('/api/v1/export-contract').json()['mode'].startswith('explicit local import')


def test_drain_phase_is_separate_and_no_sample_is_not_zero(tmp_path):
    p=progress(2); p['phase']='mixed'; p['issue_deadline_ns']=1_500_000_000
    first=progress(); first['issue_deadline_ns']=1_500_000_000
    final_row=final(); final_row['measurement_duration_ns']=1_500_000_000; final_row['drain_duration_ns']=500_000_000
    result,store=ingest(tmp_path,snapshot([first,p,final_row]))
    run=store.runs()[0]
    assert run['stream']['validity']=='valid'
    assert [w['phase'] for w in run['stream']['windows']]==['steady','mixed']
    assert run['duration_s']==1.5 and run['drain_s']==0.5


def test_unsampled_window_retains_null_latency(tmp_path):
    p=progress(); p.update(sample_stride=1000,sample_count=0,p50_latency_ns=None,p95_latency_ns=None,p99_latency_ns=None)
    _,store=ingest(tmp_path,snapshot([p]))
    run=store.runs()[0]
    assert run['stream']['validity']=='valid'
    assert run['stream']['windows'][0]['p99_us'] is None
    assert run['latency']['p99_us'] is None


def test_large_finite_reported_rate_is_serializable(tmp_path):
    row=progress(); row['goodput_bytes_per_second']=1e308
    result,store=ingest(tmp_path,row)  # no payload available to reconcile producer rate
    assert result['status']=='imported'
    run=store.runs()[0]
    assert run['stream']['windows'][0]['goodput_mbps_bidirectional']==8e302
    assert store.artifact(result['sha256'])


@pytest.mark.parametrize('tail',[b'{"schema":"nbsr-',b'{"offered":1e'])
def test_truncation_inside_string_or_number(tmp_path,tail):
    raw=json.dumps(progress()).encode()+b'\n'+tail
    store=Store(tmp_path); result=store.ingest(raw,'partial.ndjson')
    assert result['status']=='imported'
    assert store.runs()[0]['stream']['truncated_tail'] is True


def test_truncation_after_final_invalidates_evidence(tmp_path):
    raw=b''.join(json.dumps(r).encode()+b'\n' for r in snapshot()['records'])+b'{"schema":'
    store=Store(tmp_path); store.ingest(raw,'bad-final.ndjson')
    assert store.runs()[0]['stream']['validity']=='invalid'


def two_group_snapshot():
    obj=snapshot()
    for row in obj['records']:
        group=copy.deepcopy(row['group_counters'][0]); group['group_id']=1
        row['group_counters']=[group,row['group_counters'][0]]  # order deliberately differs from IDs
        for key in ('offered','reserved','issued','completed','missed','unreserved_current'): row[key]*=2
        if row['schema'].endswith('progress-v1'):
            row['sample_count']*=2; row['goodput_bytes_per_second']*=2
        else: row['groups']=2
    return obj


def test_two_groups_reordered_are_valid(tmp_path):
    _,store=ingest(tmp_path,two_group_snapshot())
    assert store.runs()[0]['stream']['validity']=='valid'
    assert store.runs()[0]['counts']['completed']=='512'


def test_per_group_decrease_not_hidden_by_aggregate(tmp_path):
    obj=two_group_snapshot()
    # Shift one group's valid cumulative totals backward and the other's forward.
    for key in ('offered','reserved','issued','completed'):
        obj['records'][1]['group_counters'][0][key]-=200
        obj['records'][1]['group_counters'][1][key]+=200
    _,store=ingest(tmp_path,obj)
    assert store.runs()[0]['stream']['validity']=='invalid'
