"""Recheck retained control/peer evidence; no sustainable-capacity inference."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
from scripts.performance.linux_native_lifecycle_gate import check_endpoint
from scripts.performance.linux_native_lifecycle_pair import analyze
from scripts.performance.linux_native_pair import verify_index

OUT = Path(__file__).resolve().parent
ROOT = Path('C:/NBSR-build/native-control-smoke-3dfd9f8a')
SCALE = Path('C:/NBSR-build/native-control-scale512-3dfd9f8a')
SHA = Path('C:/NBSR-build/linux-current-3dfd9f8a/source-sha.txt').read_text().strip()
roles = ('source', 'destination')


def read(root, name):
    return json.loads((root / name).read_bytes())


def check_cell(root, label, count):
    cell = root / label
    index = verify_index(cell)
    result = read(cell, 'result.json')
    assert result['status'] == 'PASS_FUNCTIONAL_CONTROLLED_PAIR'
    assert not (cell / 'failure.json').exists()
    endpoints = {role: check_endpoint(cell / role, role, count) for role in roles}
    pair = analyze(cell / 'source' / 'peer', cell / 'destination' / 'peer', source_sha=SHA, count=count)
    rows = [json.loads(line) for line in (cell / 'management.ndjson').read_text().splitlines()]
    assert all(rows[i]['timestamp_ns'] <= rows[i+1]['timestamp_ns'] for i in range(len(rows)-1))

    def phase(role, event):
        found = [row for row in rows if row['action'] == 'receive' and row['role'] == role and row['value']['event'] == event]
        assert len(found) == 1 and found[0]['value'] == endpoints[role]['events'][event]
        return found[0]['timestamp_ns']

    def sent(role, op):
        found = [row for row in rows if row['action'] == 'send' and row['role'] == role and row['value']['op'] == op]
        assert len(found) == 1
        return found[0]['timestamp_ns']

    both_active = max(phase(role, 'active') for role in roles)
    hold = sent('destination', 'release') - both_active
    cooldown = sent('destination', 'report_release') - phase('destination', 'report_ready')
    assert hold >= 2_000_000_000 and cooldown >= 2_000_000_000
    assert sent('destination', 'release') <= phase('destination', 'released') <= sent('source', 'release')
    assert phase('source', 'acked') <= sent('destination', 'report_release')
    starts = {row['role']: row['timestamp_ns'] for row in rows if row['action'] == 'start'}
    assert starts['source'] <= phase('source', 'prepared') <= starts['destination']
    cleanup = read(cell, 'cleanup.json')
    assert all(value['exit_code'] == 0 and not value['local_relay_forced'] for value in cleanup.values())
    assert all(read(root, label+'-'+role+'-remaining-processes.json') == [] for role in roles)
    transfers = {role: read(cell, role+'-transfer.json') for role in roles}
    assert all(not (cell / (role+'.tar')).exists() for role in roles)
    return dict(label=label, count=count, status=result['status'], index_sha256=index,
                hold_ns=hold, cooldown_ns=cooldown, pair=pair,
                removed_verified_duplicate_archive_bytes=sum(v['archive_bytes'] for v in transfers.values()))


records = read(ROOT, 'records.json')
assert len(records) == 9
positive = [check_cell(ROOT, row['label'], 16) for row in records if row['label'].startswith('positive-')]
assert len(positive) == 3
negative = []
for row in records:
    if row['label'].startswith('positive-'):
        continue
    assert row['status'] == 'PASS_EOF_CANCELLATION'
    cell = ROOT / row['label']
    index = verify_index(cell)
    result = read(ROOT, row['label']+'-eof-result.json')
    assert 0 < result['elapsed_ns'] < 15_000_000_000 and result['exit_code'] != 0
    cleanup = read(cell, 'cleanup.json')
    assert all(not value['local_relay_forced'] for value in cleanup.values())
    for role in roles:
        verify_index(cell / role)
        verify_index(cell / role / 'peer')
        assert 'control EOF' in read(cell / role / 'peer', 'failure.json')['error']
        assert not (cell / role / 'result.json').exists()
        assert read(ROOT, row['label']+'-'+role+'-remaining-processes.json') == []
    negative.append(dict(label=row['label'], index_sha256=index, **result,
                         interpretation='Owned process cleanup only; cancelled runs are not successful ownership lifecycles'))
assert len(negative) == 6
scale_records = read(SCALE, 'records.json')
assert len(scale_records) == 5 and all(row['status'] == 'PASS_FUNCTIONAL' for row in scale_records)
scale = [check_cell(SCALE, row['label'], 512) for row in scale_records]
failed = Path('C:/NBSR-build/native-control-smoke-25db6831')
assert read(failed, 'records.json')[0]['status'] == 'FAIL_RETAINED'
assert 'could not acquire lock' in (failed / 'positive-r1/source-stderr.log').read_text()
assert read(failed / 'positive-r1', 'cleanup.json')['source']['exit_code'] == 134
report = dict(status='PASS_FUNCTIONAL_COORDINATOR_VALIDATION', source_sha=SHA,
    positive_16=positive, eof_cancellation=negative, positive_512=scale,
    successful_completed_connections=48+2560, cancellation_cells=6,
    prior_failure='25db6831 source interpreter exit 134 after completion event; retained and rejected',
    physical_hardware='NOT_PROVEN', real_ssh='NOT_EXECUTED', sustainable_capacity='NOT_ESTABLISHED',
    production_changes='NONE', same_process_retention='NOT_MEASURED',
    limits=['Fresh Docker namespaces in one WSL host, not separate hardware.',
            'No observer-qualified latency or forwarding throughput claim.',
            'Successful fresh-namespace 512 cells do not erase earlier reused-namespace failures.',
            'EOF cleanup is not proof against host loss, SIGKILL or network partition.'])
(OUT / 'analysis.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(dict(status=report['status'], successful_completed_connections=report['successful_completed_connections'],
                     cancellation_cells=6)))
