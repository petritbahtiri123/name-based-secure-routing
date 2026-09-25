"""Replay retained Linux Go cells without asserting observer-qualified capacity."""
import json
from pathlib import Path
import statistics as stats
import sys
sys.path.insert(0, 'C:/Users/bajra/OneDrive/Documents/NBSR')
from scripts.performance.b3_go_linux_analysis import analyze_roots, analyze_cell
from scripts.performance.b3_linux_analysis import load_input
from scripts.performance.b3_v2_analysis import slope

base = Path('C:/NBSR-build/go-linux-b3-7255c9d6')
if json.loads((base/'exit.json').read_text())['exit_code'] != 0:
    raise ValueError('cohort did not complete')
document = analyze_roots([base/axis for axis in ('streams','channels','cycles')])
groups = {}
for cell in document['cells']:
    shape, repeat = cell['name'].rsplit('-r',1)
    row = dict(name=cell['name'], repeat=int(repeat), completed_operations=cell['completed_operations'], roles={})
    for role, phases in cell['roles'].items():
        cooldown = [p for p in phases['cooldown'] if p['private_resident_bytes'] is not None]
        values = [p['private_resident_bytes'] for p in cooldown]
        row['roles'][role] = dict(active_private_resident_bytes=stats.median(p['private_resident_bytes'] for p in phases['active']),
            cooldown_count=len(cooldown), unavailable_cooldown_count=len(phases['cooldown'])-len(cooldown),
            active_fd_count=stats.median(p['fd_count'] for p in phases['active']),
            active_thread_count=stats.median(p['thread_count'] for p in phases['active']),
            cooldown_first_private_bytes=values[0] if values else None,
            cooldown_last_private_bytes=values[-1] if values else None,
            cooldown_last10_range_bytes=max(values[-10:])-min(values[-10:]) if values else None,
            cooldown_last10_slope_bytes_per_cycle=slope([(p['cycle'],p['private_resident_bytes']) for p in cooldown[-10:]]) if len(cooldown)>1 else None)
    groups.setdefault(shape,[]).append(row)
for shape, rows in groups.items():
    assert sorted(r['repeat'] for r in rows) == [1,2,3,4,5], shape
summary = {}
for shape, rows in groups.items():
    roles = {}
    for role in ('source','destination'):
        values = [r['roles'][role]['active_private_resident_bytes'] for r in rows]
        roles[role] = dict(active_private_resident_median_bytes=stats.median(values),
            active_private_resident_cv=stats.stdev(values)/stats.fmean(values))
    summary[shape] = dict(repeats=5, roles=roles, rows=rows)
initial = Path('C:/NBSR-build/go-linux-b3-d88663af/streams')
cells, identity, provenance = load_input(initial,'go-rust')
baseline = [analyze_cell(c,identity['platform']['selected_cpus']) for c in cells]
assert len(baseline)==5 and all(c['completed_operations']==16 for c in baseline)
failure=json.loads((initial/'failure.json').read_text())
assert failure['classification']=='INVALID_PARTIAL' and '[Errno 3]' in failure['error']
print(json.dumps(dict(schema='go-linux-b3-followup-v1',classification='DIAGNOSTIC_SCOPED',
    completed_cells=len(document['cells']),completed_roundtrips=sum(c['completed_operations'] for c in document['cells']),
    summary=summary, retained_prior=dict(provenance=provenance,completed_cells=5,completed_roundtrips=80,failure=failure),
    analysis=document),indent=2))
