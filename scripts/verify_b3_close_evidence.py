"""Verify complete failure-only B3 diagnostics against retained client outcomes."""
import argparse
import collections
import hashlib
import json
from pathlib import Path


def verify(root):
    root = root.resolve()
    index = {}
    for line in (root / 'checksums.sha256').read_text().splitlines():
        digest, name = line.split('  ', 1)
        path = (root / name).resolve()
        if not path.is_relative_to(root) or path in index:
            raise ValueError('invalid checksum path')
        index[path] = digest

    def read(path):
        data = path.read_bytes()
        if index.get(path.resolve()) != hashlib.sha256(data).hexdigest():
            raise ValueError('unverified input')
        return data.decode()

    cell = root / 'raw/rust-rust/bundles-1024-r1'
    diagnostics = [json.loads(line) for line in read(cell / 'source-0.stderr').splitlines()
                   if 'nbsr-b3-close-diagnostic-v1' in line]
    outcomes = [json.loads(line) for line in read(cell / 'source-0.stdout').splitlines()
                if line.startswith('{')]
    outcomes = [row for row in outcomes if type(row.get('success')) is bool]
    if sorted(row['logical_client_id'] for row in outcomes) != list(range(1024)):
        raise ValueError('incomplete or duplicate client outcomes')
    failed = sorted(row['logical_client_id'] for row in outcomes if not row['success'])
    if not failed or sorted(row['logical_client_id'] for row in diagnostics) != failed:
        raise ValueError('failure/diagnostic identity mismatch')
    for row in diagnostics:
        if (row.get('role') != 'source' or row.get('clock_origin') != 'connection_attempt'
                or row.get('close_reason') not in ('not_closed', 'timed_out', 'other_closed')
                or not 0 <= row['prepared_elapsed_ns'] <= row['released_elapsed_ns'] <= row['failed_elapsed_ns']):
            raise ValueError('invalid failure diagnostic')
    groups = {}
    for reason in sorted({r['close_reason'] for r in diagnostics}):
        selected = [r for r in diagnostics if r['close_reason'] == reason]
        held = [(r['released_elapsed_ns'] - r['prepared_elapsed_ns']) / 1e9 for r in selected]
        groups[reason] = dict(count=len(selected), held_seconds_range=[min(held), max(held)])
    return dict(classification='PASS_DIAGNOSTIC_COMPLETENESS_NOT_CAPACITY',
                failed=len(failed), successful=1024-len(failed), categories=groups,
                failed_id_range=[min(failed), max(failed)],
                failure_types=dict(collections.Counter(row.get('error') for row in outcomes if not row['success'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.root), indent=2))
