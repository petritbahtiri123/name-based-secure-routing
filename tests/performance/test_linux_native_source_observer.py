import json

import pytest

from tests.performance.test_linux_native_paced import transcript


class Sampler:
    def __init__(self, *args, **kwargs):
        self.sink = kwargs['record_sink']
        self.started = self.stopped = False

    def start(self):
        self.started = True

    def check_health(self, require_running=False):
        assert not require_running or self.started and not self.stopped

    def stop(self):
        self.stopped = True


def observer(tmp_path):
    from scripts.performance.linux_native_source_observer import SourceObserver
    (tmp_path / 'stdout').touch()
    return SourceObserver(tmp_path, pid=123, cpus=[0], payload_bytes=1024,
                          deadline_ns=100_000_000_000, sampler_factory=Sampler,
                          clock=lambda: 25_000_000_000)


def test_source_observer_frames_partial_stdout_and_replays(tmp_path):
    from scripts.performance.linux_native_source_observer import replay
    with observer(tmp_path) as value:
        wire = ''.join(json.dumps(row)+'\n' for row in transcript()).encode()
        with (tmp_path / 'stdout').open('ab') as stream:
            stream.write(wire[:19])
            stream.flush()
            value.poll()
            stream.write(wire[19:])
            stream.flush()
            value.poll()
        value.stop()
        result = value.finish(0)
    assert result['final_received']
    assert result['sustained_capacity'] == 'NOT_ESTABLISHED'
    assert replay(tmp_path, payload_bytes=1024) == result
    assert (tmp_path / 'live-observed-stdout').read_bytes() == wire


@pytest.mark.parametrize('fault', ['partial', 'missing-final', 'after-final', 'exit'])
def test_observer_rejects_invalid_completion(tmp_path, fault):
    with observer(tmp_path) as value:
        rows = transcript()
        if fault == 'missing-final':
            rows.pop()
        if fault == 'after-final':
            rows.append({'event': 'diagnostic'})
        wire = ''.join(json.dumps(row)+'\n' for row in rows).encode()
        (tmp_path / 'stdout').write_bytes(wire[:-1] if fault == 'partial' else wire)
        with pytest.raises(ValueError):
            value.poll()
            value.stop()
            value.finish(1 if fault == 'exit' else 0)


def test_replay_rejects_changed_observed_stdout(tmp_path):
    from scripts.performance.linux_native_source_observer import replay
    with observer(tmp_path) as value:
        (tmp_path / 'stdout').write_bytes(''.join(json.dumps(row)+'\n' for row in transcript()).encode())
        value.poll()
        value.stop()
        value.finish(0)
    (tmp_path / 'live-observed-stdout').write_bytes(b'changed\n')
    with pytest.raises(ValueError):
        replay(tmp_path, payload_bytes=1024)


def test_sampler_stopped_on_exception(tmp_path):
    value = observer(tmp_path)
    with pytest.raises(RuntimeError):
        with value:
            raise RuntimeError('cancel')
    assert value.sampler.stopped


def test_live_source_mode_is_explicit_and_paced_only():
    from scripts.performance.linux_native_finite_run import validate_config, endpoint_arguments
    from tests.performance.test_linux_native_finite_run import config
    row = config() | dict(post_close_reports=True, diagnostic_rate=[100, 1], source_live_guard=True)
    validate_config(row)
    assert '--source-live-guard' in endpoint_arguments(row, 'source')
    assert '--source-live-guard' not in endpoint_arguments(row, 'destination')
    row.pop('diagnostic_rate')
    with pytest.raises(ValueError):
        validate_config(row)


def test_live_mode_is_part_of_cohort_identity():
    from scripts.performance.linux_native_cohort import comparison_identity
    env = dict(linux_environment={}, binary_sha256={}, certificates_sha256={}, bind='192.0.2.1:0')
    assert comparison_identity(env) != comparison_identity(env | {'source_live_guard': True})


def test_sampler_stops_before_owned_source_reap(tmp_path, monkeypatch):
    from scripts.performance import linux_native_peer as peer
    from types import SimpleNamespace
    events = []
    monitor = SimpleNamespace(poll=lambda: events.append('poll'), stop=lambda: events.append('stop'),
                              finish=lambda code: events.append('finish') or {'diagnostic': True})
    def reap(**kwargs):
        assert events[-1] == 'stop'
        events.append('reap')
        return 0
    child = SimpleNamespace(pid=123, wait=reap)
    monkeypatch.setattr(peer, 'sample_process', lambda *a, **k:
                        dict(pid=123, start_ticks=1, state='Z', cpu_ns=10))
    result = peer.observe_child(child, [0], tmp_path, deadline=peer.time.monotonic()+1, live_observer=monitor)
    assert events == ['poll', 'stop', 'reap', 'finish']
    assert result['source_live_guard'] == {'diagnostic': True}


def test_live_deadline_is_checked_without_stdout(tmp_path):
    with observer(tmp_path) as value:
        value.stream._clock = lambda: 100_000_000_001
        with pytest.raises(ValueError, match='deadline'):
            value.poll()


def test_sampler_failure_is_not_silently_ignored(tmp_path):
    with observer(tmp_path) as value:
        def fail(**kwargs):
            raise RuntimeError('sampling failed')
        value.sampler.check_health = fail
        with pytest.raises(ValueError, match='sampling failed'):
            value.poll()


@pytest.mark.parametrize('fault', ['pid', 'affinity', 'start_ticks', 'cpu_ns'])
def test_replay_rejects_resource_identity_or_counter_mutation(tmp_path, fault):
    from scripts.performance.linux_native_source_observer import replay
    (tmp_path / 'pid.json').write_text(json.dumps({'pid': 123}))
    (tmp_path / 'environment.json').write_text(json.dumps({'linux_environment': {'selected_cpus': [0]}}))
    with observer(tmp_path) as value:
        for index in (1, 2):
            value.sampler.sink(dict(role='source', pid=123, affinity=[0], start_ticks=10,
                cpu_ns=index, timestamp_ns=index, private_resident_bytes=1000,
                state='S', memory_state='MEASURED'))
        (tmp_path / 'stdout').write_bytes(''.join(json.dumps(row)+'\n' for row in transcript()).encode())
        value.poll()
        value.stop()
        value.finish(0)
    replay(tmp_path, payload_bytes=1024)
    path = tmp_path / 'live-events.ndjson'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[1]['value'][fault] = {'pid': 456, 'affinity': [1], 'start_ticks': 11, 'cpu_ns': 0}[fault]
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    with pytest.raises(ValueError):
        replay(tmp_path, payload_bytes=1024)
