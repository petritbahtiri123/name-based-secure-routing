import json,sys
from pathlib import Path
sys.path.insert(0,'/tmp/source')
from scripts.performance.linux_socket_ownership import snapshot,validate_binding
root=Path('/out')/sys.argv[1];address=sys.argv[2]
pid=json.loads((root/'pid.json').read_text())['pid']
row=json.loads((root/'resources.ndjson').read_text().splitlines()[0])
binary=json.loads((root/'command.json').read_text())['argv'][3]
result=snapshot(pid,row['start_ticks'],binary,address)
assert result['status']=='MEASURED_LIVE_SOCKET_SNAPSHOT',result
for entry in result['sockets']:
 validate_binding(result,pid=pid,start_ticks=row['start_ticks'],binary=binary,local=entry['local'])
print(json.dumps(result))
