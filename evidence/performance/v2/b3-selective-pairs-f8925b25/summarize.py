import json,statistics
from pathlib import Path
root=Path(__file__).resolve().parent
report=json.loads((root/'analysis.json').read_text())
cells=[]
for mode in ('before','after'):
    rows=[row for row in report['rows'] if row['mode']==mode]
    metrics={}
    for group in ('idle_effective_cores','active_private_resident_bytes'):
        roles=sorted({role for row in rows for role in row[group]})
        metrics[group]={}
        for role in roles:
            values=[row[group][role] for row in rows if role in row[group]]
            mean=statistics.mean(values)
            metrics[group][role]=dict(n=len(values),median=statistics.median(values),cv=statistics.stdev(values)/mean if mean and len(values)>1 else None)
    cells.append(dict(mode=mode,metrics=metrics))
change=100*(cells[1]['metrics']['idle_effective_cores']['source']['median']/cells[0]['metrics']['idle_effective_cores']['source']['median']-1)
(root/'metrics.json').write_text(json.dumps(dict(cells=cells,source_prestart_cpu_change_percent=change,
    limitation='Idle samples are pre-start process CPU and may include setup; not isolated polling or handshake CPU.'),indent=2))
print((root/'metrics.json').read_text())
