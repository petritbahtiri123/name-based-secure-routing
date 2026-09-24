from pathlib import Path

import pytest


@pytest.mark.parametrize('seconds', [60, 3600, 7200])
def test_duration_changes_real_command_and_bounded_control_budget(seconds, tmp_path):
    from scripts.performance.linux_native_duration import bounds
    from scripts.performance.linux_native_peer import native_command
    from scripts.performance.linux_native_lifecycle_coordinator import Manager
    from scripts.performance.linux_native_finite_control import FiniteLedger
    cell = dict(path='nbsr', cores=1, payload_bytes=16384, streams=8, outstanding=1,
                diagnostic_rate=[1000, 1], diagnostic_seconds=seconds)
    command, _ = native_command(cell, 'source', Path('/bins'), Path('/private'), tmp_path,
        bind='192.0.2.1:0', endpoint='192.0.2.2:4444', post_close_reports=True)
    assert command[command.index('--p2a-duration-seconds') + 1] == str(seconds)
    contract = bounds(seconds)
    assert contract['controller_seconds'] == seconds + 120
    assert contract['resources'] >= 2 * (seconds + 120)
    assert contract['progress'] > seconds // 5
    manager = Manager(None, tmp_path, ledger=FiniteLedger(), diagnostic_seconds=seconds)
    manager.close()


@pytest.mark.parametrize('seconds', [True, 20, 0, -1, 61, 3600.0, '3600', 7201])
def test_duration_is_explicit_bounded_profile(seconds):
    from scripts.performance.linux_native_duration import bounds
    with pytest.raises(ValueError):
        bounds(seconds)


def test_old_short_contract_and_deadline_remain_unchanged(tmp_path):
    from scripts.performance.linux_native_duration import bounds
    from scripts.performance.linux_native_lifecycle_coordinator import Manager
    assert bounds(None) == dict(duration=20, controller_seconds=120, progress=1024, resources=250)
    with pytest.raises(ValueError):
        Manager(None, tmp_path, timeout=121)


def test_long_endpoint_eof_still_cancels_before_child_and_records_duration(tmp_path, monkeypatch):
    import io
    import json
    from scripts.performance import linux_native_finite_endpoint as endpoint
    from tests.performance.test_linux_native_finite_endpoint import args
    item = args(tmp_path, 'source')
    item.diagnostic_seconds = 7200
    item.diagnostic_rate = [1000, 1]
    item.post_close_reports = True
    monkeypatch.setattr(endpoint.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(endpoint, 'read_commands', lambda stream, messages, stop: messages.put(None))
    with pytest.raises(InterruptedError, match='EOF'):
        endpoint.execute_endpoint(item, input_stream=io.BytesIO(), output_stream=io.StringIO(),
            delegate=lambda *a, **k: pytest.fail('child started after EOF'))
    controller = json.loads((item.output / 'controller.json').read_bytes())
    assert '7200' in controller['workload']
    assert controller['diagnostic_seconds'] == 7200


def test_duration_config_requires_pacing_and_reaches_both_endpoints():
    from scripts.performance.linux_native_finite_run import validate_config, endpoint_arguments
    from tests.performance.test_linux_native_finite_run import config
    value = config() | dict(diagnostic_seconds=3600)
    with pytest.raises(ValueError):
        validate_config(value)
    value.update(diagnostic_rate=[1000, 1], post_close_reports=True)
    validate_config(value)
    for role in ('source', 'destination'):
        command = endpoint_arguments(value, role)
        assert command[command.index('--diagnostic-seconds') + 1] == '3600'


def test_short_final_cannot_satisfy_declared_long_workload(tmp_path):
    import json
    from scripts.performance.linux_native_paced import read_paced
    from tests.performance.test_linux_native_paced import transcript
    path = tmp_path / 'stdout'
    path.write_text(''.join(json.dumps(row)+'\n' for row in transcript()))
    cell = dict(path='nbsr', payload_bytes=1024, streams=1, outstanding=1,
                diagnostic_rate=[100, 1], diagnostic_seconds=3600)
    read_paced(path, {k: v for k, v in cell.items() if k != 'diagnostic_seconds'})
    with pytest.raises(ValueError, match='duration'):
        read_paced(path, cell)


def test_two_hour_transcript_and_both_resource_replays_exceed_old_bounds(tmp_path):
    import json
    from scripts.performance.linux_native_source_observer import SourceObserver, replay
    from scripts.performance.linux_native_destination_observer import DestinationObserver, replay_destination
    from scripts.performance.linux_native_paced import read_paced
    from tests.performance.test_linux_native_paced import transcript, cell
    from tests.performance.test_linux_native_source_observer import Sampler
    source, destination = tmp_path / 'source', tmp_path / 'destination' / 'peer'
    source.mkdir()
    destination.mkdir(parents=True)
    for root in (source, destination):
        (root / 'pid.json').write_text(json.dumps({'pid': 123}))
        (root / 'environment.json').write_text(json.dumps({'linux_environment': {'selected_cpus': [0]}}))
    template = transcript()
    rows = []
    for index in range(1, 1441):
        counters = dict(offered=index*500, reserved=index*500, issued=index*500,
                        completed=index*500, missed=0, unreserved_current=0)
        rows.append(template[0] | counters | dict(window_index=index, elapsed_ns=index*5_000_000_000,
            interval_start_ns=(index-1)*5_000_000_000, interval_end_ns=index*5_000_000_000,
            issue_deadline_ns=7_200_000_000_000, group_counters=[dict(group_id=0, **counters)]))
    rows.append(template[-1] | counters | dict(measurement_duration_ns=7_200_000_000_000,
        group_counters=[dict(group_id=0, **counters)]))
    (source / 'stdout').write_text(''.join(json.dumps(row)+'\n' for row in rows))
    kwargs = dict(pid=123, cpus=[0], payload_bytes=1024, deadline_ns=7_400_000_000_000,
        diagnostic_seconds=7200, sampler_factory=Sampler, clock=lambda: 7_300_000_000_000)
    with DestinationObserver(destination, **kwargs) as dst:
        with SourceObserver(source, on_record=lambda kind, row: dst.source_event(
                kind, row, received_ns=7_300_000_000_000), **kwargs) as src:
            for role, value in (('source', src), ('destination', dst)):
                for index in range(300):
                    value.sampler.sink(dict(role=role, pid=123, affinity=[0], start_ticks=10,
                        cpu_ns=index, timestamp_ns=index+1, private_resident_bytes=1000,
                        state='S', memory_state='MEASURED'))
            for _ in range(30):
                src.poll()
            src.stop()
            src.finish(0)
        assert dst.finish(0)['samples'] == 300
    (destination.parent / 'result.json').write_text(json.dumps({'destination_live_guard': dst.guard.qualification()}))
    assert replay(source, payload_bytes=1024, diagnostic_seconds=7200)['steady_windows'] == 1440
    assert replay_destination(destination.parent, source, payload_bytes=1024,
                              diagnostic_seconds=7200)['steady_windows'] == 1440
    assert read_paced(source / 'stdout', cell() | {'diagnostic_seconds': 7200})['completed_operations'] == 720000
    with pytest.raises(ValueError):
        replay(source, payload_bytes=1024)  # Old short mode still rejects this history.
