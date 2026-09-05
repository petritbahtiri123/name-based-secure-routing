import hashlib
import json
from pathlib import Path
import statistics

root = Path('C:/NBSR-build/b1-v2-packets-e2c75b59')
records = json.loads((root / 'records.json').read_text())
environment = json.loads((root / 'environment.json').read_text())
assert len(records) == 20
layers = ('captured_frame_bytes', 'ip_bytes', 'udp_bytes', 'udp_payload_bytes')

def stats(values):
    mean = statistics.mean(values)
    return dict(median=statistics.median(values), minimum=min(values), maximum=max(values),
                mean=mean, sample_cv_percent=100 * statistics.stdev(values) / abs(mean) if mean else None)

for row in records:
    observer = row['packet_observer']
    account = observer['packet_accounting']
    drop = observer['capture_drops']
    assert observer['valid'] and observer['readiness']['status'] == 'PASS'
    assert drop['captured'] == drop['received'] == account['capture_inventory_packets']
    assert all(drop[key] == 0 for key in ('dropped', 'pcap_drops', 'dumpcap_drops', 'flushed', 'interface_drops'))
    assert account['capture_inventory_packets'] == account['packet_count'] + account['readiness_probe_packets']
    assert account['capture_inventory_frame_bytes'] == account['captured_frame_bytes'] + account['readiness_probe_frame_bytes']
    assert observer['packet_count'] == account['packet_count'] and observer['flow_count'] == 1
    assert row['completed_operations'] == row['expected_operations'] == row['streams'] * 1000
    assert not any(row[key] for key in ('errors', 'timeouts', 'missing', 'duplicates', 'corrupt', 'wrong_request', 'rejected_datagrams'))

workloads = []
for payload in (1024, 16384):
    group = [row for row in records if row['payload_bytes'] == payload]
    pairs = []
    for repeat in range(1, 6):
        pair = {row['path']: row for row in group if row['repeat'] == repeat}
        assert set(pair) == {'direct', 'nbsr'}
        direct, nbsr = pair['direct'], pair['nbsr']
        assert direct['application_bytes'] == nbsr['application_bytes']
        pairs.append(dict(repeat=repeat, application_bytes=direct['application_bytes'],
                          delta_bytes={key: nbsr['packet_observer']['packet_accounting'][key] - direct['packet_observer']['packet_accounting'][key] for key in layers}))
    workloads.append(dict(payload_bytes=payload, streams=group[0]['streams'], operations_per_stream=1000,
                          application_bytes=group[0]['application_bytes'], pairs=pairs,
                          paths={path: {key: stats([row['packet_observer']['packet_accounting'][key] for row in group if row['path'] == path]) for key in layers} for path in ('direct', 'nbsr')},
                          paired_delta={key: stats([pair['delta_bytes'][key] for pair in pairs]) for key in layers},
                          paired_delta_percent_useful_application_bytes={key: stats([100 * pair['delta_bytes'][key] / pair['application_bytes'] for pair in pairs]) for key in layers}))

analysis = dict(schema='nbsr-b1-v2-paired-accounting-analysis-v1', source=environment,
                records_sha256=hashlib.sha256((root/'records.json').read_bytes()).hexdigest(),
                capture_gates=dict(valid_captures=20, matched_pairs=10, readiness_pass=20, zero_capture_loss=20,
                                   exact_inventory=20, completed_operation_and_error_gates=20),
                qualifications=['Whole-capture server-facing loopback leg only, including setup, untimed validation and teardown.',
                                'Byte denominator includes useful fixed request/response payload only; not a phase-aligned established overhead ratio.',
                                'CV uses sample standard deviation divided by absolute mean; descriptive only, no timing/capacity gate.',
                                'Established-only packet split NOT_PROVEN; physical Ethernet NOT_MEASURED; no performance/capacity claim.'],
                workloads=workloads)
output = root.with_name(root.name + '-analysis.json')
output.write_text(json.dumps(analysis, indent=2) + '\n')
print(json.dumps(dict(gates=analysis['capture_gates'], workloads=[dict(payload_bytes=w['payload_bytes'], paired_delta=w['paired_delta']) for w in workloads]), indent=2))
