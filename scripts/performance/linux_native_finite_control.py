"""Bounded private control for existing finite native forwarding peers."""

import json

from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_native_lifecycle_control import decode_object
from scripts.performance.linux_native_lifecycle_endpoint import read_optional_json
from scripts.performance.linux_native_peer import validate_endpoint


SCHEMA = 'nbsr-native-finite-control-v1'
SEQUENCES = dict(source=('owned', 'readiness_transferred', 'complete'),
                 destination=('owned', 'ready', 'acked', 'complete'))


class FiniteLedger:
    def __init__(self):
        self.positions = dict.fromkeys(SEQUENCES, 0)
        self.last_time = dict.fromkeys(SEQUENCES, -1)
        self.received = {}

    def accept(self, role, wire):
        require(role in SEQUENCES, 'invalid role')
        value = decode_object(wire)
        index = self.positions[role]
        require(index < len(SEQUENCES[role]), 'event after completion')
        name = SEQUENCES[role][index]
        fields = {'schema', 'role', 'event', 'timestamp_ns'} | ({'value'} if name == 'ready' else set())
        require(set(value) == fields and value.get('schema') == SCHEMA
                and value.get('role') == role and value.get('event') == name, 'event fields/order mismatch')
        require(type(value['timestamp_ns']) is int and value['timestamp_ns'] >= 0
                and value['timestamp_ns'] >= self.last_time[role], 'invalid event clock')
        if name == 'ready':
            require(isinstance(value['value'], dict), 'readiness object required')
        self.positions[role] += 1
        self.last_time[role] = value['timestamp_ns']
        self.received[role, name] = value
        return value

    def eof(self, role):
        if self.positions[role] != len(SEQUENCES[role]):
            raise InterruptedError(role + ' control EOF before completion')


class FiniteControl:
    def __init__(self, args):
        self.args = args
        self.ready = self.transferred = self.acked = False

    @staticmethod
    def validate_ready(value, address):
        require(isinstance(value, dict), 'readiness object required')
        host, _ = validate_endpoint(value.get('endpoint'), allow_zero=False)
        require(host == address and value.get('alpn') == 'nbsr-quic-1', 'readiness address/ALPN mismatch')

    def poll(self):
        if self.args.role == 'destination' and not self.ready:
            value = read_optional_json(self.args.output / 'ready.json')
            if value is not None:
                self.validate_ready(value, validate_endpoint(self.args.bind, allow_zero=True)[0])
                self.ready = True
                return [dict(event='ready', value=value)]
        return []

    def request(self, value):
        require(isinstance(value, dict), 'control object required')
        op = value.get('op')
        fields = {'op', 'value'} if op == 'readiness' else {'op'}
        require(set(value) == fields and op in ('readiness', 'ack', 'cancel'), 'invalid control request')
        if op == 'cancel':
            raise InterruptedError('control cancellation requested')
        if op == 'readiness':
            require(self.args.role == 'source' and not self.transferred, 'source readiness permitted once')
            self.validate_ready(value['value'], self.args.destination_address)
            with self.args.ready_input.open('x') as stream:
                json.dump(value['value'], stream)
            self.transferred = True
            return [dict(event='readiness_transferred')]
        require(self.args.role == 'destination' and self.ready and not self.acked, 'ACK permitted once after ready')
        with (self.args.output / 'completion.ack').open('x') as stream:
            stream.write('validated source completed and relay exited successfully\n')
        self.acked = True
        return [dict(event='acked')]


def drive(start, wait, send, finish):
    start('source')
    wait('source', 'owned')
    start('destination')
    wait('destination', 'owned')
    ready = wait('destination', 'ready')
    send('source', dict(op='readiness', value=ready['value']))
    wait('source', 'readiness_transferred')
    wait('source', 'complete')
    finish('source')
    send('destination', dict(op='ack'))
    wait('destination', 'acked')
    wait('destination', 'complete')
    finish('destination')
