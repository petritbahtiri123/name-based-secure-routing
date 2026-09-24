import io
import json

import pytest

from tests.performance.test_linux_native_finite_endpoint import args
from tests.performance.test_linux_native_paced import transcript


def paired_args(tmp_path, role):
    value = args(tmp_path, role)
    value.paired_live_guards = value.post_close_reports = True
    value.source_live_guard = role == 'source'
    value.diagnostic_rate = [100, 1]
    value.payload = 1024
    return value


def test_paired_config_binds_both_endpoints_without_changing_source_only_mode():
    from scripts.performance.linux_native_finite_run import validate_config, endpoint_arguments
    from tests.performance.test_linux_native_finite_run import config
    row = config() | dict(post_close_reports=True, diagnostic_rate=[100, 1],
                          source_live_guard=True, paired_live_guards=True)
    validate_config(row)
    for role in ('source', 'destination'):
        assert '--paired-live-guards' in endpoint_arguments(row, role)
    with pytest.raises(ValueError):
        validate_config(row | {'source_live_guard': False})


def test_source_endpoint_emits_telemetry_before_complete(tmp_path, monkeypatch):
    from scripts.performance import linux_native_finite_endpoint as endpoint
    monkeypatch.setattr(endpoint.platform, 'system', lambda: 'Linux')
    def reader(stream, messages, stop):
        messages.put(b'{"op":"readiness","value":{"endpoint":"192.0.2.2:1234","alpn":"nbsr-quic-1"}}\n')
        stop.wait(2)
    monkeypatch.setattr(endpoint, 'read_commands', reader)
    def delegate(item, check_cancelled, live_events):
        item.output.mkdir()
        for row in transcript():
            live_events('paced_final' if row['schema'].endswith('final-v1') else 'paced_progress', row)
        return dict(exit_code=0)
    output = io.StringIO()
    endpoint.execute_endpoint(paired_args(tmp_path, 'source'), input_stream=io.BytesIO(),
                              output_stream=output, delegate=delegate)
    events = [json.loads(line)['event'] for line in output.getvalue().splitlines()]
    assert events == ['owned', 'readiness_transferred', *(['paced_progress']*4), 'paced_final', 'complete']


def test_destination_ack_cannot_precede_telemetry_final(tmp_path, monkeypatch):
    from scripts.performance import linux_native_finite_endpoint as endpoint
    monkeypatch.setattr(endpoint.platform, 'system', lambda: 'Linux')
    def reader(stream, messages, stop):
        messages.put(b'{"op":"ack"}\n')
        stop.wait(2)
    monkeypatch.setattr(endpoint, 'read_commands', reader)
    def delegate(item, check_cancelled, destination_observer_factory):
        item.output.mkdir()
        (item.output/'ready.json').write_text(json.dumps(dict(endpoint='192.0.2.2:1234', alpn='nbsr-quic-1')))
        check_cancelled()
        pytest.fail('early ACK accepted')
    with pytest.raises(ValueError, match='telemetry'):
        endpoint.execute_endpoint(paired_args(tmp_path, 'destination'), input_stream=io.BytesIO(),
                                  output_stream=io.StringIO(), delegate=delegate)
    assert not (tmp_path/'out/peer/completion.ack').exists()


def test_destination_receives_all_telemetry_before_ack_and_reports_local_guard(tmp_path, monkeypatch):
    from scripts.performance import linux_native_finite_endpoint as endpoint
    from scripts.performance.linux_native_destination_observer import DestinationObserver
    from tests.performance.test_linux_native_source_observer import Sampler
    monkeypatch.setattr(endpoint.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(endpoint, 'DestinationObserver', lambda root, **kwargs:
                        DestinationObserver(root, **kwargs, sampler_factory=Sampler))
    def reader(stream, messages, stop):
        for row in transcript():
            op = 'paced_final' if row['schema'].endswith('final-v1') else 'paced_progress'
            messages.put((json.dumps(dict(op=op, value=row))+'\n').encode())
        messages.put(b'{"op":"ack"}\n')
        stop.wait(2)
    monkeypatch.setattr(endpoint, 'read_commands', reader)
    def delegate(item, check_cancelled, destination_observer_factory):
        import time
        item.output.mkdir()
        (item.output/'ready.json').write_text(json.dumps(dict(endpoint='192.0.2.2:1234', alpn='nbsr-quic-1')))
        with destination_observer_factory(item.output, pid=123, cpus=[0], payload_bytes=1024,
                                          deadline_ns=time.monotonic_ns()+10**10) as monitor:
            for _ in range(6):
                check_cancelled()
            assert (item.output/'completion.ack').exists()
            assert monitor.guard.final is not None and monitor.sampler.stopped
            return dict(exit_code=0, destination_live_resources=monitor.finish(0))
    output = io.StringIO()
    endpoint.execute_endpoint(paired_args(tmp_path, 'destination'), input_stream=io.BytesIO(),
                              output_stream=output, delegate=delegate)
    result = json.loads((tmp_path/'out/result.json').read_bytes())
    assert result['destination_live_guard']['final_received']
    assert result['destination_live_guard']['sustained_capacity'] == 'NOT_ESTABLISHED'
    assert [json.loads(line)['event'] for line in output.getvalue().splitlines()] == ['owned', 'ready', 'acked', 'complete']


def test_paired_mode_is_bound_in_comparison_identity():
    from scripts.performance.linux_native_cohort import comparison_identity
    env = dict(linux_environment={}, binary_sha256={}, certificates_sha256={}, bind='192.0.2.1:0')
    assert comparison_identity(env) != comparison_identity(env | {'paired_live_guards': True})
