import json
from pathlib import Path
import sys
import statistics

sys.path.insert(0, str(Path.cwd()))
from scripts.performance.linux_native_cycle_gate import analyze, check_endpoint
from scripts.performance.linux_native_pair import verify_index
from scripts.performance.post_close_cleanup import FIELDS
from scripts.performance.b3_v2_analysis import slope

root = Path(sys.argv[1])
verify_index(root)
records = json.loads((root/'records.json').read_bytes())
assert len(records) in (3,5) and all(r['status']=='PASS_FUNCTIONAL' for r in records)
rows=[]
for record in records:
    cell=root/record['label']
    config=json.loads((cell/'config.json').read_bytes())
    cycles=config['cycles']
    assert cycles == 50
    verify_index(cell)
    result=analyze(cell/'source/peer',cell/'destination/peer',source_sha=config['source_sha'],count=cycles)
    role_rows={}
    for role in ('source','destination'):
        checked=check_endpoint(cell/role,role,cycles)
        events=checked['events']
        samples=[json.loads(line) for line in (cell/role/'peer/resources.ndjson').read_text().splitlines()]
        assert len({(s['pid'],s['start_ticks']) for s in samples})==1
        phases=[]
        for cycle in range(cycles):
            start=events['active',cycle]['timestamp_ns']
            end=events['released',cycle]['timestamp_ns']
            active=[s for s in samples if start <= s['timestamp_ns'] <= end and s['state']!='Z']
            cool_start=events['acked' if role=='source' else 'released',cycle]['timestamp_ns']
            cool_end=events['started',cycle+1]['timestamp_ns'] if cycle<cycles-1 else events['final_released',cycle]['timestamp_ns']
            cooldown=[s for s in samples if cool_start<=s['timestamp_ns']<=cool_end and s['state']!='Z']
            assert active and cooldown and all(s['fd_count_state']=='MEASURED' for s in active+cooldown)
            assert cooldown[-1]['timestamp_ns']-cooldown[0]['timestamp_ns'] >= 1_000_000_000
            assert all(type(s['fd_count']) is int and s['fd_count']>=0 and type(s['rss_bytes']) is int and s['rss_bytes']>=0
                       and len(set(s['thread_ids']))==len(s['thread_ids']) and all(type(t) is int and t>0 for t in s['thread_ids'])
                       for s in active+cooldown)
            phases.append(dict(cycle=cycle,active_samples=len(active),cooldown_samples=len(cooldown),
                active_peak_rss_bytes=max(s['rss_bytes'] for s in active),
                cooldown_last_rss_bytes=cooldown[-1]['rss_bytes'],
                cooldown_median_rss_bytes=statistics.median(s['rss_bytes'] for s in cooldown),
                cooldown_last_fd_count=cooldown[-1]['fd_count'],
                cooldown_last_threads=len(cooldown[-1]['thread_ids'])))
        points=[(row['cycle'],row['cooldown_median_rss_bytes']) for row in phases]
        tail=points[-10:]
        role_rows[role]=dict(process_epoch=[samples[0]['pid'],samples[0]['start_ticks']],cycles=phases,
            rss_slope_bytes_per_cycle=slope(points),second_half_rss_slope_bytes_per_cycle=slope(points[len(points)//2:]),
            last_ten_rss_slope_bytes_per_cycle=slope(tail),last_ten_rss_range_bytes=max(y for _,y in tail)-min(y for _,y in tail),
            first_to_last_cooldown_median_rss_delta_bytes=points[-1][1]-points[0][1],
            last_fd_delta=phases[-1]['cooldown_last_fd_count']-phases[0]['cooldown_last_fd_count'],
            last_thread_delta=phases[-1]['cooldown_last_threads']-phases[0]['cooldown_last_threads'])
    source_rows=[json.loads(line) for line in (cell/'source/peer/stdout').read_text().splitlines()]
    closed=[r for r in source_rows if str(r.get('phase','')).startswith('lifecycle_cycle_')]
    assert len(closed)==cycles
    all_zero=all(type(r.get(f)) is int and r[f]==0 for r in closed for f in FIELDS)
    rows.append(dict(label=record['label'],result=result,resources=role_rows,
        source_per_cycle_eleven_counters_zero=all_zero,
        destination_per_cycle_closed_ownership='NOT_MEASURED',
        owned_pids_absent_before_stop=record['owned_processes_absent_before_stop']))
cvs=json.loads((root/'first-three-resource-cv.json').read_bytes())
assert len(records)==(5 if any(value>.05 for value in cvs.values()) else 3)
print(json.dumps(dict(first_three_resource_cv=cvs,classification='PASS_FUNCTIONAL_SAME_PROCESS_CYCLES',trials=len(records),
    successful_cycles=sum(row['result']['cycles'] for row in rows),all_source_per_cycle_closed_ownership_zero=all(r['source_per_cycle_eleven_counters_zero'] for r in rows),
    scope='Docker/WSL namespaces; diagnostic observer; sampled process epochs; no physical/server or bytes/resource claim',
    memory_classification='DIAGNOSTIC_RSS_ONLY_NO_ALLOCATOR_ATTRIBUTION',rows=rows),indent=2))
