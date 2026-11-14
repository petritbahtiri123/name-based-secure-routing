"""Pure adapters. Report source claims; never execute the benchmark harness."""
import json
import math

ADAPTER_VERSION = '2.1.0'
MAX_BYTES = 4 * 1024 * 1024


def decode(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError('Artifact exceeds 4 MiB limit')
    def pairs(items):
        obj = {}
        for k, v in items:
            if k in obj:
                raise ValueError('Duplicate JSON key: ' + k)
            obj[k] = v
        return obj
    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Non-finite number')
        if isinstance(value, dict):
            for v in value.values(): finite(v)
        if isinstance(value, list):
            for v in value: finite(v)
    try:
        obj = json.loads(raw, object_pairs_hook=pairs,
            parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Non-finite number')))
        if not isinstance(obj, dict): raise ValueError('Expected one JSON object')
        finite(obj)
        return obj
    except (RecursionError, UnicodeError, json.JSONDecodeError) as e:
        raise ValueError('Invalid JSON document') from e


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def count(value):
    return str(value) if type(value) is int and 0 <= value < 2**64 else None


def gate(name, status, detail):
    return dict(name=name, status=status, detail=detail)


def base(obj, label, implementation):
    for key in ('date','topology','latency_method'):
        if key in obj and not isinstance(obj[key],str):
            raise ValueError(f'{key} must be text')
    return dict(label=label, implementation=implementation, date=obj.get('date'),
        schema=obj['schema'], evidence='summary_only', capacity='NOT_ESTABLISHED',
        counts={k:None for k in ('offered','started','completed','failed','timeout','unstarted','incomplete')},
        latency=dict(p50_us=None,p95_us=None,p99_us=None,scope='Producer aggregate; sampling unspecified'),
        duration_s=None, drain_s=None, goodput_mbps=None, offered_rate=None,
        shape={}, resources={}, provenance={}, gates=[],
        topology=obj.get('topology','Not recorded'),
        limitations=['No active benchmark connection. Historical artifact only.',
            'Raw operation logs and paired ABBA evidence are not available in this import.'])


def check_counts(run):
    c = run['counts']; known = {k:int(v) for k,v in c.items() if v is not None}
    if 'offered' in known and 'completed' in known and known['completed'] > known['offered']:
        run['gates'].append(gate('Counter bounds','fail','Completed exceeds offered.'))
    elif all(k in known for k in ('offered','completed','unstarted','failed','timeout')):
        total = sum(known[k] for k in ('completed','unstarted','failed','timeout'))
        run['gates'].append(gate('Reported totals','pass' if total == known['offered'] else 'fail',
            'Checks reported offered = completed + missed + errors + timeouts; does not establish start-boundary accounting.'))
    else:
        run['gates'].append(gate('Reported totals','unknown','Insufficient counters to reconcile this population.'))
    run['gates'].append(gate('Start / terminal invariant','unknown','Started and incomplete counts are not established by this artifact.'))


def normalize(obj):
    schema = obj.get('schema')
    if schema == 'nbsr-sphere-controlled-load-summary-v1':
        result = []
        shape = obj.get('shape', {})
        if not isinstance(shape, dict): raise ValueError('shape must be an object')
        for phase in ('smoke','measurement'):
            row = obj.get(phase)
            if row is None: continue
            if not isinstance(row, dict): raise ValueError('Measurement must be an object')
            if 'interface_and_resource_guards' in row and not isinstance(row['interface_and_resource_guards'],dict):
                raise ValueError('interface_and_resource_guards must be an object')
            rate = number(shape.get('aggregate_offered_operations_per_second'))
            run = base(obj, f'{rate:g} ops/s · {phase}' if rate is not None else phase, 'NBSR')
            run.update(shape=shape, phase=phase, offered_rate=rate,
                duration_s=number(row.get('measurement_seconds')),drain_s=number(row.get('drain_seconds')),
                goodput_mbps=number(row.get('useful_payload_mbps_each_direction')),
                resources=row.get('interface_and_resource_guards',{}),
                provenance={k:obj[k] for k in ('measured_sender_source_commit','measured_source_base','measured_sender_patch_sha256','runtime_commit','measured_binary_sha256','server_provenance','provenance_note') if k in obj})
            if 'raw_sha256' in row: run['provenance']['referenced_raw_sha256_unverified'] = row['raw_sha256']
            for target, source in dict(offered='offered_operations',completed='completed_operations',unstarted='missed_offer_slots',timeout='timeouts').items():
                run['counts'][target] = count(row.get(source))
            # Nonzero errors may include timeouts: no unsupported disjointness assumption.
            run['counts']['failed'] = '0' if type(row.get('errors')) is int and row['errors'] == 0 else None
            quantiles = row.get('median_window_quantiles_us',{})
            if 'median_window_quantiles_us' not in row and 'latency_median_of_window_quantiles_us' in row:
                legacy = row['latency_median_of_window_quantiles_us']
                if not isinstance(legacy,dict): raise ValueError('Legacy quantiles must be an object')
                # Verified 6000/s summary + accompanying methodology: container is us,
                # despite historically retained *_ns inner key names.
                quantiles = {q:legacy.get(q+'_latency_ns') for q in ('p50','p95','p99')}
            if not isinstance(quantiles, dict): raise ValueError('Quantiles must be an object')
            run['latency'] = {**{q+'_us':number(quantiles.get(q)) for q in ('p50','p95','p99')},
                'scope':'Median of sampled steady-window quantiles; not pooled percentiles. ' + obj.get('latency_method','Sampling stride and timer boundary not recorded in this artifact.')}
            run['gates'] = [gate('Evidence level','unknown','Sanitized summary claims only; referenced raw hashes have not been verified.'),
                gate('Ownership cleanup','pass' if row.get('owned_process_tls_and_mount_cleanup_confirmed') is True else 'unknown','Reported by summary; not independently checked by the Lab.'),
                gate('Capacity','unknown','Controlled-load completion does not establish sustainable or maximum capacity.')]
            flags = row.get('drift_flags')
            if flags is not None and not isinstance(flags,list): raise ValueError('drift_flags must be a list')
            run['gates'].append(gate('Latency drift','warn' if flags else 'unknown',
                f'{len(flags)} reported drift flag(s); overlapping flags are not independent failures.' if flags else
                'No reported flags here; this does not establish general latency stability.'))
            check_counts(run)
            result.append(run)
        if not result: raise ValueError('Summary has no smoke or measurement object')
        return result
    if schema == 'nbsr-p2a-repeat-v2':
        implementation = {'direct':'Direct QUIC','nbsr':'NBSR'}.get(obj.get('path'),'Unknown path')
        run = base(obj, f'{implementation} · established-stream repeat', implementation)
        duration = number(obj.get('measured_ns'))
        run.update(phase='repeat',duration_s=duration/1e9 if duration is not None else None,
            shape={k:obj[k] for k in ('streams','payload_bytes','outstanding_per_stream','model') if k in obj})
        run['counts']['completed'] = count(obj.get('completed_operations'))
        run['latency'] = {**{q+'_us': number(obj.get(q+'_latency_ns'))/1000 if number(obj.get(q+'_latency_ns')) is not None else None for q in ('p50','p95','p99')},
            'scope':f"Producer repeat quantiles. Sample stride: {obj.get('latency_sample_stride','not recorded')}; count: {obj.get('latency_sample_count','not recorded')}. No pooled-window inference."}
        run['gates'] = [gate('Provenance','unknown','Standalone repeat lacks environment and role-specific binary provenance.'),
            gate('Comparison eligibility','unknown','No matched ABBA block metadata.')]
        check_counts(run)
        return [run]
    return []
