"""Bounded benchmark telemetry interleaved with finite management events."""

from copy import deepcopy

from scripts.performance.b5_grouped import ProgressValidator
from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_native_finite_control import FiniteLedger, SCHEMA
from scripts.performance.linux_native_lifecycle_control import decode_object


class LiveLedger(FiniteLedger):
    def __init__(self, *, payload_bytes):
        super().__init__()
        self.validator = ProgressValidator(1, payload_bytes)
        self.telemetry = []
        self.final_received = False

    def accept(self, role, wire):
        value = decode_object(wire)
        name = value.get('event')
        if name not in ('paced_progress', 'paced_final'):
            require(not (role == 'source' and name == 'complete') or self.final_received,
                    'source completion before telemetry final')
            return super().accept(role, wire)
        require(role == 'source' and self.positions['source'] == 2 and not self.final_received,
                'telemetry outside source measurement phase')
        require(len(self.telemetry) < 1024, 'telemetry frame bound exceeded')
        require(set(value) == {'schema', 'role', 'event', 'timestamp_ns', 'value'}
                and value['schema'] == SCHEMA and value['role'] == role,
                'invalid telemetry fields/schema/role')
        require(type(value['timestamp_ns']) is int and value['timestamp_ns'] >= self.last_time[role],
                'invalid telemetry clock')
        if name == 'paced_progress':
            self.validator.accept(value['value'])
        else:
            self.validator.finish(value['value'])
            self.final_received = True
        self.last_time[role] = value['timestamp_ns']
        self.telemetry.append(deepcopy(value))
        return value
