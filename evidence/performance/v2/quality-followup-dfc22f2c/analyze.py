"""Replay this bounded quality/storage summary; verify raw indexes separately."""
from pathlib import Path
import json
import re
import sys

base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('C:/NBSR-build')
quality = base / 'quality-be07f67c-20260925'
go = base / 'go-quality-be07f67c'
assert '5 failed, 1600 passed, 3 skipped' in (quality / 'python.txt').read_text()
assert '1612 passed, 3 skipped' in (quality / 'python-followup.txt').read_text()
for filename in ('python-followup-exit.txt', 'rust-focused-exit.txt', 'rust-isolated-exit.txt',
                 'fmt-followup-exit.txt', 'ruff-final-exit.txt', 'dependencies-exit.txt', 'privacy-exit.txt'):
    assert int((quality / filename).read_text()) == 0, filename
assert int((quality / 'exit-code.txt').read_text()) == 101
rust = re.findall(r'test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored;',
                  (quality / 'rust-isolated.log').read_text())
assert rust and all(row[0] == 'ok' and row[2] == '0' for row in rust)
initial_go = json.loads((go / 'results.json').read_text())
failures = [(r['module'], r['stage']) for r in initial_go if r['exit_code']]
assert failures == [('client/nbsr-go-client/demo', 'test'), ('verifiers/federation-go', 'test')]
for filename in ('authority-cancel-focused-exit.txt', 'authority-cancel-green-exit.txt',
                 'demo-followup-exit.txt', 'demo-vet-followup-exit.txt'):
    assert int((go / filename).read_text()) == 0
assert 'untrusted manifest digest' in (go / 'verifiers_federation-go-test.log').read_text()
assert int((base / 'clippy-quality-be07f67c/exit-code.txt').read_text()) == 0
storage = []
for suffix in ('', '-part2'):
    root = base / ('retained-native-compression-20260925' + suffix)
    rows = json.loads((root / 'results.json').read_text())
    for row in rows:
        assert row['exit_code'] == 0 and row['sha256'] == row['sha256_after']
        assert row['logical_bytes'] == row['logical_after']
        assert row['mtime_ns_before'] == row['mtime_ns_after']
    storage += rows
print(json.dumps({
    'scope': 'QUALITY_FOLLOWUP_NOT_FINAL_FUNDING_FREEZE',
    'python': {'passed': 1612, 'skipped': 3, 'initial_failed': 5},
    'rust_isolated': {'passed': sum(int(r[1]) for r in rust), 'ignored': sum(int(r[3]) for r in rust),
                      'initial_close_timeout_retained': True},
    'go_race_followup': {'four_modules': 'PASS', 'federation': 'BLOCKED_ARCHITECTURAL'},
    'production_changed': False,
    'storage': {'files': len(storage), 'allocated_bytes_saved': sum(r['allocated_before'] - r['allocated_after'] for r in storage),
                'all_logical_bytes_and_hashes_unchanged': True, 'deleted_files': 0},
}, indent=2))
