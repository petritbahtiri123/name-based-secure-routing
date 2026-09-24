"""Finite coordinator before/after integrity; diagnostic throughput only."""
import json
from pathlib import Path
import statistics
import sys
sys.path.insert(0,str(Path.cwd()))
from scripts.performance.linux_native_pair import analyze_pair,verify_index,read
from scripts.performance.linux_native_finite_run import check_endpoint

OUT=Path(__file__).resolve().parent
cohorts=[]
for sha in ('0866ca47','f3814929'):
    root=Path('C:/NBSR-build/native-finite-'+sha)
    source_sha=(Path('C:/NBSR-build/linux-current-'+sha)/'source-sha.txt').read_text().strip()
    rows=read(root,'records.json')
    expected=[f'{path}-r{repeat}' for repeat in range(1,6)
              for path in (('direct','nbsr') if repeat%2 else ('nbsr','direct'))]
    assert [r['label'] for r in rows]==expected
    cells=[]
    for row in rows:
        cell=root/row['label']
        index=verify_index(cell)
        assert all(not r['local_relay_forced'] for r in read(cell,'cleanup.json').values())
        peer=analyze_pair(cell/'source/peer',cell/'destination/peer',source_sha=source_sha)
        entry=dict(label=row['label'],path=row['path'],controller_status=row['status'],index_sha256=index,peer=peer)
        record=read(cell/'source/peer','validated-result.json')
        entry['latency_ns']={q:record[q+'_latency_ns'] for q in ('p50','p95','p99')}
        entry['operations']=record['completed_operations']
        if row['status']=='PASS_FUNCTIONAL':
            endpoints={role:check_endpoint(cell/role,role) for role in ('source','destination')}
            messages=[json.loads(line) for line in (cell/'management.ndjson').read_text().splitlines()]
            receives={(r['role'],r['value']['event']):r for r in messages if r['action']=='receive'}
            for role,endpoint in endpoints.items():
                assert all(receives[role,name]['value']==event for name,event in endpoint['events'].items())
            source_exit=next(r for r in messages if r['action']=='exit' and r['role']=='source')
            ack=next(r for r in messages if r['action']=='send' and r['role']=='destination' and r['value']['op']=='ack')
            assert source_exit['code']==0 and source_exit['timestamp_ns']<=ack['timestamp_ns']
            assert all(r['exit_code']==0 for r in read(cell,'cleanup.json').values())
            if row['path']=='nbsr':
                assert (cell/'destination/completion.ack').exists()
                assert not (cell/'destination/peer/completion.ack').exists()
        else:
            assert sha=='0866ca47' and row['path']=='nbsr'
            assert read(cell/'destination','failure.json')['error']=='peer completed before control handshake'
            entry['classification']='CONTROLLER_ONLY_FALSE_FAILURE_RETAINED'
        cells.append(entry)
    summary={}
    for path in ('direct','nbsr'):
        selected=[r for r in cells if r['path']==path]
        passed=[r for r in selected if r['controller_status']=='PASS_FUNCTIONAL']
        summary[path]=dict(passes=len(passed),failures=len(selected)-len(passed))
        if len(passed)==5:
            rates=[r['peer']['application_gbps'] for r in passed]
            summary[path].update(median_gbps=statistics.median(rates),gbps_cv_percent=100*statistics.stdev(rates)/statistics.mean(rates),
                median_cell_latency_ns={q:statistics.median(r['latency_ns'][q] for r in passed) for q in ('p50','p95','p99')})
    cohorts.append(dict(source_sha=source_sha,summary=summary,cells=cells))
cancel_root=Path('C:/NBSR-build/native-finite-eof-f3814929')
cancel_rows=read(cancel_root,'records.json')
assert [r['label'] for r in cancel_rows]==[f'nbsr-{role}-eof-r{repeat}' for repeat in range(1,4) for role in ('source','destination')]
cancellations=[]
for row in cancel_rows:
    assert row['status']=='PASS_CANCEL_CONTROL'
    cell=cancel_root/row['label']
    index=verify_index(cell)
    assert all(not value['local_relay_forced'] for value in read(cell,'cleanup.json').values())
    for role in ('source','destination'):
        verify_index(cell/role)
        assert (cell/role/'failure.json').exists() and not (cell/role/'result.json').exists()
        active=read(cell,role+'-active-process.json')
        assert active['pid']==read(cell/role/'peer','pid.json')['pid']
        assert active['exe'].startswith('/tmp/binaries/')
        assert read(cell/role/'peer','forced-cleanup.json')['group_killed'] is True
        assert (cell/(role+'-owned-pid-absent.txt')).read_text().strip()=='OWNED_PID_ABSENT'
    cancellations.append(dict(label=row['label'],index_sha256=index,status='PASS_CATCHABLE_EOF_CLEANUP'))
report=dict(cohorts=cohorts,cancellations=cancellations,timing='DIAGNOSTIC_ONLY',strict_stable='NOT_ESTABLISHED',soak='NOT_RUN',
    runtime_ownership='NOT_MEASURED',physical_core_capacity='NOT_PROVEN',production_changes='NONE',
    scan_limit='Initial absence scans match output-root paths only or skip unreadable proc entries; process cleanup relies on owned terminal/reap evidence. Separate EOF controls use exact live PID then explicit PID absence under same UID.')
(OUT/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps([{r['source_sha']:r['summary']} for r in cohorts],indent=2))
