"""Offline grouped-progress adapter. No imports from, or execution of, NBSR.

Contracts inspected: scripts/performance/b5_grouped.py and linux_native_paced.py.
Structural errors quarantine a document. Semantic failures retain an invalid
observation; they never become a green chart or a discarded failed experiment.
"""
import math
import statistics
from .adapters import base, gate

ENVELOPE = 'nbsr-performance-lab-snapshot-v1'
PROGRESS_SCHEMA = 'nbsr-b5-grouped-progress-v1'
FINAL_SCHEMA = 'nbsr-b5-grouped-final-v1'
COUNTERS = ('offered','reserved','issued','completed','missed','unreserved_current')
QUANTILES = ('p50_latency_ns','p95_latency_ns','p99_latency_ns')
PROGRESS_FIELDS = {'schema','event','window_index','phase','elapsed_ns','interval_start_ns',
    'issue_deadline_ns','interval_end_ns',*COUNTERS,'group_counters','goodput_bytes_per_second',
    'sample_count','sample_stride','sample_capacity','sample_overflow_count',*QUANTILES,
    'max_reservation_lateness_ns','errors','timeouts','evidence_valid'}
FINAL_FIELDS = {'schema','groups','payload_bytes','streams_per_group','outstanding_per_stream',
    'measurement_duration_ns','drain_duration_ns',*COUNTERS,'group_counters','max_outstanding_observed',
    'errors','timeouts','collector_overflow_count','all_groups_joined','source_cleanup','evidence_valid'}


def uint(v, name):
    if type(v) is not int or not 0 <= v < 2**64:
        raise ValueError(f'{name} must be an unsigned 64-bit integer')
    return v


def validate_shape(row):
    if not isinstance(row,dict): raise ValueError('Every record must be an object')
    schema=row.get('schema')
    if schema not in (PROGRESS_SCHEMA,FINAL_SCHEMA): raise ValueError('Unsupported grouped record schema')
    required=PROGRESS_FIELDS if schema==PROGRESS_SCHEMA else FINAL_FIELDS
    if set(row)!=required: raise ValueError('Grouped record has missing or unsupported fields')
    skip={'schema','event','phase','group_counters','evidence_valid','goodput_bytes_per_second',
          'all_groups_joined','source_cleanup',*QUANTILES}
    for key in required-skip: uint(row[key],key)
    if type(row['evidence_valid']) is not bool: raise ValueError('evidence_valid must be boolean')
    groups=row['group_counters']
    if not isinstance(groups,list) or not 1<=len(groups)<=4: raise ValueError('Expected 1–4 group counters')
    for group in groups:
        if not isinstance(group,dict) or set(group)!={'group_id',*COUNTERS}:
            raise ValueError('Invalid group counter fields')
        for k,v in group.items(): uint(v,k)
    if schema==PROGRESS_SCHEMA:
        if type(row['event']) is not str or type(row['phase']) is not str: raise ValueError('Event and phase must be text')
        value=row['goodput_bytes_per_second']
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:
            raise ValueError('Goodput must be finite and nonnegative')
        for q in QUANTILES:
            if row[q] is not None: uint(row[q],q)
    elif type(row['all_groups_joined']) is not bool or not isinstance(row['source_cleanup'],dict):
        raise ValueError('Invalid final ownership fields')


