from scripts.run_b4b_task4g import observer_gate


def base_record():
    return dict(valid=True, successful_admissions=128, requested_clients=128,
                admission_rate=50, established_goodput_bytes_per_second=100,
                **{f'{kind}_p{p}_latency_ns': 10 for kind in ('established','admission') for p in (50,95,99)},
                handshake_latency_ns={'50':10,'95':10,'99':10},cleanup={'all_zero':True})


def test_observer_gate_rejects_distortion_and_success_shift():
    base = base_record()
    assert observer_gate([base]*3, [base]*3)['pass']
    assert not observer_gate([base]*3, [dict(base, admission_rate=54)]*3)['pass']
    assert not observer_gate([base]*3, [dict(base, successful_admissions=126)]*3)['pass']


def test_gate_rejects_missing_latency_and_incomplete_high_variance_pairs():
    base=base_record()
    missing=dict(base)
    del missing['admission_p95_latency_ns']
    assert not observer_gate([missing]*3,[missing]*3)['pass']
    noisy=[dict(base,admission_rate=v) for v in (50,60,50)]
    assert not observer_gate(noisy,noisy)['pass']
