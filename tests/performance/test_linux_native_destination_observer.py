import json
import pytest

from tests.performance.test_linux_native_source_observer import Sampler
from tests.performance.test_linux_native_paced import transcript


def test_destination_retains_late_final_after_owned_peer_exit(tmp_path):
    from scripts.performance.linux_native_destination_observer import DestinationObserver
    peer = tmp_path / 'peer'
    peer.mkdir()
    with DestinationObserver(peer, pid=123, cpus=[0], payload_bytes=1024,
        deadline_ns=100_000_000_000, sampler_factory=Sampler, clock=lambda: 25_000_000_000) as value:
        value.stop()
        assert value.finish(0)['resource_collection_complete']
    for row in transcript()[:-1]:
        value.source_event('paced_progress', row, received_ns=30_000_000_000+row['elapsed_ns'])
    value.source_event('paced_final', transcript()[-1], received_ns=55_000_000_000)
    assert value.guard.qualification()['final_received']
    assert value.guard.qualification()['sustained_capacity'] == 'NOT_ESTABLISHED'
    assert len((tmp_path/'destination-live-events.ndjson').read_text().splitlines()) == 5


def test_source_final_stops_destination_sampler_before_guard_closes(tmp_path):
    from scripts.performance.linux_native_destination_observer import DestinationObserver
    peer = tmp_path / 'peer'
    peer.mkdir()
    with DestinationObserver(peer, pid=123, cpus=[0], payload_bytes=1024,
        deadline_ns=100_000_000_000, sampler_factory=Sampler, clock=lambda: 25_000_000_000) as value:
        for row in transcript()[:-1]:
            value.source_event('paced_progress', row, received_ns=row['elapsed_ns'])
        value.source_event('paced_final', transcript()[-1], received_ns=25_000_000_000)
        assert value.sampler.stopped
        value.poll()
        assert value.finish(0)['resource_collection_complete']


def test_source_observer_emits_validated_progress_then_final(tmp_path):
    from scripts.performance.linux_native_source_observer import SourceObserver
    (tmp_path/'stdout').write_bytes(''.join(json.dumps(row)+'\n' for row in transcript()).encode())
    emitted = []
    with SourceObserver(tmp_path, pid=123, cpus=[0], payload_bytes=1024,
        deadline_ns=100_000_000_000, sampler_factory=Sampler, clock=lambda: 25_000_000_000,
        on_record=lambda kind, row: emitted.append((kind, row))) as value:
        value.poll()
        value.stop()
        value.finish(0)
    assert [kind for kind, _ in emitted] == ['paced_progress']*4 + ['paced_final']
    assert [row for _, row in emitted] == transcript()


@pytest.mark.parametrize('fault', [None, 'source-value', 'resource-copy', 'reported-result', 'receipt-clock'])
def test_destination_replay_joins_source_and_owned_samples(tmp_path, fault):
    from scripts.performance.linux_native_destination_observer import DestinationObserver, replay_destination
    peer = tmp_path/'peer'
    peer.mkdir()
    (peer/'pid.json').write_text(json.dumps({'pid': 123}))
    (peer/'environment.json').write_text(json.dumps({'linux_environment': {'selected_cpus': [0]}}))
    source = tmp_path/'source'
    source.mkdir()
    (source/'stdout').write_bytes(''.join(json.dumps(row)+'\n' for row in transcript()).encode())
    with DestinationObserver(peer, pid=123, cpus=[0], payload_bytes=1024,
        deadline_ns=100_000_000_000, sampler_factory=Sampler, clock=lambda: 25_000_000_000) as value:
        value.sampler.sink(dict(role='destination', pid=123, affinity=[0], start_ticks=10,
            cpu_ns=1, timestamp_ns=1, private_resident_bytes=1000, state='S', memory_state='MEASURED'))
        for row in transcript()[:-1]:
            value.source_event('paced_progress', row, received_ns=row['elapsed_ns'])
        value.source_event('paced_final', transcript()[-1], received_ns=25_000_000_000)
        value.finish(0)
    (tmp_path/'result.json').write_text(json.dumps({'destination_live_guard': value.guard.qualification()}))
    if fault == 'source-value':
        rows = transcript()
        rows[0]['p99_latency_ns'] += 1
        (source/'stdout').write_bytes(''.join(json.dumps(row)+'\n' for row in rows).encode())
    elif fault == 'resource-copy':
        (peer/'destination-live-resources.ndjson').write_bytes(b'')
    elif fault == 'reported-result':
        (tmp_path/'result.json').write_text(json.dumps({'destination_live_guard': {}}))
    elif fault == 'receipt-clock':
        path = tmp_path/'destination-live-events.ndjson'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[-1]['received_ns'] = 0
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    if fault:
        with pytest.raises(ValueError):
            replay_destination(tmp_path, source, payload_bytes=1024)
    else:
        assert replay_destination(tmp_path, source, payload_bytes=1024) == value.guard.qualification()
