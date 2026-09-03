"""Reproduce descriptive Task-4g summaries; never infer causality from timings."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.run_b4b_task4g import observer_gate
from scripts.run_b4b_mixed_connections import checksums, percentile
from scripts.run_b4b_v2 import coefficient_of_variation, write_json


def analyze(root):
    cells=[]
    inputs={}
    for clients in (128,256):
        modes={}
        for mode in ('off','on'):
            paths=sorted((root/'raw'/mode).glob(f'clients-{clients}-r*.json'))
            records=[json.loads(p.read_text()) for p in paths]
            for p in paths:
                inputs[p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
            modes[mode]=records
        if not all(modes.values()):
            continue
        if any(not r.get('valid') for records in modes.values() for r in records):
            report=dict(classification='PARTIAL / UNRESOLVED',observer_gate_pass=False,
                reason='invalid captured run',input_sha256=inputs,etw='NOT RUN')
            write_json(root/'timeline-analysis.json',report)
            checksums(root)
            return report
        gate=observer_gate(modes['off'],modes['on'])
        summaries={}
        for mode,records in modes.items():
            summaries[mode]=dict(repeats=len(records),
                valid=sum(bool(r['valid']) for r in records),
                median_admitted=statistics.median(r['successful_admissions'] for r in records),
                median_admissions_per_second=statistics.median(r['admission_rate'] for r in records),
                median_gbps=statistics.median(r['established_goodput_bytes_per_second']*8/1e9 for r in records),
                goodput_cv=coefficient_of_variation([r['established_goodput_bytes_per_second'] for r in records]),
                admission_rate_cv=coefficient_of_variation([r['admission_rate'] for r in records]),
                cleanup_zero=all(r['cleanup']['all_zero'] for r in records),
                median_effective_cores=statistics.median(r['effective_cores'] for r in records))
        stages={}
        for role in ('source','destination'):
            values={}
            outcomes={}
            for run in modes['on']:
                timeline=run['timeline_capture'].get(role)
                if not timeline:
                    continue
                frequency=timeline['qpc_frequency']
                for row in timeline['records']:
                    event=row['events']
                    outcome=next((name for name in ('failed','timed_out','cancelled') if event[name]),'admitted')
                    outcomes[outcome]=outcomes.get(outcome,0)+1
                    for start,end in [('requested','task_started'),('task_started','connect_first_poll'),
                        ('connect_first_poll','connected'),('connected','control_hello_complete'),
                        ('control_hello_complete','admission_started'),('admission_started','route_accepted'),
                        ('route_accepted','admitted'),('admitted','cleaned'),('connect_first_poll','timed_out')]:
                        if event[start] and event[end]:
                            key=f'{outcome}:{start}->{end}'
                            values.setdefault(key,[]).append((event[end]-event[start])*1e9/frequency)
            stages[role]=dict(outcomes=outcomes,pooled_observed_intervals_ns={
                key:dict(count=len(v),p50=percentile(v,.5),p95=percentile(v,.95),p99=percentile(v,.99))
                for key,v in values.items()},cross_process_matching='NONE')
        cells.append(dict(clients=clients,gate=gate,modes=summaries,timeline=stages))
    accepted=len(cells)==2 and all(c['gate']['pass'] for c in cells)
    report=dict(schema='nbsr-task4g-descriptive-analysis-v1',cells=cells,input_sha256=inputs,
        observer_gate_pass=accepted,classification='GATE PASS / ATTRIBUTION UNRESOLVED' if accepted else 'PARTIAL / UNRESOLVED',
        etw='NOT RUN',causal_attribution='NOT ESTABLISHED',
        note='Intervals are pooled descriptive ON observations, not independent repeat medians. Rejected observer data cannot attribute the uninstrumented collapse.')
    write_json(root/'timeline-analysis.json',report)
    lines=['# Task 4g observer results','',report['classification'],'',
        '| Clients | OFF admitted | ON admitted | OFF Gbit/s | ON Gbit/s | OFF admissions/s | ON admissions/s | Gate |',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    for c in cells:
        off,on=c['modes']['off'],c['modes']['on']
        lines.append(f"| {c['clients']} | {off['median_admitted']} | {on['median_admitted']} | {off['median_gbps']:.6f} | {on['median_gbps']:.6f} | {off['median_admissions_per_second']:.3f} | {on['median_admissions_per_second']:.3f} | {'PASS' if c['gate']['pass'] else 'REJECT'} |")
    lines += ['',report['note'],'','ETW not collected. No handshake mechanism, scheduler cause, or production limit is claimed.',
        '', 'Reproduce: `python scripts/analyze_b4b_task4g.py --root <evidence-root>`', '']
    (root/'SUMMARY.md').write_text('\n'.join(lines),encoding='utf-8')
    checksums(root)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    analyze(parser.parse_args().root)
