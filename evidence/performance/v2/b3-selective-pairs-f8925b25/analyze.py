import hashlib,json,re,statistics
from pathlib import Path
root=Path(__file__).resolve().parent
attempts=json.loads((root/'results.json').read_text())
assert len(attempts)==10
rows=[];verified=0
for attempt in attempts:
    case=root/f"{attempt['mode']}-r{attempt['repeat']}"
    for line in (case/'checksums.sha256').read_text().splitlines():
        expected,name=line.split('  ',1);path=(case/name).resolve()
        assert path.is_relative_to(case.resolve())
        with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==expected
        verified+=1
    raw=case/'raw/rust-rust/live-bundles-2048-r1'
    passed=attempt['exit_code']==0
    data=json.loads((raw/('cell.json' if passed else 'failure.json')).read_text())
    row=dict(mode=attempt['mode'],repeat=attempt['repeat'],exit_code=attempt['exit_code'],passed=passed)
    if passed:
        assert data['active_count']==2048
        assert data['cleanup']['all_zero'] and data['cleanup']['source_all_zero']
        assert data['cleanup']['destination_exited'] and data['cleanup']['source_processes_exited']
        row.update(active_count=2048,cleanup=data['cleanup'],start_rate=data['start_rate'],accept_window=data['accept_window'])
    else:
        snapshot=json.loads((raw/'failure-markers.json').read_text())
        assert snapshot['status']=='CAPTURED'
        names={r['name'] for r in snapshot['markers']}
        row['source_active']=sum(bool(re.fullmatch(r'connection-\d+\.active',n)) for n in names)
        row['destination_active']=sum(bool(re.fullmatch(r'destination-\d+\.active',n)) for n in names)
        row['active_count']=min(row['source_active'],row['destination_active'])
        row['missing_connected']=sum(f'connection-{i}.connected' not in names for i in range(2048))
        row['handshake_timeout_mentions']=sum(p.read_text().count('HandshakeTimeout') for p in raw.glob('source*.stderr'))
        row['cleanup']='FAILED_CELL_NOT_ACCEPTED'
    idle={};memory={}
    samples=data.get('samples',[])
    for role in sorted({s['role'] for s in samples}):
        selected=sorted((s for s in samples if s['role']==role and s['phase']=='idle'),key=lambda s:s['timestamp_ns'])
        if len(selected)>=2:
            a,b=selected[0],selected[-1]
            idle[role]=(b['cpu_ns']-a['cpu_ns'])/(b['timestamp_ns']-a['timestamp_ns'])
        live=[s for s in samples if s['role']==role and s['phase']=='active']
        values=[s.get('private_resident_bytes') for s in live]
        if values and all(type(v) is int for v in values): memory[role]=statistics.median(values)
    row['idle_effective_cores']=idle
    row['active_private_resident_bytes']=memory
    rows.append(row)
summary=[]
for mode in ('before','after'):
    selected=[r for r in rows if r['mode']==mode]
    assert sorted(r['repeat'] for r in selected)==[1,2,3,4,5]
    roles=sorted({role for row in selected for role in row['idle_effective_cores']})
    summary.append(dict(mode=mode,passed=sum(r['passed'] for r in selected),failed=sum(not r['passed'] for r in selected),
        median_active=statistics.median(r['active_count'] for r in selected),
        median_idle_cores={role:statistics.median(r['idle_effective_cores'][role] for r in selected if role in r['idle_effective_cores']) for role in roles}))
report=dict(classification='MATCHED_B3_HARNESS_COMPARISON',indexed_files_verified=verified,rows=rows,summary=summary,
    limitations=['Guest CPU, not dedicated physical-core or server capacity.',
                 'Idle CPU is pre-start harness cost, not handshake CPU attribution.',
                 'Failed cells remain failures; no accepted cleanup inferred for them.'])
(root/'analysis.json').write_text(json.dumps(report,indent=2))
print(json.dumps(summary,indent=2))
