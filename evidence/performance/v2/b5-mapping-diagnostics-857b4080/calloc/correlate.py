import json
from pathlib import Path
import re

root = Path(__file__).parent
results = []
for trace in sorted(root.glob('mappings-r*-calloc.txt')):
    prefix = trace.name.removesuffix('-calloc.txt')
    snapshots = [json.loads(line) for line in (root / (prefix+'-mappings.ndjson')).read_text().splitlines()]
    for pid, size, pointer in re.findall(r'CALLOC pid=(\d+) bytes=(\d+) pointer=(0x[0-9a-f]+)', trace.read_text()):
        pid, size, pointer = int(pid), int(size), int(pointer,16)
        matched = []
        for snapshot in snapshots:
            if snapshot.get('pid') != pid:
                continue
            for mapping in snapshot['mappings']:
                begin,end = [int(part,16) for part in mapping['address_range'].split('-')]
                if begin <= pointer and pointer+size <= end:
                    matched.append(dict(role=snapshot['role'], timestamp_ns=snapshot['timestamp_ns'],
                        mapping_size=mapping['Size'], private_resident=mapping['Private_Clean']+mapping['Private_Dirty'],
                        name=mapping['name']))
        if matched:
            results.append(dict(repeat=prefix, pid=pid, allocated_bytes=size, snapshots=matched,
                mapping_sizes=sorted({m['mapping_size'] for m in matched}),
                private_delta=matched[-1]['private_resident']-matched[0]['private_resident'],
                maximum_private=max(m['private_resident'] for m in matched)))
(root/'allocation-correlation.json').write_text(json.dumps(results,indent=2))
print(json.dumps([{k:v for k,v in r.items() if k!='snapshots'} for r in results],indent=2))
