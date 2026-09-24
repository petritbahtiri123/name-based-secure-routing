"""Bounded offline accounting for short native paced diagnostics, not B5 stability."""

import statistics

from scripts.performance.b5_grouped import ProgressValidator
from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_native_lifecycle_control import decode_object
from scripts.performance.sustained_capacity import live_drift_failure


def validate_rate(rate):
    require(type(rate) is list and len(rate) == 2
            and all(type(value) is int and 0 < value < 2**64 for value in rate),
            'positive exact rational diagnostic rate required')
    return rate


def read_paced(path, cell):
    validate_rate(cell['diagnostic_rate'])
    validator = ProgressValidator(1, cell['payload_bytes'])
    final, steady, failures = None, [], []
    with path.open('rb') as stream:
        for index in range(1025):
            wire = stream.readline(65537)
            if not wire:
                break
            require(index < 1024 and len(wire) <= 65536 and wire.endswith(b'\n'),
                    'paced stdout framing/bound failed')
            require(final is None, 'record after paced final')
            value = decode_object(wire)
            schema = value.get('schema')
            if schema == 'nbsr-b5-grouped-progress-v1':
                validator.accept(value)
                if value['phase'] == 'steady':
                    steady.append(value)
                    reason = live_drift_failure(steady)
                    if reason:
                        failures.append(dict(window=value['window_index'], reason=reason))
            elif schema == 'nbsr-b5-grouped-final-v1':
                validator.finish(value)
                final = value
            else:
                require(value.get('event') == 'diagnostic'
                        and (not isinstance(schema, str) or not schema.startswith('nbsr-b5')),
                        'unknown paced stdout record')
    require(final is not None and final['measurement_duration_ns'] == 20_000_000_000
            and final['streams_per_group'] == cell['streams']
            and final['outstanding_per_stream'] == cell['outstanding'], 'paced final shape/duration mismatch')
    require(final['offered'] > 0 and final['completed'] > 0, 'empty paced workload')
    quantiles = {q: statistics.median(row[q] for row in steady if row[q] is not None)
                 if any(row[q] is not None for row in steady) else None
                 for q in ('p50_latency_ns', 'p95_latency_ns', 'p99_latency_ns')}
    return dict(schema='nbsr-native-paced-diagnostic-v1', path=cell['path'],
        payload_bytes=cell['payload_bytes'], streams=cell['streams'],
        outstanding_per_stream=cell['outstanding'], diagnostic_rate=cell['diagnostic_rate'],
        completed_operations=final['completed'],
        measured_ns=final['measurement_duration_ns'] + final['drain_duration_ns'],
        achieved_offered_ratio=final['completed'] / final['offered'], final=final,
        drift_failures=failures, steady_windows=len(steady),
        latency_scope='median of steady-window quantiles, not pooled quantiles', **quantiles,
        strict_stable_capacity='NOT_ESTABLISHED', live_private_growth='NOT_MEASURED')
