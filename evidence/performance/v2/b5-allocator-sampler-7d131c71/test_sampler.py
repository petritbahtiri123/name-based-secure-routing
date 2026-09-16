"""Fixture checks only; this does not qualify a performance observer."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path('/out')
lib = root / sys.argv[1]
with tempfile.TemporaryDirectory(dir=root) as directory:
    env = dict(os.environ, LD_PRELOAD=str(lib), NBSR_ALLOCATOR_TRACE_DIR=directory)
    process = subprocess.run([str(root / 'perf_rust_source'), 'large'], env=env,
                             capture_output=True, text=True, check=True, timeout=5)
    files = list(Path(directory).glob('*.ndjson'))
    assert len(files) == 1, 'expected exactly one allocator trace'
    rows = [json.loads(line) for line in files[0].read_text().splitlines()]
    assert len(rows) >= 2, 'expected initial and final records'
    assert rows[0]['phase'] == 'sample' and rows[-1]['phase'] == 'final'
    assert len({row['pid'] for row in rows}) == 1
    assert all(row['timestamp_ns'] <= row['end_ns'] and row['uordblks'] >= 0
               and row['hblkhd'] >= 0 for row in rows)
    assert all(a['timestamp_ns'] <= b['timestamp_ns'] for a, b in zip(rows, rows[1:]))
    assert len(process.stdout.splitlines()) == 6, 'fixture output changed'
    print('PASS: activated sampler, initial/final records, bounded join, fixture output')
with tempfile.TemporaryDirectory(dir=root) as directory:
    env = dict(os.environ, LD_PRELOAD=str(lib), NBSR_ALLOCATOR_TRACE_DIR=directory)
    subprocess.run(['/bin/true'], env=env, check=True, timeout=5)
    assert not list(Path(directory).iterdir()), 'unselected executable traced'
    print('PASS: unselected executable produces no trace')
env = dict(os.environ, LD_PRELOAD=str(lib))
env.pop('NBSR_ALLOCATOR_TRACE_DIR', None)
subprocess.run([str(root / 'perf_rust_source'), 'large'], env=env,
               stdout=subprocess.DEVNULL, check=True, timeout=5)
print('PASS: absent opt-in executes normally')
