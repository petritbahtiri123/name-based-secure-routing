"""Task 4g timeline-only observer gate. No ETW or optimization on rejection."""
import argparse
import hashlib
import os
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_b4b_v2 as v2
from scripts.run_b4b_mixed_connections import SOURCE_FILES, checksums


def observer_gate(off, on):
    metrics = ['established_goodput_bytes_per_second', 'admission_rate']
    metrics += [f'{kind}_p{p}_latency_ns' for kind in ('established', 'admission')
                for p in (50, 95, 99) if all(f'{kind}_p{p}_latency_ns' in r for r in off+on)]
    impact = {}
    for key in metrics:
        before = statistics.median(r[key] for r in off)
        after = statistics.median(r[key] for r in on)
        impact[key] = abs(after/before-1) if before else (0 if not after else None)
    success_shift = abs(statistics.median(r['successful_admissions']/r['requested_clients'] for r in on)
                        - statistics.median(r['successful_admissions']/r['requested_clients'] for r in off))
    valid = len(off) >= 3 and len(off) == len(on) and all(r['valid'] for r in off+on)
    cleanup = all(r['cleanup']['all_zero'] for r in on)
    for p in ('50','95','99'):
        if all('handshake_latency_ns' in r for r in off+on):
            before=statistics.median(r['handshake_latency_ns'][p] for r in off)
            after=statistics.median(r['handshake_latency_ns'][p] for r in on)
            impact['handshake_p'+p]=abs(after/before-1) if before else (0 if not after else None)
    return {'pass': valid and cleanup and success_shift <= .01
            and all(v is not None and v <= .05 for v in impact.values()),
            'absolute_median_impact': impact, 'success_shift_fraction': success_shift,
            'all_runs_valid': valid, 'on_cleanup_zero': cleanup}


def run(output):
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    binaries = v2.build(Path(os.environ.get('CARGO_TARGET_DIR', r'C:\NBSR-build\b4b-task4g')))
    environment = v2.host_environment()
    sources = list(SOURCE_FILES) + ['scripts/run_b4b_task4g.py',
        'scripts/performance/handshake_timeline.py',
        'crates/nbsr-transport/src/bin/benchmark_support/handshake_timeline.rs']
    environment.update(timestamp_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        build='release', duration_seconds=20, warmup_seconds=2, planned_clients=[128,256],
        command=[sys.executable,*sys.argv],
        binary_sha256={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in binaries.items()},
        source_sha256={p:hashlib.sha256((v2.ROOT/p).read_bytes()).hexdigest() for p in sources})
    v2.write_json(output/'environment.json', environment)
    gates=[]
    for clients in (128,256):
        selected={'off':[], 'on':[]}
        count=3
        repeat=1
        while repeat <= count:
            for mode in (('off','on') if repeat % 2 else ('on','off')):
                raw=output/'raw'/mode
                raw.mkdir(parents=True,exist_ok=True)
                print(f'clients={clients} repeat={repeat}/{count} timeline={mode}',flush=True)
                record=v2.run_measured_cell(clients,1,repeat,binaries,raw,duration=20,warmup=2,
                    planned_clients=[128,256],timeline=mode=='on',
                    counter_path=raw/f'clients-{clients}-r{repeat}-host.csv')
                v2.write_json(raw/f'clients-{clients}-r{repeat}.json',record)
                selected[mode].append(record)
                if not record['valid']:
                    v2.write_json(output/'analysis.json',dict(classification='PARTIAL / UNRESOLVED',
                        reason='invalid timeline/workload evidence',clients=clients,mode=mode,gates=gates))
                    checksums(output)
                    return
            if repeat==3:
                count=max(v2.required_repeats(selected[m]) for m in selected)
            repeat+=1
        gates.append(dict(clients=clients,**observer_gate(selected['off'],selected['on'])))
    v2.write_json(output/'analysis.json',dict(gates=gates,
        classification='OBSERVER GATE PASS' if all(g['pass'] for g in gates) else 'PARTIAL / UNRESOLVED',
        etw_collected=False, attribution='No causal attribution from timeline-only counts or timings'))
    checksums(output)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
