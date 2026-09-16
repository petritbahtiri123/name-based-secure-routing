import json, os, pathlib, subprocess, sys, tempfile
root=pathlib.Path('/out')
lib=root/sys.argv[1]
with tempfile.TemporaryDirectory(dir=root) as d:
 env=dict(os.environ, LD_PRELOAD=str(lib), NBSR_ALLOCATOR_TRACE_DIR=d)
 p=subprocess.run([str(root/'perf_rust_source'),'large'],env=env,capture_output=True,text=True,check=True)
 files=list(pathlib.Path(d).glob('*.ndjson'))
 assert len(files)==1, 'expected exactly one allocator trace'
 rows=[json.loads(x) for x in files[0].read_text().splitlines()]
 assert len(rows)>=2, 'expected initial and final records'
 assert rows[0]['phase']=='sample' and rows[-1]['phase']=='final'
 assert len({r['pid'] for r in rows})==1
 assert all(r['timestamp_ns']<=r['end_ns'] and r['uordblks']>=0 and r['hblkhd']>=0 for r in rows)
 assert all(a['timestamp_ns']<=b['timestamp_ns'] for a,b in zip(rows,rows[1:]))
 assert len(p.stdout.splitlines())==6, 'fixture output changed'
 print('PASS: activated sampler, parseable initial/final records, process exit, fixture output')
with tempfile.TemporaryDirectory(dir=root) as d:
 env=dict(os.environ,LD_PRELOAD=str(lib)); env.pop('NBSR_ALLOCATOR_TRACE_DIR',None)
 subprocess.run([str(root/'perf_rust_source'),'large'],env=env,stdout=subprocess.DEVNULL,check=True)
 assert not list(pathlib.Path(d).iterdir())
 print('PASS: absent opt-in executes normally')
