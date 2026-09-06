import json
import os
import signal
import subprocess
import sys
import threading
import time

from scripts.performance.linux_resources import LinuxResourceSampler, sample_linux_process

cpus = [min(os.sched_getaffinity(0))]
os.sched_setaffinity(0, cpus)
child = subprocess.Popen([sys.executable, '-u', '-c',
    'import time; payload=bytearray(8*1024*1024); print("READY",flush=True); time.sleep(20)'],
    stdout=subprocess.PIPE, text=True)
sampler = None
try:
    assert child.stdout.readline().strip() == 'READY'
    captured = threading.Event()
    def sink(row):
        print(json.dumps({'event': 'resource', 'sample': row}), flush=True)
        captured.set()
    sampler = LinuxResourceSampler({'child': child.pid}, cpus, interval_seconds=.1,
                                   max_records=20, record_sink=sink)
    sampler.start()
    assert captured.wait(3)
    sampler.check_health(require_running=True)
    rows = sampler.stop()
    sampler = None
    assert rows and rows[0]['private_resident_bytes'] >= 8*1024*1024
    os.kill(child.pid, signal.SIGTERM)
    end = time.monotonic() + 3
    while os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
        assert time.monotonic() < end
        time.sleep(.01)
    final = sample_linux_process(child.pid, cpus)
    assert final['start_ticks'] == rows[0]['start_ticks'] and final['state'] == 'Z'
    assert final['memory_state'] == 'UNAVAILABLE_ZOMBIE' and final['private_resident_bytes'] is None
    print(json.dumps({'event': 'zombie', 'sample': final}), flush=True)
finally:
    if sampler is not None:
        sampler.stop()
    if child.poll() is None:
        child.kill()
    child.wait(timeout=3)
print(json.dumps({'result': 'PASS', 'scope': 'restricted Linux container compatibility only',
                  'owned_child_joined': True}), flush=True)
