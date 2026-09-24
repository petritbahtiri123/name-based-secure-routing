"""Bounded sequential lifecycle transcript and driver; endpoint integration pending."""

from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_native_lifecycle_control import CYCLE_COUNTS, decode_object


def sequence(role, cycles):
    require(role in ('source', 'destination') and type(cycles) is int
            and cycles in CYCLE_COUNTS, 'invalid role/cycle count')
    initial = ('prepared', 'readiness_transferred') if role == 'source' else ('ready',)
    result = [(name, None) for name in initial]
    for cycle in range(cycles):
        result.extend((name, cycle) for name in ('started', 'active', 'released'))
        if role == 'source':
            result.append(('acked', cycle))
    if role == 'destination':
        result.append(('report_ready', cycles - 1))
    return result + [('final_released', cycles - 1), ('complete', None)]


class CycleLedger:
    def __init__(self, cycles):
        self.sequences = {role: sequence(role, cycles) for role in ('source', 'destination')}
        self.positions = dict.fromkeys(self.sequences, 0)
        self.last_time = dict.fromkeys(self.sequences, -1)
        self.received = {}

    def accept(self, role, wire):
        require(role in self.sequences, 'invalid role')
        value = decode_object(wire)
        position = self.positions[role]
        require(position < len(self.sequences[role]), 'event after completion')
        name, cycle = self.sequences[role][position]
        require(value.get('schema') == 'nbsr-native-cycle-control-v1'
                and value.get('role') == role and value.get('event') == name, 'cycle event order/schema mismatch')
        fields = {'schema', 'role', 'event', 'timestamp_ns'}
        if cycle is not None:
            fields.add('cycle')
            require(type(value.get('cycle')) is int and value['cycle'] == cycle, 'cycle identity mismatch')
        if name == 'ready':
            fields.add('value')
            require(isinstance(value.get('value'), dict), 'readiness object required')
        require(set(value) == fields and type(value.get('timestamp_ns')) is int
                and value['timestamp_ns'] >= 0 and value['timestamp_ns'] >= self.last_time[role],
                'cycle event fields/clock mismatch')
        self.positions[role] += 1
        self.last_time[role] = value['timestamp_ns']
        self.received[role, name if cycle is None else (name, cycle)] = value
        return value

    def eof(self, role):
        require(role in self.sequences, 'invalid role')
        if self.positions[role] != len(self.sequences[role]):
            raise InterruptedError(role + ' control EOF before cycle completion')


def drive_cycles(cycles, start, wait, send, finish, *, sleep):
    sequence('source', cycles)  # Validate before starting any process.
    start('source')
    wait('source', 'prepared')
    start('destination')
    ready = wait('destination', 'ready')
    send('source', dict(op='readiness', value=ready['value']))
    wait('source', 'readiness_transferred')
    for cycle in range(cycles):
        for role in ('destination', 'source'):
            send(role, dict(op='start', cycle=cycle))
            wait(role, ('started', cycle))
        for role in ('source', 'destination'):
            wait(role, ('active', cycle))
        sleep(2)
        for role in ('destination', 'source'):
            send(role, dict(op='release', cycle=cycle))
            wait(role, ('released', cycle))
        wait('source', ('acked', cycle))
        sleep(2)
    wait('destination', ('report_ready', cycles - 1))
    sleep(2)  # Destination report-ready can arrive after source ACK/cooldown.
    for role in ('destination', 'source'):
        send(role, dict(op='final_release', cycle=cycles - 1))
        wait(role, ('final_released', cycles - 1))
    for role in ('source', 'destination'):
        wait(role, 'complete')
    finish('source')
    finish('destination')
