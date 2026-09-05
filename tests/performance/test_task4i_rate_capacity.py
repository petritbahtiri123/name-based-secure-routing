from scripts.run_b4b_task4i import classify_cell, ownership_high_water, required_repeats, should_stop, summarize


def cell(*, offered=100, achieved=100, errors=0, timeouts=0, goodput=100, p99=10,
         cleanup=True, cv=0.02):
    return dict(offered_rate=offered, actual_admissions_per_second=achieved,
        achieved_offered_ratio=achieved/offered, errors=errors, timeouts=timeouts,
        established_goodput_bytes_per_second=goodput, established_p99_latency_ns=p99,
        cleanup_pass=cleanup, admission_success_ratio=1.0, repeat_cv=cv)


def test_rate_classification_uses_existing_v2_boundaries():
    baseline=cell(offered=25,achieved=25)
    assert classify_cell(cell(),baseline)=='STABLE'
    assert classify_cell(cell(achieved=92),baseline)=='DEGRADED'
    assert classify_cell(cell(achieved=89),baseline)=='SATURATED'
    assert classify_cell(cell(errors=1),baseline)=='SATURATED'
    assert classify_cell(cell(p99=21),baseline)=='SATURATED'


def test_high_variance_requires_five_repeats():
    records=[dict(established_goodput_bytes_per_second=v,admission_rate=100) for v in (80,100,120)]
    assert required_repeats(records)==5


def test_ownership_high_water_preserves_queue_and_lifecycle_peaks():
    rows=[
        {'transport_sessions_high_water_live':2,'pending_routes_high_water_entries':1,'audit_queue_high_water_entries':4},
        {'transport_sessions_high_water_live':7,'pending_routes_high_water_entries':3,'audit_queue_high_water_entries':9},
    ]
    assert ownership_high_water(rows)=={
        'transport_sessions_high_water_live':7,
        'pending_routes_high_water_entries':3,
        'audit_queue_high_water_entries':9,
    }


def test_summary_never_hides_one_failed_repeat_with_a_median():
    records=[]
    for errors,timeouts,admitted,rate,goodput in ((0,0,512,50,100),(0,0,512,50,120),(1,1,511,49,80)):
        records.append(dict(valid=True,requested_clients=512,started_clients=512,
            connected_clients=admitted,successful_admissions=admitted,failed_admissions=512-admitted,
            errors=errors,timeouts=timeouts,admission_rate=rate,
            handshake_latency_ns={'50':1,'95':2,'99':3},admission_p50_latency_ns=1,
            admission_p95_latency_ns=2,admission_p99_latency_ns=3,
            established_goodput_bytes_per_second=goodput,established_p99_latency_ns=4,
            effective_cores=1,peak_pending_clients=512,
            cleanup={'all_zero':True,'processes_exited':True},resources={'peak_handles':1}))
    result=summarize(50,records)
    assert result['errors']==1 and result['timeouts']==1
    assert result['admission_success_ratio']==511/512
    assert result['repeat_cv'] > .05
    assert result['status'] == 'SATURATED'


def test_isolated_low_rate_failure_does_not_hide_a_later_stable_region():
    assert not should_stop([{'status':'BASELINE'},{'status':'SATURATED'}])
    assert should_stop([{'status':'BASELINE'},{'status':'STABLE'},{'status':'DEGRADED'},{'status':'SATURATED'}])
