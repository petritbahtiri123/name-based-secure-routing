"""Extract the retained d0792699 B3 failure without rerunning its workload."""
import argparse
import hashlib
import json
from pathlib import Path


def analyze(root):
    index = dict(line.split('  ', 1)[::-1]
                 for line in (root / 'checksums.sha256').read_text().splitlines())
    inputs = {}

    def read(name):
        path = root / 'raw/rust-rust/bundles-1024-r1' / name
        relative = path.relative_to(root).as_posix()
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if index.get(relative) != digest:
            raise ValueError(f'unverified input: {relative}')
        inputs[relative] = digest
        return data.decode()

    failure = json.loads(read('failure.json'))
    rows = [json.loads(line) for line in read('source-0.stdout').splitlines()
            if line.startswith('{')]
    success = [r for r in rows if r.get('success') is True]
    failed = [r for r in rows if r.get('success') is False]
    ids = [r['logical_client_id'] for r in success + failed]
    if sorted(ids) != list(range(1024)):
        raise ValueError('expected exactly one outcome per client')
    samples = failure['samples']
    gaps = {}
    for role in ('source', 'destination'):
        idle = [s['timestamp_ns'] for s in samples if s['role'] == role and s['phase'] == 'idle']
        active = [s['timestamp_ns'] for s in samples if s['role'] == role and s['phase'] == 'active']
        gaps[role] = (min(active) - max(idle)) / 1e9
    return dict(classification='DIAGNOSTIC_RETAINED_FAILURE', inputs=inputs,
                successful_application_rows=len(success), failed_client_rows=len(failed),
                failed_client_ids=sorted(r['logical_client_id'] for r in failed),
                idle_to_active_sample_gap_seconds=gaps,
                successful_scenario_seconds_range=[
                    min(r['total_scenario_ns'] for r in success) / 1e9,
                    max(r['total_scenario_ns'] for r in success) / 1e9],
                cause='UNRESOLVED: idle expiry hypothesis needs close-reason evidence')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.root), indent=2))