def normalize_grouped(records, metadata=None, truncated_tail=False, record_numbers=None):
    metadata={} if metadata is None else metadata
    if not isinstance(metadata,dict) or set(metadata)-{'label','implementation','payload_bytes'}:
        raise ValueError('Snapshot metadata accepts only label, implementation and payload_bytes')
    if 'label' in metadata and (type(metadata['label']) is not str or not 1<=len(metadata['label'])<=120):
        raise ValueError('Snapshot label must be 1–120 characters')
    implementation=metadata.get('implementation')
    if implementation is not None and implementation not in ('direct-quic','rust-rust','go-rust'):
        raise ValueError('Unsupported declared implementation')
    payload=metadata.get('payload_bytes')
    if payload is not None and (type(payload) is not int or payload not in (1024,16384)):
        raise ValueError('Supported payload sizes are 1024 and 16384 bytes')
    if not isinstance(records,list) or not 1<=len(records)<=4096:
        raise ValueError('Expected 1–4096 grouped records')
    for row in records: validate_shape(row)
    progresses=[r for r in records if r['schema']==PROGRESS_SCHEMA]
    finals=[r for r in records if r['schema']==FINAL_SCHEMA]
    if not progresses: raise ValueError('A snapshot needs at least one progress record')
    final=finals[-1] if finals else None
    if final and payload is None: payload=final['payload_bytes']
    findings=[]
    def check(ok,detail):
        if not ok and detail not in findings: findings.append(detail)
    group_count=len(progresses[0]['group_counters'])
    prior=None; previous_groups=None; last_end=0; last_index=0; deadline=None; sampling=None
    final_seen=False; windows=[]
    numbers=record_numbers or list(range(1,len(records)+1))
    for row,record_number in zip(records,numbers):
        check(not final_seen,'Record after final marker')
        groups=row['group_counters']
        check(len(groups)==group_count,'Group count changed')
        ids=[g['group_id'] for g in groups]
        check(sorted(ids)==list(range(group_count)),'Group identities are not unique and contiguous')
        for value in [row,*groups]:
            check(value['offered']==value['reserved']+value['missed']+value['unreserved_current'],
                  'offered != reserved + missed + unreserved_current')
            check(value['reserved']>=value['issued']>=value['completed'],'reserved >= issued >= completed violated')
        check(all(sum(g[k] for g in groups)==row[k] for k in COUNTERS),'Group sums differ from aggregate')
        check(row['evidence_valid'],'Producer marked evidence invalid')
        check(row['errors']==0 and row['timeouts']==0,'Producer reported errors or timeouts')
        if row['schema']==FINAL_SCHEMA:
            final_seen=True
            check(prior is not None,'Final marker precedes progress')
            check(row['groups']==group_count,'Final group count mismatch')
            check(row['payload_bytes'] in (1024,16384) and row['payload_bytes']==payload,'Final payload mismatch')
            check(1<=row['streams_per_group']<=64 and 1<=row['outstanding_per_stream']<=64,'Final stream/depth bounds violated')
            check(row['max_outstanding_observed']<=row['groups']*row['streams_per_group']*row['outstanding_per_stream'],
                  'Outstanding work exceeds configured bound')
            check(row['collector_overflow_count']==0,'Final collector overflow')
            check(row['all_groups_joined'],'Groups not joined at final marker')
            check(row['measurement_duration_ns']==deadline and row['measurement_duration_ns']>0,'Final measurement boundary mismatch')
            check(row['measurement_duration_ns']+row['drain_duration_ns']==last_end,'Final duration differs from observed end')
            if prior:
                check(all(row[k]==prior[k] for k in COUNTERS),'Final counters differ from last progress')
                check(sorted(groups,key=lambda g:g['group_id'])==previous_groups,'Final group counters differ from last progress')
            for value in [row,*groups]:
                check(value['unreserved_current']==0 and value['reserved']==value['issued']==value['completed'],
                    'Final reservation/issuance/completion closure incomplete')
            continue
        start,end=row['interval_start_ns'],row['interval_end_ns']
        check(row['event']=='b5_grouped_progress','Unexpected progress event')
        check(row['window_index']==last_index+1,'Noncontiguous window index')
        check(start==last_end and end>start,'Noncontiguous or nonpositive window interval')
        check(row['elapsed_ns']==end,'Elapsed time differs from interval end')
        check(row['issue_deadline_ns']>0 and (deadline is None or deadline==row['issue_deadline_ns']),
            'Issue deadline changed or is zero')
        deadline=row['issue_deadline_ns']
        expected_phase='steady' if end<=deadline else 'drain' if start>=deadline else 'mixed'
        check(row['phase']==expected_phase,'Phase does not match issue boundary')
        ordered=sorted(groups,key=lambda g:g['group_id'])
        if prior:
            check(all(row[k]>=prior[k] for k in COUNTERS[:-1]),'Cumulative counters decreased')
            check(len(ordered)==len(previous_groups) and all(
                all(g[k]>=old[k] for k in COUNTERS[:-1]) for g,old in zip(ordered,previous_groups)),
                'Group cumulative counters decreased')
            check(row['max_reservation_lateness_ns']>=prior['max_reservation_lateness_ns'],'Maximum lateness decreased')
            if last_end>=deadline:
                check(row['offered']==prior['offered'] and row['reserved']==prior['reserved'],
                    'Offers or reservations advanced after deadline')
                check(all(g['offered']==old['offered'] and g['reserved']==old['reserved'] for g,old in zip(ordered,previous_groups)),
                    'Group offers or reservations advanced after deadline')
        stride,capacity=row['sample_stride'],row['sample_capacity']
        check(stride>0 and capacity>0,'Sampling stride/capacity must be positive')
        check(sampling is None or sampling==(stride,capacity),'Sampling configuration changed')
        sampling=(stride,capacity)
        samples=row['sample_count']; delta=row['completed']-(prior['completed'] if prior else 0)
        check(row['sample_overflow_count']==0,'Window sampler overflow')
        check(samples<=capacity,'Sample count exceeds capacity')
        if stride:
            check(samples==row['completed']//stride-(prior['completed']//stride if prior else 0),'Sample count inconsistent with stride')
        check(samples<=delta,'Sample count exceeds window completions')
        quantiles=[row[q] for q in QUANTILES]
        if samples==0: check(all(q is None for q in quantiles),'Empty sample window has quantiles')
        else:
            check(all(q is not None for q in quantiles) and quantiles==sorted(quantiles,key=lambda q:-1 if q is None else q),
                'Missing or unordered sampled quantiles')
            if samples==1: check(len(set(quantiles))==1,'Single-sample quantiles differ')
        if payload is not None and end>start:
            expected=delta*2*payload*1e9/(end-start)
            check(math.isclose(row['goodput_bytes_per_second'],expected,rel_tol=1e-12,abs_tol=1e-9),
                'Goodput differs from completed payload / interval')
        windows.append(dict(record_number=record_number,index=row['window_index'],phase=row['phase'],
            start_ns=str(start),end_ns=str(end),completed_delta=str(delta),
            goodput_mbps_bidirectional=row['goodput_bytes_per_second']/125000,
            sample_count=str(samples),sample_stride=str(stride),
            **{q.split('_')[0]+'_us':row[q]/1000 if row[q] is not None else None for q in QUANTILES}))
        prior=row; previous_groups=ordered; last_end=end; last_index=row['window_index']
    check(len(finals)<=1,'Multiple final markers')
    if final and truncated_tail: check(False,'Trailing incomplete record after final marker')
    valid=not findings
    impl={'direct-quic':'Direct QUIC','rust-rust':'NBSR (Rust–Rust)','go-rust':'NBSR (Go–Rust)'}.get(implementation,'Unknown path')
    run=base({'schema':ENVELOPE},metadata.get('label','Grouped progress snapshot'),impl)
    last=final or progresses[-1]
    run.update(evidence='progress_records',phase='progress',
        duration_s=final['measurement_duration_ns']/1e9 if final and valid else None,
        drain_s=final['drain_duration_ns']/1e9 if final and valid else None,
        shape={'groups':group_count,**({'payload_bytes':payload} if payload is not None else {}),
            **({k:final[k] for k in ('streams_per_group','outstanding_per_stream')} if final else {})},
        provenance={'implementation_source':'Declared snapshot metadata; not independently verified' if implementation else 'Producer implementation not recorded'})
    run['counts']['offered']=str(last['offered']); run['counts']['completed']=str(last['completed'])
    run['counts']['unstarted']=str(last['missed']) if final and valid else None
    run['counts']['timeout']=str(last['timeouts'])
    run['counts']['failed']='0' if valid and last['errors']==0 else None
    steady=[w for w in windows if w['phase']=='steady'] if valid else []
    run['latency']={**{q+'_us':statistics.median(v) if (v:=[w[q+'_us'] for w in steady if w[q+'_us'] is not None]) else None for q in ('p50','p95','p99')},
        'scope':'Median of imported steady-window sampled quantiles; not pooled percentiles. Partial snapshots are provisional. Pacing wait is outside the documented producer timer.'}
    run['stream']=dict(state='final' if final else 'partial',validity='valid' if valid else 'invalid',
        elapsed_ns=str(last_end),issue_deadline_ns=str(deadline),truncated_tail=truncated_tail,
        windows=windows if valid else [],source_counters={k:str(last[k]) for k in COUNTERS},
        source_errors=str(last['errors']),source_timeouts=str(last['timeouts']),
        records=len(records),final_record_number=numbers[records.index(final)] if final else None,
        payload_verified=payload is not None,declared_implementation=implementation)
    run['gates']=[gate('Grouped accounting','pass' if valid else 'fail',
        'Imported counters, windows, groups and sampling reconcile.' if valid else '; '.join(findings)),
        gate('Completeness','pass' if final and valid else 'unknown',
            'Final marker reconciles with the last imported window.' if final and valid else 'No validated final result. The producer may still be running, stopped or unavailable.'),
        gate('Payload rate','pass' if payload is not None and valid else 'unknown',
            'Bidirectional payload rate matches interval completions.' if payload is not None and valid else 'Payload shape unavailable or evidence invalid; do not treat the rate as independently reconciled.'),
        gate('Cleanup','unknown','Final source_cleanup is retained in the raw artifact; independent ownership cleanup is not established.'),
        gate('Source connection','unknown','Imported snapshot only. Receipt time is not measurement time; no live feed is connected.'),
        gate('Capacity','unknown','An imported progress stream does not establish sustainable capacity.')]
    if truncated_tail: run['gates'].append(gate('Framing','warn','An incomplete final line was retained but not parsed. Earlier complete records only.'))
    run['limitations']=['Independent snapshots are never automatically merged or treated as independent benchmark runs.',
        'Source execution-start, incomplete operation counts and cleanup remain unverified.',
        'No direct source connection or synchronized wall-clock timestamp is present.']
    return [run]
