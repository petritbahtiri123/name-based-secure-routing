import hashlib
import json
from pathlib import Path

BASE = Path(__file__).parent
ROOT = BASE / 'captured'
COUNTERS = ('transport_sessions_current_live', 'service_channels_current_live',
    'application_streams_current_live', 'nbsr_tasks_current_live', 'quic_connections_current_live',
    'quic_streams_current_live', 'pending_routes_current_entries', 'channel_registry_current_entries',
    'stream_registry_current_entries', 'audit_queue_current_entries', 'replay_state_current_entries')
results = []
for shape in ('streams-16', 'streams-32', 'bundles-16', 'cycles-3'):
    rows = json.loads((ROOT / shape / 'records.json').read_text())
    assert len(rows) == 3
    for row in rows:
        cell = ROOT / shape / 'raw/rust-rust' / row['name']
        source = [json.loads(line) for line in (cell / 'source-0.stdout').read_text().splitlines() if line.startswith('{')]
        destination = [json.loads(line) for line in (cell / 'destination-diagnostics.ndjson').read_text().splitlines()]
        finals = [r for r in source if r.get('phase') == 'lifecycle_cleanup']
        assert len(finals) == 1
        reports = [('source', finals[0]), ('destination', destination[-1])]
        if shape == 'cycles-3':
            cycles = [r for r in source if r.get('phase', '').startswith('lifecycle_cycle_')]
            assert len(cycles) == 3
            reports += [('source_cycle', r) for r in cycles]
        for role, report in reports:
            assert all(type(report.get(k)) is int and report[k] == 0 for k in COUNTERS), (shape, row['name'], role)
        assert row['cleanup']['source_processes_exited'] and row['cleanup']['destination_exited']
        if shape != 'bundles-16':
            expected = {'streams-16': (8, 16, 1), 'streams-32': (8, 32, 1), 'cycles-3': (1, 64, 3)}[shape]
            markers = list(cell.glob('destination-*.active.json'))
            assert len(markers) == expected[2]
            for path in markers:
                marker = json.loads(path.read_text())
                assert marker['service_channels_current_live'] == expected[0]
                assert marker['application_streams_current_live'] == marker['quic_streams_current_live'] == expected[1]
        results.append(dict(shape=shape, name=row['name'], raw_11_counter_reports=len(reports),
                            original_controller_counter_count=len(row['cleanup']['counters']), all_zero=True))
bundle_rows = json.loads((ROOT / 'bundles-16/records.json').read_text())
postclose = [s for r in bundle_rows for s in r['samples'] if s.get('memory_state') == 'UNAVAILABLE_EXPECTED_EXIT']
assert postclose and all(s['role'] == 'source' and s['phase'] == 'cooldown' and s['private_resident_bytes'] is None for s in postclose)
result = dict(status='INDEPENDENT_RAW_11_COUNTER_CHECK_PASS', runs=results,
    total_raw_reports=sum(r['raw_11_counter_reports'] for r in results), expected_postclose_source_rows=len(postclose),
    limitation='Existing B3 controller gates8 counters, not11. Independent raw validation covers11; original records unchanged.',
    first_attempt='INVALID_FAILED_EVIDENCE_CAPTURE_NOT_COUNTED', cli_live='NOT_RUN')
(BASE / 'independent-closure-validation.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result))
for directory in (BASE, Path('C:/NBSR-build/linux-b3-live-1cca67ad')):
    paths = sorted(p for p in directory.rglob('*') if p.is_file() and p != directory / 'external-checksums.sha256')
    lines = []
    for path in paths:
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        lines.append(digest + '  ' + path.relative_to(directory).as_posix() + '\n')
    (directory / 'external-checksums.sha256').write_bytes(''.join(lines).encode())
