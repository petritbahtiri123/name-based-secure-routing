"""Read-only startup/finite-slot correlation; no event timestamp is invented."""
import json
from pathlib import Path

ROOT = Path('C:/NBSR-build/native-control-scale512-a401567d')
OUT = Path(__file__).resolve().parent
records = []
for repeat in range(1, 6):
    label = f'local-512-r{repeat}'
    resources = {role: [json.loads(line) for line in
        (ROOT / role / label / 'resources.ndjson').read_text().splitlines()]
        for role in ('source', 'destination')}
    diagnostics = [json.loads(line) for line in
        (ROOT / 'destination' / label / 'diagnostics.ndjson').read_text().splitlines()]
    errors = [json.loads(line) for line in
        (ROOT / 'source' / label / 'stdout').read_text().splitlines()
        if json.loads(line).get('success') is False]
    destination_timeouts = (ROOT / 'destination' / label / 'stderr').read_text().count(
        'lifecycle destination handshake failed: HandshakeTimeout')
    gap = (resources['source'][0]['timestamp_ns'] - resources['destination'][0]['timestamp_ns']) / 1e9
    records.append(dict(label=label, first_resource_sample_gap_seconds=gap,
        start_ticks_gap=resources['source'][0]['start_ticks'] - resources['destination'][0]['start_ticks'],
        destination_timeout_count=destination_timeouts,
        source_failed_ids=[e['logical_client_id'] for e in errors],
        source_errors=errors, predicted_empty_wait_slots=int(gap // 5),
        diagnostic_trajectory=[dict(seconds=row['timestamp_ns']/1e9,
            quic_connections_created=row['quic_connections_created'])
            for row in diagnostics if row.get('phase') == 'sample']))
assert [r['destination_timeout_count'] for r in records] == [0, 1, 4, 0, 0]
assert [r['source_failed_ids'] for r in records] == [[], [511], [508, 509, 510, 511], [], []]
assert all(r['predicted_empty_wait_slots'] == r['destination_timeout_count'] for r in records)
(OUT / 'historical-startup-analysis.json').write_text(json.dumps(dict(
    classification='DIAGNOSTIC_SUPPORTED_STARTUP_SLOT_EXHAUSTION',
    raw_root=str(ROOT), records=records,
    limitations=['First resource sample gaps are sampled process timing, not exact accept-arm timestamps.',
                 'Shared WSL clock; not applicable to independent host monotonic clocks.',
                 'This analysis alone is correlation. Controlled delayed-start experiment is separate.',
                 'No attribution of historical Windows admission collapse or production ceiling.']), indent=2)+'\n')
print('Five original outcomes match finite empty-accept slot exhaustion.')
