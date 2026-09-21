"""Paired guest CPU placement diagnostic; no physical-core capacity claim."""

import json
import math
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path.cwd()))
from scripts.performance.linux_native_lifecycle_gate import check_endpoint
from scripts.performance.linux_native_lifecycle_pair import analyze
from scripts.performance.linux_native_pair import verify_index

ROOT = Path('C:/NBSR-build/native-placement-2da82de2')
OUT = Path(__file__).resolve().parent
SHA = Path('C:/NBSR-build/linux-current-2da82de2/source-sha.txt').read_text().strip()
ROLES = ('source', 'destination')


def read(root, name):
    return json.loads((root / name).read_bytes())


def quantiles(values):
    values = sorted(values)
    return {name: values[math.ceil(q * len(values))-1] for name, q in [('p50', .5), ('p95', .95), ('p99', .99)]}


def resource_summary(peer, phases):
    rows = [json.loads(line) for line in (peer / 'resources.ndjson').read_text().splitlines()]
    active, released = (phases[name]['timestamp_ns'] for name in ('active', 'released'))
    held = [row for row in rows if active <= row['timestamp_ns'] <= released and row['state'] != 'Z']
    assert len(held) >= 2
    before = [row for row in rows if row['timestamp_ns'] <= active]
    assert len(before) >= 2
    first, last = before[0], before[-1]
    elapsed = last['timestamp_ns'] - first['timestamp_ns']
    assert elapsed > 0
    return dict(held_samples=len(held), held_rss_median_bytes=statistics.median(row['rss_bytes'] for row in held),
        peak_rss_bytes=max(row['rss_bytes'] for row in rows),
        held_fd_median=statistics.median(row['fd_count'] for row in held),
        held_threads_median=statistics.median(len(row['thread_ids']) for row in held),
        to_active_cpu_ns=last['cpu_ns']-first['cpu_ns'], to_active_sampled_wall_ns=elapsed,
        to_active_effective_guest_cores=(last['cpu_ns']-first['cpu_ns'])/elapsed,
        selected_guest_cpus=first['affinity'],
        scope='Owned Rust peer RSS/FD/threads; startup-to-active CPU only; not total host, allocator bytes or pure NBSR object cost')


records = read(ROOT, 'records.json')
expected = [f'{mode}-1024-r{repeat}' for repeat in range(1,6)
            for mode in (('shared','split') if repeat % 2 else ('split','shared'))]
assert [row['label'] for row in records] == expected, 'incomplete or replaced cohort'
cells = []
for record in records:
    label, count = record['label'], record['count']
    cell = ROOT / label
    index = verify_index(cell)
    assert record['rate'] == 200
    assert record['owned_processes_absent_before_stop'] == dict.fromkeys(ROLES, True)
    assert all(read(ROOT, label+'-'+role+'-remaining-processes.json') == [] for role in ROLES)
    row = dict(label=label, mode=record['mode'], repeat=record['repeat'], count=count, rate=200, index_sha256=index, status=record['status'])
    if record['status'] != 'PASS_FUNCTIONAL':
        assert record['status'] == 'FAIL_RETAINED'
        row['failure'] = read(cell, 'failure.json')
        row['phase_prefix'] = [json.loads(line) for line in (cell/'management.ndjson').read_text().splitlines()]
        cells.append(row)
        continue
    endpoints = {role: check_endpoint(cell/role, role, count) for role in ROLES}
    row['pair'] = analyze(cell/'source/peer', cell/'destination/peer', source_sha=SHA, count=count)
    transcript = [json.loads(line) for line in (cell/'management.ndjson').read_text().splitlines()]
    receives = {(v['role'],v['value']['event']):v for v in transcript if v['action']=='receive'}
    sends = {(v['role'],v['value']['op']):v for v in transcript if v['action']=='send'}
    for role in ROLES:
        for name, event in endpoints[role]['events'].items():
            assert receives[role,name]['value'] == event
    hold = sends['destination','release']['timestamp_ns'] - max(receives[r,'active']['timestamp_ns'] for r in ROLES)
    cooldown = sends['destination','report_release']['timestamp_ns'] - receives['destination','report_ready']['timestamp_ns']
    assert hold >= 2_000_000_000 and cooldown >= 2_000_000_000
    assert receives['destination','released']['timestamp_ns'] <= sends['source','release']['timestamp_ns']
    cleanup = read(cell,'cleanup.json')
    assert all(v['exit_code']==0 and not v['local_relay_forced'] for v in cleanup.values())
    row['coordinator_hold_ns'], row['coordinator_cooldown_ns'] = hold, cooldown
    row['resources'] = {role:resource_summary(cell/role/'peer', endpoints[role]['events']) for role in ROLES}
    rows = [json.loads(line) for line in (cell/'source/peer/stdout').read_text().splitlines()]
    success = [v for v in rows if v.get('success') is True]
    assert len(success)==count
    row['cold_handshake_including_tls_ms'] = quantiles([v['transport_handshake_ns']/1e6 for v in success])
    row['source_admission_local_check_ms'] = quantiles([v['source_admission_ns']/1e6 for v in success])
    cells.append(row)
summary = {}
for mode in ('shared','split'):
    selected = [row for row in cells if row['mode']==mode]
    passed = [row for row in selected if row['status']=='PASS_FUNCTIONAL']
    for row in passed:
        for role in ROLES:
            expected_cpu = [1] if mode=='split' and role=='destination' else [0]
            assert row['resources'][role]['selected_guest_cpus']==expected_cpu
    summary[mode] = dict(passes=len(passed), failures=len(selected)-len(passed), repeats=len(selected))
    if len(passed)==5:
        summary[mode]['cold_handshake_median_cell_quantiles_ms'] = {
            name:statistics.median(row['cold_handshake_including_tls_ms'][name] for row in passed)
            for name in ('p50','p95','p99')}
        p99=[row['cold_handshake_including_tls_ms']['p99'] for row in passed]
        summary[mode]['p99_cv_percent']=100*statistics.stdev(p99)/statistics.mean(p99)
paired=[]
for repeat in range(1,6):
    labels=[f'{mode}-1024-r{repeat}' for mode in ('shared','split')]
    fixtures=[read(ROOT/label/role/'peer','environment.json')['fixture_sha256'] for label in labels for role in ROLES]
    assert all(value==fixtures[0] for value in fixtures)
    pair=[next(row for row in cells if row['label']==label) for label in labels]
    if all(row['status']=='PASS_FUNCTIONAL' for row in pair):
        old,new=[row['cold_handshake_including_tls_ms']['p99'] for row in pair]
        paired.append(dict(repeat=repeat, shared_p99_ms=old,split_p99_ms=new,change_percent=100*(new/old-1)))
report=dict(source_sha=SHA,summary=summary,cells=cells,paired_p99=paired,
    classification='DIAGNOSTIC_GUEST_ALLOCATION_SENSITIVITY',
    capacity='NOT_ESTABLISHED',physical_core_scaling='NOT_PROVEN',production_changes='NONE',
    timing='Cold handshake includes TLS configuration. Split doubles selected guest CPU count across roles.',
    interruption='Disk reserve stopped original driver between pairs 1 and 2; original pair retained unchanged, Cargo cache cleaned before resume.')
(OUT/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(summary,indent=2))
print(json.dumps(paired,indent=2))
