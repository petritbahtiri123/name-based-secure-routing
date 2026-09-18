from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import run_b4b_v2 as v2


RATES = (25, 50, 75, 100, 125, 150, 200, 250, 300, 400)
CLIENTS = 512


def required_repeats(records):
    return v2.required_repeats(records)


def ownership_high_water(rows):
    keys = {
        key
        for row in rows
        for key in row
        if key.endswith("_high_water_live") or key.endswith("_high_water_entries")
    }
    return {key: max(int(row.get(key, 0)) for row in rows) for key in sorted(keys)}


def classify_cell(candidate, baseline):
    if (candidate['errors'] or candidate['timeouts']
            or candidate['achieved_offered_ratio'] < .90
            or candidate['admission_success_ratio'] < .90
            or candidate['established_goodput_bytes_per_second'] < .75 * baseline['established_goodput_bytes_per_second']
            or candidate['established_p99_latency_ns'] > 2 * baseline['established_p99_latency_ns']
            or not candidate['cleanup_pass']):
        return 'SATURATED'
    if (candidate['achieved_offered_ratio'] < .95
            or candidate['admission_success_ratio'] < .95
            or candidate['established_goodput_bytes_per_second'] < .90 * baseline['established_goodput_bytes_per_second']
            or candidate['established_p99_latency_ns'] > 1.25 * baseline['established_p99_latency_ns']
            or candidate['repeat_cv'] > .05):
        return 'DEGRADED'
    return 'STABLE'


def should_stop(cells):
    return bool(cells and cells[-1]['status'] == 'SATURATED'
        and any(cell['status'] == 'STABLE' for cell in cells[:-1]))


def summarize(rate, records, baseline=None):
    med=lambda key: statistics.median(float(r[key]) for r in records)
    requested=int(statistics.median(r['requested_clients'] for r in records))
    admitted=int(statistics.median(r['successful_admissions'] for r in records))
    actual=med('admission_rate')
    result=dict(offered_rate=rate, repeats=len(records), valid=sum(r['valid'] for r in records),
        requested=requested, started=int(statistics.median(r['started_clients'] for r in records)),
        connected=int(statistics.median(r['connected_clients'] for r in records)), admitted=admitted,
        failed=sum(int(r['failed_admissions']) for r in records),
        errors=sum(int(r['errors']) for r in records), timeouts=sum(int(r['timeouts']) for r in records),
        actual_admissions_per_second=actual, achieved_offered_ratio=actual/rate,
        admission_success_ratio=min(int(r['successful_admissions'])/int(r['requested_clients']) for r in records), handshake_latency_ns={str(p):statistics.median(r['handshake_latency_ns'][str(p)] for r in records) for p in (50,95,99)},
        admission_p50_latency_ns=med('admission_p50_latency_ns'), admission_p95_latency_ns=med('admission_p95_latency_ns'), admission_p99_latency_ns=med('admission_p99_latency_ns'),
        established_goodput_bytes_per_second=med('established_goodput_bytes_per_second'), established_p99_latency_ns=med('established_p99_latency_ns'),
        effective_cores=med('effective_cores'), peak_pending_clients=med('peak_pending_clients'),
        cleanup_pass=all(r['cleanup']['all_zero'] and r['cleanup']['processes_exited'] for r in records),
        repeat_cv=max(v2.coefficient_of_variation([float(r['admission_rate']) for r in records]),
            v2.coefficient_of_variation([float(r['established_goodput_bytes_per_second']) for r in records])),
        resources={key:statistics.median(float(r['resources'][key]) for r in records) for key in records[0]['resources'] if isinstance(records[0]['resources'][key],(int,float))})
    # Being the reference cell does not waive absolute rate/error/CV gates.
    result['status']=classify_cell(result, result if baseline is None else baseline)
    result['is_reference_cell']=baseline is None
    return result


def checksums(root):
    lines=[]
    for path in sorted(p for p in root.rglob('*') if p.is_file() and p.name!='checksums.sha256'):
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}")
    (root/'checksums.sha256').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')


