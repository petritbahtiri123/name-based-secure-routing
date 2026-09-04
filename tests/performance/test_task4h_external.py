from pathlib import Path

from scripts.run_b4b_mixed_connections import lifecycle_client_command, lifecycle_server_environment
from scripts.performance.external_packet_capture import flow_table
from scripts.run_b4b_task4h import observer_gate


def command(batch=None, interval=None, rate=None):
    return lifecycle_client_command(Path('source'), '127.0.0.1:4444', Path('a'), Path('l'),
        connections=1, offset=0, logical_clients=256,
        release_batch=batch, release_interval_ms=interval, release_rate=rate)


def test_disabled_batch_release_keeps_existing_command():
    argv=command()
    assert '--lifecycle-release-batch' not in argv
    assert '--lifecycle-release-interval-ms' not in argv


def test_batched_release_supplies_exact_pair():
    argv=command(16,25)
    assert argv[argv.index('--lifecycle-release-batch')+1]=='16'
    assert argv[argv.index('--lifecycle-release-interval-ms')+1]=='25'


def test_partial_release_configuration_is_rejected():
    import pytest
    with pytest.raises(ValueError): command(8,None)


def test_rate_release_is_mutually_exclusive_and_exact():
    argv=command(rate=125)
    assert argv[argv.index('--lifecycle-offered-rate')+1]=='125'
    import pytest
    with pytest.raises(ValueError): command(8,25,125)


def test_disabled_rate_does_not_set_destination_schedule_environment():
    assert 'NBSR_PERF_LIFECYCLE_OFFERED_RATE' not in lifecycle_server_environment({},None)
    assert lifecycle_server_environment({},125)['NBSR_PERF_LIFECYCLE_OFFERED_RATE']=='125'


def test_udp_flows_remain_port_based_without_client_id_invention():
    packets=[
        dict(timestamp=1.0,src='127.0.0.1',srcport=50000,dst='127.0.0.1',dstport=4444,packet_type='0'),
        dict(timestamp=1.1,src='127.0.0.1',srcport=4444,dst='127.0.0.1',dstport=50000,packet_type='0'),
        dict(timestamp=2.0,src='127.0.0.1',srcport=50001,dst='127.0.0.1',dstport=4444,packet_type='0'),
    ]
    flows=flow_table(packets,4444)
    assert flows[0]['client_port']==50000 and flows[0]['first_reply_timestamp']==1.1
    assert flows[1]['client_port']==50001 and flows[1]['first_reply_timestamp'] is None
    assert all('client_id' not in flow for flow in flows)


def metric_record(success=256,rate=40,goodput=100,p99=20):
    return dict(valid=True,requested_clients=256,successful_admissions=success,
        admission_rate=rate,established_goodput_bytes_per_second=goodput,
        admission_p95_latency_ns=10,admission_p99_latency_ns=p99,
        established_p95_latency_ns=10,established_p99_latency_ns=p99,
        handshake_latency_ns={'95':10,'99':p99},cleanup={'all_zero':True})


def test_capture_gate_is_absolute_and_fail_closed():
    base=metric_record()
    assert observer_gate([base]*3,[base]*3)['pass']
    assert not observer_gate([base]*3,[metric_record(success=250)]*3)['pass']
    assert not observer_gate([base]*3,[metric_record(rate=44)]*3)['pass']
