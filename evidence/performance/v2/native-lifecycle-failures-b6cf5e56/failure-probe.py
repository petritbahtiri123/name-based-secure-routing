import json,sys,os
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,'/tmp/source')
from scripts.performance.linux_socket_ownership import snapshot
from scripts.performance.linux_udp_failure import capture_owned_udp
label,address,role=sys.argv[1:];root=Path('/out')/label
pid=json.loads((root/'pid.json').read_text())['pid']
row=json.loads((root/'resources.ndjson').read_text().splitlines()[0])
binary=json.loads((root/'command.json').read_text())['argv'][3]
before=snapshot(pid,row['start_ticks'],binary,address)
assert before['status']=='MEASURED_LIVE_SOCKET_SNAPSHOT',before
# Live identity is checked both by socket snapshot and capture_owned_udp.
process=SimpleNamespace(pid=pid,poll=lambda:None)
result=capture_owned_udp({role:process},{pid:row['start_ticks']})
after=snapshot(pid,row['start_ticks'],binary,address)
assert after['status']=='MEASURED_LIVE_SOCKET_SNAPSHOT',after
print(json.dumps(dict(before=before,counters=result,after=after,trigger='first existing failed marker observed; no workload cancellation or timer changes')))