def execute(output: Path, duration=30, warmup=2, *, offered_rates=None, source_shards=1,
            backend=None, prepared_binaries=None, prepared_environment=None):
    rates = tuple(RATES if offered_rates is None else offered_rates)
    if not rates or any(type(rate) is not int or rate <= 0 for rate in rates) or list(rates) != sorted(set(rates)):
        raise ValueError('offered rates must be positive unique increasing integers')
    if type(source_shards) is not int or source_shards not in (1, 2):
        raise ValueError('source shards must be one or two')
    if output.exists(): raise FileExistsError(output)
    output.mkdir(parents=True); raw=output/'raw'; raw.mkdir()
    target=Path(os.environ.get('CARGO_TARGET_DIR',r'C:\NBSR-build\b4b-task4i'))
    binaries=v2.build(target) if prepared_binaries is None else prepared_binaries
    environment=v2.host_environment() if prepared_environment is None else dict(prepared_environment)
    sources=['crates/nbsr-transport/src/bin/benchmark_support/batch_release.rs','crates/nbsr-transport/src/bin/perf_rust_source.rs',
        'crates/nbsr-transport/src/bin/wp8_interop_server.rs','scripts/run_b4b_mixed_connections.py',
        'scripts/run_b4b_v2.py','scripts/run_b4b_task4i.py','scripts/analyze_b4b_task4i.py',
        'crates/nbsr-transport/src/bin/benchmark_support/lifecycle_shards.rs','scripts/performance/resources.py']
    if backend is not None:
        sources += ['scripts/run_b4b_linux.py', 'scripts/performance/b4_linux.py',
                    'scripts/performance/linux_resources.py', 'scripts/performance/linux_loopback.py',
                    'scripts/performance/b3_linux.py', 'scripts/run_b3_v2.py',
                    'scripts/performance/process_cancellation.py']
    for source in sources:
        destination=output/'capture-source'/source; destination.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(v2.ROOT/source,destination)
    environment.update(timestamp_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),build='release',duration_seconds=duration,
        warmup_seconds=warmup,total_clients=CLIENTS,offered_rates=list(rates),source_shards=source_shards,command=[sys.executable,*sys.argv],
        claim_boundary=('rate-controlled admission on Linux single-host loopback; no distributed-host claim'
                        if backend is not None else 'rate-controlled admission on Windows loopback; simultaneous burst remains separate'),
        binary_sha256={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in binaries.items()},
        source_sha256={p:hashlib.sha256((v2.ROOT/p).read_bytes()).hexdigest() for p in sources})
    v2.write_json(output/'environment.json',environment)
    cells=[]; invalid=[]
    for rate in rates:
        directory=raw/f'rate-{rate}'; directory.mkdir()
        records=[]; target_repeats=3; repeat=1
        while repeat<=target_repeats:
            print(f'rate={rate}/s repeat={repeat}/{target_repeats}',flush=True)
            record=v2.run_measured_cell(CLIENTS,1,repeat,binaries,directory,duration=duration,warmup=warmup,planned_clients=[CLIENTS],
                release_rate=rate,source_shards=source_shards,counter_path=directory/f'r{repeat}-host.csv',
                **({'backend': backend} if backend is not None else {}))
            v2.write_json(directory/f'r{repeat}.json',record)
            (records if record['valid'] else invalid).append(record)
            if repeat==3 and len(records)==3: target_repeats=required_repeats(records)
            repeat+=1
        # Invalid attempts remain raw evidence and cannot qualify a short cell.
        if len(records) < target_repeats: break
        cell=summarize(rate,records,None if not cells else cells[0]); cells.append(cell)
        if should_stop(cells): break
    analysis=dict(schema='nbsr-b4b-task4i-analysis-v1',classification='PASS' if any(c['status']=='STABLE' for c in cells) and any(c['status'] in ('DEGRADED','SATURATED') for c in cells) and not invalid else 'PARTIAL',
        cells=cells,invalid_runs=len(invalid),simultaneous_burst_result='separate Task 4h diagnostic; not mixed into capacity',
        thresholds=dict(stable_achieved_offered=.95,stable_p99_ratio=1.25,stable_goodput_ratio=.90,stable_cv=.05,saturated_achieved_offered=.90,saturated_p99_ratio=2.0,saturated_goodput_ratio=.75))
    v2.write_json(output/'analysis.json',analysis); checksums(output); return analysis


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True); parser.add_argument('--duration-seconds',type=float,default=30); parser.add_argument('--warmup-seconds',type=float,default=2)
    parser.add_argument('--offered-rates', type=int, nargs='+', default=None)
    parser.add_argument('--source-shards', type=int, choices=(1, 2), default=1)
    args=parser.parse_args(); execute(args.output,args.duration_seconds,args.warmup_seconds,
        offered_rates=args.offered_rates,source_shards=args.source_shards)
