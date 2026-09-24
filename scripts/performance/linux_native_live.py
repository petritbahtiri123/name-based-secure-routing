"""Bounded endpoint-local guards; not a remote clock or soak qualification."""

from copy import deepcopy

from scripts.performance.b5_grouped import ProgressValidator
from scripts.performance.linux_b5_ceiling import require
from scripts.performance.sustained_capacity import live_drift_failure, private_growth


class LocalLiveGuard:
    def __init__(self, *, role, payload_bytes, max_progress, max_resources):
        require(role in ('source', 'destination'), 'invalid local role')
        require(all(type(n) is int and 0 < n <= 100000 for n in (max_progress, max_resources)),
                'positive bounded input limits required')
        self.role = role
        self.validator = ProgressValidator(1, payload_bytes)
        self.max_progress, self.max_resources = max_progress, max_resources
        self.resources, self.steady, self.failures = [], [], []
        self.count, self.last_received, self.origin = 0, -1, None
        self.evaluated_resources = 0
        self.final = None

    def resource(self, value):
        require(self.final is None and len(self.resources) < self.max_resources,
                'resource after final or input bound exceeded')
        require(isinstance(value, dict) and value.get('role') == self.role,
                'resource must belong to this endpoint role')
        clock, memory = value.get('timestamp_ns'), value.get('private_resident_bytes')
        require(type(clock) is int and clock >= 0
                and (not self.resources or clock >= self.resources[-1]['timestamp_ns']),
                'invalid/reversed local resource clock')
        terminal = (value.get('state') == 'Z' and value.get('memory_state') == 'UNAVAILABLE_ZOMBIE'
                    and 'private_resident_bytes' in value and memory is None)
        require(terminal or (type(memory) is int and memory >= 0), 'invalid private resident memory')
        self.resources.append(dict(timestamp_ns=clock, private_resident_bytes=memory))

    def progress(self, value, *, received_ns):
        require(self.final is None and self.count < self.max_progress,
                'progress after final or input bound exceeded')
        require(type(received_ns) is int and received_ns >= 0 and received_ns >= self.last_received,
                'invalid/reversed local receipt clock')
        self.validator.accept(value)
        self.count += 1
        self.last_received = received_ns
        if self.origin is None:
            self.origin = received_ns - value['elapsed_ns']
        if value['phase'] != 'steady':
            return
        self.steady.append(deepcopy(value))
        reason = live_drift_failure(self.steady)
        if reason:
            self.failures.append(dict(window=value['window_index'], reason=reason))
        points = [((row['timestamp_ns'] - self.origin) / 1e9, float(row['private_resident_bytes']))
                  for row in self.resources if row['private_resident_bytes'] is not None
                  and self.origin <= row['timestamp_ns'] <= received_ns]
        self.evaluated_resources = len(points)
        if private_growth(points):
            self.failures.append(dict(window=value['window_index'], reason='private_growth'))

    def finish(self, value):
        require(self.final is None, 'duplicate final')
        self.validator.finish(value)
        self.final = deepcopy(value)

    def qualification(self):
        return dict(role=self.role, final_received=self.final is not None,
            steady_windows=len(self.steady),
            latency_comparison_available=len(self.steady) >= 3
                and all(row['p99_latency_ns'] is not None for row in self.steady),
            resource_series_available=self.evaluated_resources >= 4,
            resource_samples_evaluated=self.evaluated_resources,
            local_phase_origin_ns=self.origin,
            resource_phase_clock='first local progress receipt minus source elapsed duration; approximate relay-delay uncertainty',
            failures=deepcopy(self.failures), sustained_capacity='NOT_ESTABLISHED',
            observer_qualification='NOT_ESTABLISHED')
