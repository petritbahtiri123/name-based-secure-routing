import json
from pathlib import Path
import re
import statistics

root=Path(__file__).resolve().parent
text=(root/'run.log').read_text()
assert 'test result: ok. 1 passed; 0 failed' in text
rows=[]
for line in text.splitlines():
    if 'PACED_CPU ' not in line:
        continue
    fields=dict(re.findall(r'(\w+)=(\w+)',line.split('PACED_CPU ',1)[1]))
    row={k:v if k=='mode' else int(v) for k,v in fields.items()}
    assert row['completed']==row['count']==2048
    assert row['offered_per_second']==100
    assert row['elapsed_ns']>=20_470_000_000
    row['cpu_percent']=row['cpu_ticks']/row['hz']/(row['elapsed_ns']/1e9)*100
    rows.append(row)
assert len(rows)==10
cells=[]
for mode in ('monitor','event'):
    values=[r for r in rows if r['mode']==mode]
    assert sorted(r['repeat'] for r in values)==[1,2,3,4,5]
    summary={'mode':mode,'repeats':5,'completed_per_repeat':2048}
    for field in ('cpu_percent','wake_p50_ns','wake_p95_ns','wake_p99_ns','publish_lateness_p99_ns'):
        data=[r[field] for r in values]
        summary[field]={'median':statistics.median(data),'cv':statistics.stdev(data)/statistics.mean(data),
                        'min':min(data),'max':max(data)}
    cells.append(summary)
comparisons={field:100*(cells[1][field]['median']/cells[0][field]['median']-1)
             for field in ('cpu_percent','wake_p50_ns','wake_p95_ns','wake_p99_ns')}
report=dict(classification='OFFLINE_DIAGNOSTIC_NOT_INTEGRATED',rows=rows,cells=cells,
            prototype_change_percent=comparisons,
            limitations=['CPU includes publisher and waiter tasks in both arms.',
                         'No QUIC, no handshake/admission capacity, no production memory result.',
                         'Selective-name prototype; fixed native directory and regular marker paths only.'])
(root/'analysis.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'cells':cells,'prototype_change_percent':comparisons},indent=2))
