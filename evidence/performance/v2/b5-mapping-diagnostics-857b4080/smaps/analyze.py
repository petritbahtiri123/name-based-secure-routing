import collections
import json
from pathlib import Path

root = Path(__file__).parent
results = []
for path in sorted(root.glob('mappings-r*-mappings.ndjson')):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    record_path = root / path.name.removesuffix('-mappings.ndjson') / 'records.json'
    if not record_path.exists():
        continue
    record = json.loads(record_path.read_text())[0]
    report = dict(file=path.name, error=record.get('error'), valid=record['valid'], roles={})
    for role in ('server', 'nbsr'):
        selected = [r for r in rows if r.get('role') == role]
        if len(selected) < 2:
            continue
        def group(row):
            values = collections.Counter()
            for mapping in row['mappings']:
                values[mapping['name']] += mapping.get('Private_Clean', 0) + mapping.get('Private_Dirty', 0)
            return values
        first, last = group(selected[0]), group(selected[-1])
        report['roles'][role] = dict(snapshots=len(selected), elapsed_s=(selected[-1]['timestamp_ns']-selected[0]['timestamp_ns'])/1e9,
            max_capture_ns=max(r['capture_duration_ns'] for r in selected),
            changes={name: dict(first=first[name], last=last[name], delta=last[name]-first[name])
                     for name in sorted(set(first)|set(last)) if first[name] != last[name]})
    results.append(report)
(root / 'mapping-analysis.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2))
