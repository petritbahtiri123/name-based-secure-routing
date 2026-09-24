"""Historical same-engine peer lifetime CPU occupancy, not a physical-core ceiling."""
import argparse
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.performance.linux_native_pair import analyze_pair, verify_index

SHA = 'ac40740c73c70c3661140ed613f61b693abbf1a9'


def analyze(root):
    index = verify_index(root)
    records = json.loads((root / 'records.json').read_bytes())
    assert len(records) == 10
    output, seen = [], set()
    for record in records:
        label = record['label']
        assert label not in seen and record['status'] == 'PASS_FUNCTIONAL'
        seen.add(label)
        analyze_pair(root / label / 'source/peer', root / label / 'destination/peer', source_sha=SHA)
        config = json.loads((root / (label + '-config.json')).read_bytes())
        inspect = json.loads((root / (label + '-containers-before.json')).read_bytes())
        deltas, starts, ends = [], [], []
        for role in ('source', 'destination'):
            peer = root / label / role / 'peer'
            env = json.loads((peer / 'environment.json').read_bytes())
            assert env['linux_environment']['selected_cpus'] == [0]
            assert config[role]['transport'] == 'docker'
            host = inspect[role]['HostConfig']
            assert host['Privileged'] is False and not host['CapAdd']
            assert host['Runtime'] == 'runc'
            rows = [json.loads(line) for line in (peer / 'resources.ndjson').read_text().splitlines()]
            pid = json.loads((peer / 'pid.json').read_bytes())['pid']
            assert len(rows) >= 2
            for i, row in enumerate(rows):
                assert row['pid'] == pid and row['affinity'] == [0]
                assert row['start_ticks'] == rows[0]['start_ticks']
                if i:
                    assert row['timestamp_ns'] > rows[i-1]['timestamp_ns']
                    assert row['cpu_ns'] >= rows[i-1]['cpu_ns']
            deltas.append(rows[-1]['cpu_ns'] - rows[0]['cpu_ns'])
            starts.append(rows[0]['timestamp_ns'])
            ends.append(rows[-1]['timestamp_ns'])
        assert max(starts) < min(ends), 'sampled lifetimes must overlap'
        duration = max(ends) - min(starts)
        output.append(dict(label=label, path=record['path'], summed_cpu_ns=sum(deltas),
            union_lifetime_ns=duration, allocated_guest_cpu_percent=100 * sum(deltas) / duration))
    assert all(row['allocated_guest_cpu_percent'] >= 90 for row in output)
    return dict(source_sha=SHA, raw_index_sha256=index, classification='HISTORICAL_DERIVED_DIAGNOSTIC',
        rows=output, medians={mode: statistics.median(row['allocated_guest_cpu_percent']
            for row in output if row['path'] == mode) for mode in ('direct', 'nbsr')},
        formula='sum of both peer CPU deltas divided by union of their overlapping sampled lifetime intervals',
        clock_scope='same retained local Docker/WSL engine with ordinary unprivileged runc containers; never valid for independent host clocks',
        conclusion='combined peers occupy over 90% of their single allocated guest CPU over sampled lifetimes',
        limitations='includes startup/warmup/drain; excludes harness CPU; no steady CPU ns/op, physical-core proof, whole-host ceiling, stable capacity or production call-stack attribution')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    print(json.dumps(analyze(parser.parse_args().root), indent=2))
