"""Task 4h external-only simultaneous versus pre-connect batch diagnosis."""
import argparse, hashlib, os, shutil, statistics, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import run_b4b_v2 as v2
from scripts.performance.external_packet_capture import ExternalCapture
from scripts.run_b4b_mixed_connections import SOURCE_FILES, checksums

MANDATORY=('established_goodput_bytes_per_second','admission_rate','admission_p95_latency_ns','admission_p99_latency_ns','established_p95_latency_ns','established_p99_latency_ns')
def observer_gate(off,on):
    if len(off)!=len(on) or len(off)<3 or not all(r.get('valid') and all(r.get(k) is not None for k in MANDATORY) and
        r.get('handshake_latency_ns',{}).get('95') is not None and r['handshake_latency_ns'].get('99') is not None for r in off+on):
        return {'pass':False,'reason':'missing/invalid matched capture evidence'}
    impact={}
    for key in (*MANDATORY,'handshake_p95','handshake_p99'):
        values=lambda rows:[r['handshake_latency_ns'][key[-2:]] for r in rows] if key.startswith('handshake_') else [r[key] for r in rows]
        before,after=statistics.median(values(off)),statistics.median(values(on))
        impact[key]=abs(after/before-1) if before else None
    shift=abs(statistics.median(r['successful_admissions']/r['requested_clients'] for r in off)-statistics.median(r['successful_admissions']/r['requested_clients'] for r in on))
    required=max(v2.required_repeats(off),v2.required_repeats(on))
    cleanup=all(r['cleanup']['all_zero'] for r in off+on)
    return {'pass':len(off)>=required and cleanup and shift<=.01 and all(v is not None and v<=.05 for v in impact.values()),
        'absolute_median_impact':impact,'success_shift_fraction':shift,'required_repeats':required,'cleanup_zero':cleanup}

def medians(records):
    result=dict(repeats=len(records),valid=sum(r['valid'] for r in records),admitted=statistics.median(r['successful_admissions'] for r in records),
        admissions_per_second=statistics.median(r['admission_rate'] for r in records),gbps=statistics.median(r['established_goodput_bytes_per_second']*8/1e9 for r in records),
        p99_ns=statistics.median(r['admission_p99_latency_ns'] for r in records),effective_cores=statistics.median(r['effective_cores'] for r in records),
        peak_pending=statistics.median(r['peak_pending_clients'] for r in records),cleanup_zero=all(r['cleanup']['all_zero'] for r in records))
    captures=[r['packet_capture'] for r in records if r.get('packet_capture',{}).get('enabled')]
    if captures:
        result['packet_capture']=dict(valid=sum(c['valid'] for c in captures),packets=statistics.median(c['packet_count'] for c in captures),
            flows=statistics.median(c['flow_count'] for c in captures),flows_without_reply=statistics.median(c['flows_without_reply'] for c in captures),
            repeated_initial_flows=statistics.median(c['repeated_initial_flows'] for c in captures),retry_packets=statistics.median(c['retry_packet_count'] for c in captures),
            first_reply_delay_p95_seconds=statistics.median(c['first_reply_delay_p95_seconds'] for c in captures if c['first_reply_delay_p95_seconds'] is not None))
    return result

