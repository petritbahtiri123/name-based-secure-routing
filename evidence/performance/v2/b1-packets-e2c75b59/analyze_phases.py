import json
from pathlib import Path
import statistics

root = Path('C:/NBSR-build/b1-v2-packets-e2c75b59')
records = json.loads((root / 'records.json').read_text())
analysis = json.loads(root.with_name(root.name + '-analysis.json').read_text())

def stats(values):
    mean = statistics.mean(values)
    return dict(median=statistics.median(values), minimum=min(values), maximum=max(values),
                mean=mean, sample_cv_percent=100 * statistics.stdev(values) / abs(mean) if mean else None)

def counters(row, phase):
    value = row[phase]
    return {'udp_payload_bytes': sum(value[direction]['bytes'] for direction in value),
            'udp_datagrams': sum(value[direction]['packets'] for direction in value)}

for row in records:
    assert row['capture_method'] == 'isolated-udp-relay'
    assert row['measured_unit'] == 'UDP payload bytes and UDP datagrams'
    assert row['client_ownership'] == 'OS UDP endpoint ownership must match the authorized benchmark client PID'
    assert row['rejected_datagrams'] == 0
    assert '--p2a-counter-control' in row['client_command']
    for phase in ('setup', 'established'):
        assert set(row[phase]) == {'client_to_server', 'server_to_client'}
        for direction in row[phase].values():
            assert set(direction) == {'bytes', 'packets'}
            assert all(type(value) is int and value > 0 for value in direction.values())

phase_workloads = []
for payload in (1024, 16384):
    group = [row for row in records if row['payload_bytes'] == payload]
    phases = {}
    for phase in ('setup', 'established'):
        pairs = []
        for repeat in range(1, 6):
            matched = [row for row in group if row['repeat'] == repeat]
            assert len(matched) == 2 and {row['path'] for row in matched} == {'direct', 'nbsr'}
            pair = {row['path']: counters(row, phase) for row in matched}
            pairs.append(dict(repeat=repeat, **pair, delta={key: pair['nbsr'][key] - pair['direct'][key] for key in pair['direct']}))
        phases[phase] = dict(pairs=pairs,
                            paths={path: {key: stats([pair[path][key] for pair in pairs]) for key in ('udp_payload_bytes', 'udp_datagrams')} for path in ('direct', 'nbsr')},
                            paired_delta={key: stats([pair['delta'][key] for pair in pairs]) for key in ('udp_payload_bytes', 'udp_datagrams')})
    phase_workloads.append(dict(payload_bytes=payload, streams=group[0]['streams'],
                                fixed_useful_application_bytes=group[0]['application_bytes'], phases=phases))

analysis['relay_phase_accounting'] = dict(
    classification='DIRECTLY_MEASURED_RELAY_UDP_PAYLOAD_AND_DATAGRAM_WINDOWS',
    validated_records=20,
    boundary_evidence='Successful clients require acknowledged setup-complete, measurement-start and measurement-stop before final record; relay transitions and counters share a lock. Records do not retain individual phase ACK transcripts or phase timestamps.',
    ownership_evidence='Authorized child PID checked against OS UDP endpoint ownership for first client tuple; subsequent datagrams match that tuple; all 20 records have zero rejected datagrams.',
    setup_scope='Relay creation through acknowledged setup-complete after connection and stream-open preparation. Does not include later preflight validation/materialization during excluded warmup phase.',
    established_scope='Acknowledged measurement-start before fixed-operation barrier release through acknowledged measurement-stop after one postflight validation exchange per stream plus 100 ms settling. Excludes teardown; not identical to measured_ns interval.',
    exclusions='Excluded warmup/preflight and stopped/teardown traffic mean setup plus established is not the whole-PCAP inventory.',
    denominator_scope='Fixed useful request/response bytes exclude postflight payload; no fixed-operation-only overhead claim.',
    phase_ip_udp_header_or_l2_bytes='NOT_PROVEN: no phase-aligned capture timestamps; do not relabel whole-PCAP layers.',
    workload_results=phase_workloads)
output = root.with_name(root.name + '-with-phase-analysis.json')
assert not output.exists()
output.write_text(json.dumps(analysis, indent=2) + '\n')
print(json.dumps([dict(payload_bytes=w['payload_bytes'], phases={p: v['paired_delta'] for p, v in w['phases'].items()}) for w in phase_workloads], indent=2))
