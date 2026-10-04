"""Verify linked_documents against Git blob bytes, without checkout or LFS filters.

Run from the repository root:
    python -B scripts/verify_technical_evidence_index.py

Unbound entries use --commit (default HEAD, resolved once). Explicit sha256_basis
commit bindings override it. Historical Windows hashes are metadata only.
This checks linked documents, not report_sha256, package indexes or raw evidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / 'docs/benchmarks/TECHNICAL_REPORT_2026-09-28.evidence.json'
BASIS = re.compile(r'Committed Git blob bytes at ([0-9a-f]{40}); corrected \d{4}-\d{2}-\d{2}\.\Z')


def git(*args):
    result = subprocess.run(
        ['git', '-c', f'safe.directory={ROOT.as_posix()}', '-C', str(ROOT), *args],
        capture_output=True, check=False,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1"},
    )
    if result.returncode:
        raise ValueError(result.stderr.decode('utf-8', errors='replace').strip())
    return result.stdout


def verify(index, commit='HEAD'):
    data = json.loads(index.read_bytes())
    rows = data.get('linked_documents') if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError('linked_documents must be a nonempty list')
    revisions = {}

    def resolve(revision):
        if revision not in revisions:
            revisions[revision] = git('rev-parse', '--verify', '--end-of-options', revision + '^{commit}').decode().strip()
        return revisions[revision]

    default_commit = resolve(commit)
    print(f'Default Git commit: {default_commit}; explicit bindings take precedence.')
    seen = {}
    errors = []
    for ordinal, row in enumerate(rows, 1):
        path = row.get('path') if isinstance(row, dict) else None
        label = f'reference {ordinal} ({path})'
        try:
            if (not isinstance(path, str) or not path or '\\' in path or ':' in path
                    or PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts
                    or str(PurePosixPath(path)) != path):
                raise ValueError('invalid repository-relative document path')
            expected = row.get('sha256')
            if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
                raise ValueError('sha256 must be 64 lowercase hexadecimal characters')
            revision = default_commit
            if 'sha256_basis' in row:
                basis = row['sha256_basis']
                match = BASIS.fullmatch(basis) if isinstance(basis, str) else None
                if not match:
                    raise ValueError('unsupported sha256_basis; supply an explicit committed-byte binding')
                revision = resolve(match[1])
            identity = (revision, expected)
            if path in seen:
                if seen[path] != identity:
                    raise ValueError('conflicting duplicate: commit or hash differs from earlier reference')
                continue
            seen[path] = identity
            try:
                blob = git('cat-file', 'blob', f'{revision}:{path}')
            except ValueError as error:
                raise ValueError(f'missing/unreadable committed document {revision}:{path}: {error}') from error
            actual = hashlib.sha256(blob).hexdigest()
            if actual != expected:
                raise ValueError(f'hash mismatch at {revision}:{path}: expected {expected}, actual {actual}')
            print(f'PASS {revision}:{path}')
        except ValueError as error:
            errors.append(f'FAIL {label}: {error}')
    for error in errors:
        print(error)
    status = 'FAIL' if errors else 'PASS'
    print(f'{status}: {len(seen)} distinct documents / {len(rows)} references; {len(errors)} failures.')
    return 1 if errors else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('index', nargs='?', type=Path, default=DEFAULT_INDEX)
    parser.add_argument('--commit', default='HEAD', help='Git revision for entries without an explicit binding (default: HEAD)')
    args = parser.parse_args(argv)
    try:
        return verify(args.index, args.commit)
    except (OSError, ValueError) as error:
        print(f'FAIL {args.index}: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