def execute(output,duration=20,warmup=2,interval_ms=25):
    if output.exists(): raise FileExistsError(output)
    output.mkdir(parents=True); raw=output/'raw'; raw.mkdir()
    target=Path(os.environ.get('CARGO_TARGET_DIR',r'C:\NBSR-build\b4b-task4h'))
    binaries=v2.build(target); environment=v2.host_environment()
    sources=list(SOURCE_FILES)+['crates/nbsr-transport/src/bin/benchmark_support/batch_release.rs',
        'scripts/run_b4b_v2.py','scripts/run_p2a_established.py',
        'scripts/performance/external_packet_capture.py','scripts/run_b4b_task4h.py']
    snapshot=output/'capture-source'
    for source in sources:
        target_path=snapshot/source; target_path.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(v2.ROOT/source,target_path)
    environment.update(timestamp_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),build='release',duration_seconds=duration,
        warmup_seconds=warmup,total_clients=256,release_interval_ms=interval_ms,command=[sys.executable,*sys.argv],
        release_batch_sizes=[8,16,32],capture_interface=r'\Device\NPF_Loopback',capture_tool='Dumpcap/TShark',
        handshake_and_cleanup_deadlines='unchanged',task4g_timelines=False,
        binary_sha256={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in binaries.items()},
        source_sha256={p:hashlib.sha256((v2.ROOT/p).read_bytes()).hexdigest() for p in sources})
    v2.write_json(output/'environment.json',environment)
    dumpcap=Path(r'C:\Program Files\Wireshark\dumpcap.exe'); tshark=Path(r'C:\Program Files\Wireshark\tshark.exe')
    records={name:[] for name in ('simultaneous_off','simultaneous_capture','batch8','batch16','batch32')}
    # Alternate matched observer controls; no Task-4g shared-memory timeline.
    repeats=3; repeat=1
    while repeat<=repeats:
        order=('simultaneous_off','simultaneous_capture') if repeat%2 else ('simultaneous_capture','simultaneous_off')
        for name in order:
            print(f'capture-gate mode={name} repeat={repeat}/{repeats}',flush=True)
            directory=raw/name; directory.mkdir(exist_ok=True)
            capture=ExternalCapture(dumpcap,tshark) if name.endswith('capture') else None
            record=v2.run_measured_cell(256,1,repeat,binaries,directory,duration=duration,warmup=warmup,planned_clients=[256],
                timeline=False,packet_capture=capture,counter_path=directory/f'r{repeat}-host.csv')
            v2.write_json(directory/f'r{repeat}.json',record); records[name].append(record)
        if repeat==3: repeats=max(v2.required_repeats(records['simultaneous_off']),v2.required_repeats(records['simultaneous_capture']))
        repeat+=1
    gate=observer_gate(records['simultaneous_off'],records['simultaneous_capture'])
    # Batches remain useful as external scheduling diagnostics even if capture is rejected.
    for repeat in range(1,6):
        for batch in (8,16,32):
            name=f'batch{batch}'; directory=raw/name; directory.mkdir(exist_ok=True)
            print(f'batch={batch} capture=off repeat={repeat}/5',flush=True)
            record=v2.run_measured_cell(256,1,repeat,binaries,directory,duration=duration,warmup=warmup,planned_clients=[256],
                timeline=False,release_batch=batch,release_interval_ms=interval_ms,
                counter_path=directory/f'r{repeat}-host.csv')
            v2.write_json(directory/f'r{repeat}.json',record); records[name].append(record)
    if gate['pass']:
        for batch in (8,16,32):
            name=f'batch{batch}_capture'; records[name]=[]
            repeat=1; count=3
            while repeat<=count:
                print(f'batch={batch} capture=on repeat={repeat}/{count}',flush=True)
                directory=raw/name; directory.mkdir(exist_ok=True)
                capture=ExternalCapture(dumpcap,tshark)
                record=v2.run_measured_cell(256,1,repeat,binaries,directory,duration=duration,warmup=warmup,planned_clients=[256],
                    timeline=False,release_batch=batch,release_interval_ms=interval_ms,packet_capture=capture,
                    counter_path=directory/f'r{repeat}-host.csv')
                v2.write_json(directory/f'r{repeat}.json',record); records[name].append(record)
                if repeat==3: count=v2.required_repeats(records[name])
                repeat+=1
    summaries={k:medians(v) for k,v in records.items()}
    base=summaries['simultaneous_off']['admitted']/256
    best=max((summaries[f'batch{batch}']['admitted']/256,batch) for batch in (8,16,32))
    burst_supported=best[0]>=.99 and best[0]-base>=.05
    analysis={'capture_observer_gate':gate,'cells':summaries,
        'capture_usable_for_causal_attribution':gate['pass'],'packet_attribution':'PENDING' if gate['pass'] else 'REJECTED_BY_OBSERVER_GATE',
        'burst_scheduling_supported':burst_supported,'best_diagnostic_batch':best[1],
        'burst_rule':'supported only when batched median is >=99% and improves >=5 percentage points over simultaneous',
        'claim_boundary':'Batched results are diagnostic only, never capacity claims.'}
    v2.write_json(output/'analysis.json',analysis); checksums(output)
    return analysis

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True); parser.add_argument('--duration-seconds',type=float,default=20); parser.add_argument('--warmup-seconds',type=float,default=2); parser.add_argument('--release-interval-ms',type=int,default=25)
    args=parser.parse_args(); execute(args.output,args.duration_seconds,args.warmup_seconds,args.release_interval_ms)
