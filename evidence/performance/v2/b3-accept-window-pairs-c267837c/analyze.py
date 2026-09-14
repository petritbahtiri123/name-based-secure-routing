import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import statistics

root = Path(__file__).resolve().parent
attempts = json.loads((root / 'results.json').read_text())
assert len(attempts) == 10
rows = []
verified = 0
for attempt in attempts:
    case = root / f"window-{attempt['window']}-r{attempt['repeat']}"
    for line in (case / 'checksums.sha256').read_text().splitlines():
        expected, name = line.split('  ', 1)
        file = (case / name).resolve()
        assert file.is_relative_to(case.resolve())
        with file.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected
        verified += 1
    raw = case / 'raw/rust-rust/live-bundles-2048-r1'
    row = dict(window=attempt['window'], repeat=attempt['repeat'], exit_code=attempt['exit_code'])
    assert f'"armed":{attempt["window"]}' in (raw / 'destination.stderr').read_text()
    outcomes = [json.loads(line) for line in (raw / 'source-0.stdout').read_text().splitlines() if line.strip()]
    row['errors'] = dict(Counter(r['error'] for r in outcomes if r.get('error')))
    if attempt['exit_code']:
        failure = json.loads((raw / 'failure.json').read_text())
        names = next(ast.literal_eval(line.split(': ', 1)[1]) for line in failure['detail'].splitlines() if line.startswith('lifecycle_files: '))
        row['active_markers'] = sum(bool(re.fullmatch(r'connection-\d+\.active', name)) for name in names)
        row['destination_active_markers'] = sum(bool(re.fullmatch(r'destination-\d+\.active', name)) for name in names)
        assert row['active_markers'] == row['destination_active_markers']
        assert row['active_markers'] + sum(row['errors'].values()) == 2048
        udp = json.loads((raw / 'linux-udp-failure.json').read_text())['roles']
        row['retained_destination_udp_drops'] = udp['destination']['live_socket_drops']
        row['retained_source_udp_drops'] = sum(v['live_socket_drops'] for k, v in udp.items() if k.startswith('source-'))
    else:
        cell = json.loads((raw / 'cell.json').read_text())
        assert cell['cleanup']['all_zero'] and cell['cleanup']['source_all_zero']
        row['active_markers'] = cell['active_count']
        row['cleanup'] = cell['cleanup']
    rows.append(row)
summary = {}
for window in (1, 32):
    selected = [r for r in rows if r['window'] == window]
    assert len(selected) == 5
    summary[str(window)] = dict(passed=sum(r['exit_code'] == 0 for r in selected),
        failed=sum(r['exit_code'] != 0 for r in selected),
        median_active_markers=statistics.median(r['active_markers'] for r in selected),
        median_handshake_timeouts=statistics.median(r['errors'].get('HandshakeTimeout', 0) for r in selected),
        total_client_task_failed=sum(r['errors'].get('client_task_failed', 0) for r in selected))
report = dict(classification='DIAGNOSTIC; neither window establishes stable 2048-bundle capacity on one guest CPU',
    decision='Keep default window 1; do not promote window 32.',
    indexed_child_files_verified=verified, summary=summary, rows=rows,
    limitations=['Active markers in failed attempts are progress, not accepted capacity or admissions/s.',
                'Failure-only socket counters omit closed sockets and drop timing.',
                'One passing attempt is not repeatable capacity.',
                'Guest CPU affinity does not prove exclusive physical-core capacity.'])
(root / 'analysis.json').write_text(json.dumps(report, indent=2))
print(json.dumps(dict(summary=summary, indexed_child_files_verified=verified), indent=2))
