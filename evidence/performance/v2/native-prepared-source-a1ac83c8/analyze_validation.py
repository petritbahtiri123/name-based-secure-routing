"""Independently check prepared-source counterfactual and held-scale results."""
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path.cwd()))
from scripts.performance.linux_native_lifecycle_pair import analyze
from scripts.performance.linux_socket_ownership import validate_binding

OUT = Path(__file__).resolve().parent
BUILD = Path('C:/NBSR-build/linux-current-a1ac83c8')
SHA = (BUILD / 'source-sha.txt').read_text().strip()
ROOTS = [Path('C:/NBSR-build/native-prepared-counterfactual-a1ac83c8-cached'),
         Path('C:/NBSR-build/native-prepared-local-observer512-a1ac83c8')]
results = []
for root in ROOTS:
    records = json.loads((root / 'records.json').read_text())
    assert len(records) == (6 if 'counterfactual' in root.name else 5)
    for record in records:
        label, count = record['label'], record['count']
        peers = {role: root / role / label for role in ('source', 'destination')}
        resources = {role: [json.loads(line) for line in (p / 'resources.ndjson').read_text().splitlines()]
                     for role, p in peers.items()}
        errors = [json.loads(line) for line in (peers['source'] / 'stdout').read_text().splitlines()
                  if json.loads(line).get('success') is False]
        timeouts = (peers['destination'] / 'stderr').read_text().count(
            'lifecycle destination handshake failed: HandshakeTimeout')
        result = dict(root=str(root), label=label, count=count, status=record['status'],
            startup_gap_seconds=(resources['source'][0]['timestamp_ns'] -
                                 resources['destination'][0]['timestamp_ns']) / 1e9,
            destination_timeout_count=timeouts, source_errors=errors,
            resources={role: dict(peak_rss_bytes=max(row['rss_bytes'] for row in rows),
                peak_fd_count=max(row['fd_count'] or 0 for row in rows),
                peak_threads=max(len(row['thread_ids']) for row in rows))
                for role, rows in resources.items()})
        if record['status'] != 'PASS_FUNCTIONAL':
            assert record['status'] == 'FAIL_RETAINED'
            if record['mode'] == 'legacy':
                assert timeouts == 1 and [row['logical_client_id'] for row in errors] == [15]
            try:
                analyze(peers['source'], peers['destination'], source_sha=SHA, count=count)
            except ValueError as error:
                result['pair_rejected'] = str(error)
            else:
                raise AssertionError('failed pair accepted')
        else:
            assert record['status'] == 'PASS_FUNCTIONAL' and not errors and timeouts == 0
            result['pair'] = analyze(peers['source'], peers['destination'], source_sha=SHA, count=count)
            prepared = json.loads((peers['source'] / 'source-prepared.json').read_text())
            assert prepared['status'] == 'PREPARED_NOT_CONNECTED'
            assert prepared['repository_sha'] == SHA
            assert prepared['timestamp_ns'] < resources['destination'][0]['timestamp_ns']
            binding = json.loads((root / (label + '-bindings.json')).read_text())
            for role in peers:
                first = resources[role][0]
                value = binding[role]
                assert len(value['sockets']) == (count if role == 'source' else 1)
                assert len({row['inode'] for row in value['sockets']}) == len(value['sockets'])
                for row in value['sockets']:
                    validate_binding(value, pid=first['pid'], start_ticks=first['start_ticks'],
                                     binary=json.loads((peers[role] / 'command.json').read_text())['argv'][3], local=row['local'])
                markers = root / role / (label + '-markers')
                prefix = 'connection' if role == 'source' else 'destination'
                assert {p.name for p in markers.glob('*.active')} == {
                    f'{prefix}-{i}.active' for i in range(count)}
                assert {p.name for p in markers.glob('*.release')} == {
                    f'connection-{i}.release' for i in range(count)}
                assert not list(markers.glob('*.failed'))
                if role == 'source':
                    assert {p.name for p in markers.glob('*.ack')} == {
                        f'connection-{i}.ack' for i in range(count)}
                else:
                    snapshots = [json.loads(p.read_text()) for p in markers.glob('*.active')]
                    fields = ('transport_sessions_current_live', 'service_channels_current_live',
                              'application_streams_current_live', 'quic_streams_current_live')
                    assert all(row['phase'] == 'b3_materialized_streams_ready' and
                               all(type(row[k]) is int and 1 <= row[k] <= count for k in fields) for row in snapshots)
                    assert any(all(row[k] == count for k in fields) for row in snapshots)
        results.append(result)
scale = [r for r in results if r['count'] == 512 and r['status'] == 'PASS_FUNCTIONAL']
report = dict(source_sha=SHA, classification='PARTIAL_FUNCTIONAL_NAMESPACE_SCALE',
    controlled_startup=dict(legacy_failures=3, prepared_passes=3),
    largest_five_repeat_successful_native_bundles=256,
    scale_successes=len(scale), scale_failures=5-len(scale), total_scale_completed=sum(r['count'] for r in scale),
    median_scale_peak_resources={role: {field: statistics.median(r['resources'][role][field] for r in scale)
        for field in ('peak_rss_bytes', 'peak_fd_count', 'peak_threads')}
        for role in ('source', 'destination')}, records=results,
    limitations=['Not sustainable admission, forwarding capacity, physical cores or external server hardware.',
        'Separate-process repetitions; not same-process memory retention or per-object allocation cost.',
        'Original failure cohorts remain retained; observer scheduling changed for the final scale cohort.',
        'Shared-WSL monotonic comparison only; not a cross-physical-host clock assumption.',
        'Two-second paired hold is controller evidence; peer pair gate does not independently prove it.'])
(OUT / 'validation-analysis.json').write_text(json.dumps(report, indent=2) + '\n')
print('Verified outcomes:',[(r['label'],r['status']) for r in results])
