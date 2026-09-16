import hashlib
import json
import re
import statistics
from pathlib import Path

root=Path(__file__).resolve().parent
log=(root/'run.log').read_text()
assert 'test result: ok.' in log
pattern=r'MONITOR_CPU mode=(\w+) count=(\d+) unrelated=(\d+) repeat=(\d+) cpu_ticks=(\d+) hz=(\d+) elapsed_ns=(\d+)'
rows=[]
for mode,count,unrelated,repeat,ticks,hz,elapsed in re.findall(pattern,log):
    rows.append(dict(mode=mode,count=int(count),unrelated=int(unrelated),repeat=int(repeat),
                     cpu_ticks=int(ticks),hz=int(hz),elapsed_ns=int(elapsed),
                     cpu_percent=100*int(ticks)/int(hz)/(int(elapsed)/1e9)))
assert len(rows)==30
cells=[]
for unrelated in (0,8192):
    for mode in ('monitor','event','pending'):
        cell=[r for r in rows if r['mode']==mode and r['unrelated']==unrelated]
        assert sorted(r['repeat'] for r in cell)==[1,2,3,4,5]
        values=[r['cpu_percent'] for r in cell]
        mean=statistics.mean(values)
        cells.append(dict(mode=mode,unrelated=unrelated,repeats=5,median_cpu_percent=statistics.median(values),
                          cv=statistics.stdev(values)/mean if mean else None,
                          min_cpu_percent=min(values),max_cpu_percent=max(values)))
report=dict(classification='OFFLINE_FEASIBILITY_ONLY_NOT_INTEGRATED', rows=rows,cells=cells,
    source_archive_base='91a88774ac6780b209dce15c562d453d1ab0a40f',
    repository_head_at_probe='a0fb3b36887d66e9b3ae817b129cb2b6ba8b9f9e',
    baseline_module_sha256=hashlib.sha256((root/'marker_monitor.rs').read_bytes()).hexdigest(),
    limitations=['No QUIC traffic; idle absent regular-file waiters on native container filesystem.',
                 'Single guest logical CPU selected; no dedicated physical-core capacity claim.',
                 'Prototype assumes one directory and regular marker paths; unsupported as a general backend.',
                 'Any directory event causes a full scan; continuous marker writes may erase the idle benefit.',
                 'Per-process CPU tick resolution is 10ms; low-cost arm CV is quantized.',
                 'No accepted live admission or memory/p99 fix follows from this experiment.'])
(root/'analysis.json').write_text(json.dumps(report,indent=2))
print(json.dumps(cells,indent=2))
