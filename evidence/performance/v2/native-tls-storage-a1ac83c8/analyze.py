import json
import math
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path.cwd()))
from scripts.performance.linux_native_lifecycle_pair import analyze
from scripts.performance.linux_socket_ownership import validate_binding

ROOT = Path('C:/NBSR-build/native-tls-storage-isolated-a1ac83c8-v2')
OUT = Path(__file__).resolve().parent
SHA = Path('C:/NBSR-build/linux-current-a1ac83c8/source-sha.txt').read_text().strip()
records = json.loads((ROOT / 'records.json').read_text())
assert len(records) == 10
results = []
fixtures = {}
for record in records:
    label = record['label']
    assert record['count'] == 512 and record['status'] == 'PASS_FUNCTIONAL'
    assert record['release_started_ns'] - record['paired_active_observed_ns'] >= 2_000_000_000
    peers = {role: ROOT / role / label for role in ('source', 'destination')}
    pair = analyze(peers['source'], peers['destination'], source_sha=SHA, count=512)
    bindings = json.loads((ROOT / (label + '-bindings.json')).read_text())
    for role, peer in peers.items():
        first = json.loads((peer / 'resources.ndjson').read_text().splitlines()[0])
        command = json.loads((peer / 'command.json').read_text())
        binding = bindings[role]
        assert len(binding['sockets']) == (512 if role == 'source' else 1)
        for entry in binding['sockets']:
            validate_binding(binding, pid=first['pid'], start_ticks=first['start_ticks'],
                             binary=command['argv'][3], local=entry['local'])
        markers = ROOT / role / (label + '-markers')
        prefix = 'connection' if role == 'source' else 'destination'
        assert {p.name for p in markers.glob('*.active')} == {f'{prefix}-{i}.active' for i in range(512)}
        assert {p.name for p in markers.glob('*.release')} == {f'connection-{i}.release' for i in range(512)}
        assert not list(markers.glob('*.failed'))
        if role == 'source':
            assert {p.name for p in markers.glob('*.ack')} == {f'connection-{i}.ack' for i in range(512)}
    env = json.loads((peers['source'] / 'environment.json').read_text())
    if record['repeat'] in fixtures:
        assert fixtures[record['repeat']] == env['fixture_sha256']
    fixtures[record['repeat']] = env['fixture_sha256']
    rows = [json.loads(line) for line in (peers['source'] / 'stdout').read_text().splitlines()]
    samples = sorted(row['transport_handshake_ns'] for row in rows if row.get('success') is True)
    assert len(samples) == 512
    quantiles = {name: samples[math.ceil(q * len(samples)) - 1] / 1e6
                 for name, q in [('p50', .5), ('p95', .95), ('p99', .99)]}
    results.append(dict(label=label, mode=record['mode'], repeat=record['repeat'],
        pair=pair, cold_handshake_including_tls_configuration_ms=quantiles,
        tls_filesystem={role: json.loads((ROOT / role / (label + '-tls-storage.json')).read_text())['filesystem']
                        for role in peers}))
summary = {}
for mode in ('prepared-mounted-tls', 'prepared-local-tls'):
    cells = [r for r in results if r['mode'] == mode]
    assert len(cells) == 5
    q = 'cold_handshake_including_tls_configuration_ms'
    p99 = [r[q]['p99'] for r in cells]
    summary[mode] = dict(passes=5, total_completed=2560,
        median_cell_quantiles_ms={k: statistics.median(r[q][k] for r in cells) for k in ('p50', 'p95', 'p99')},
        p99_cv_percent=100 * statistics.stdev(p99) / statistics.mean(p99))
report = dict(source_sha=SHA, status='PASS_FUNCTIONAL_FRESH_NAMESPACE_COMPARISON',
    sustainable_capacity='NOT_ESTABLISHED', timing='DIAGNOSTIC_ONLY', count_per_cell=512,
    completed_total=5120, summary=summary, records=results,
    quantile_method='nearest rank within cell; median across the five cells',
    interpretation='Local TLS lowers the cold-handshake timer in all five pairs; both arms complete. '
        'This supports harness fixture-I/O sensitivity, not attribution of every earlier handshake failure. '
        'Each cell has fresh containers, unlike earlier reused-namespace cohorts. Their failures remain retained. '
        'The raw transport_handshake_ns timer includes synchronous TLS reads/configuration before connect.',
    limits=['No timing observer qualification or stable latency/capacity claim.',
            'No same-process retention, pure per-object allocation, external hardware or production optimization.',
            'Prior interrupted mounted-TLS preview and setup-only failure are separately retained.'])
(OUT / 'analysis.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(summary, indent=2))
