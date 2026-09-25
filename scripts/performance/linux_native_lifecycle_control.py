"""Private benchmark control stream and per-host lifecycle barriers."""

import json
import os
import time

from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_loopback import write_json
from scripts.performance.linux_native_cycle_limits import CYCLE_COUNTS

BUNDLE_COUNTS = (16, 32, 64, 128, 256, 512, 1024)
LIVE_BUNDLE_COUNTS = (*BUNDLE_COUNTS, 2048)


class LifecycleBarrier:
    def __init__(self, *, role, count, root, output, capture, clock=time.monotonic_ns):
        require(role in ('source', 'destination') and type(count) is int
                and count in LIVE_BUNDLE_COUNTS, 'invalid role/count')
        require(root.is_dir() and not root.is_symlink() and output.is_dir(), 'invalid barrier directories')
        self.role, self.count, self.root, self.output = role, count, root, output
        self.capture, self.clock = capture, clock
        prefix = 'connection' if role == 'source' else 'destination'
        self.expected_active = {f'{prefix}-{i}.active' for i in range(count)}
        self.active_ns = self.report_ns = None
        self.released = self.acked = self.report_released = False

    def _inventory(self):
        names = set()
        with os.scandir(self.root) as entries:
            for entry in entries:
                if entry.name.endswith(('.active', '.ack', '.failed')):
                    require(entry.is_file(follow_symlinks=False), 'invalid marker entry')
                    names.add(entry.name)
        return names

    @staticmethod
    def _names(suffix, inventory):
        return {name for name in inventory if name.endswith('.' + suffix)}

    def _no_failure(self, inventory):
        require(not self._names('failed', inventory), 'failed marker prevents progress')

    def poll(self):
        inventory = self._inventory()
        self._no_failure(inventory)
        events = []
        active = self._names('active', inventory)
        require(active <= self.expected_active, 'unexpected active marker')
        if active == self.expected_active and self.active_ns is None:
            binding = self.capture()
            require(binding.get('status') == 'MEASURED_LIVE_SOCKET_SNAPSHOT'
                    and len(binding.get('sockets', [])) == (self.count if self.role == 'source' else 1),
                    'complete live socket observation required')
            write_json(self.output / 'socket-binding.json', binding)
            self.active_ns = self.clock()
            events.append(dict(event='active', count=self.count))
        if self.role == 'source':
            acks = self._names('ack', inventory)
            expected = {f'connection-{i}.ack' for i in range(self.count)}
            require(acks <= expected, 'unexpected ACK marker')
            require(not acks or self.released, 'ACK before release')
            if acks == expected and not self.acked:
                self.acked = True
                events.append(dict(event='acked', count=self.count))
        else:
            ready = self.root / 'destination.report-ready'
            require(not ready.is_symlink(), 'invalid report marker')
            if ready.exists():
                require(ready.is_file() and self.released, 'report ready before release')
                if self.report_ns is None:
                    self.report_ns = self.clock()
                    events.append(dict(event='report_ready'))
        return events

    def _write_release(self, name):
        with (self.root / name).open('x', encoding='utf-8', newline='\n') as stream:
            stream.write('release\n')

    def request(self, operation):
        inventory = self._inventory()
        self._no_failure(inventory)
        if operation == 'release':
            require(self.active_ns is not None and self._names('active', inventory) == self.expected_active,
                    'all active required before release')
            require(self.clock() - self.active_ns >= 2_000_000_000, 'two-second hold required')
            if self.released:
                return []
            for i in range(self.count):
                self._write_release(f'connection-{i}.release')
            self.released = True
            return [dict(event='released', count=self.count)]
        require(operation == 'report_release', 'unknown barrier operation')
        require(self.role == 'destination', 'destination only report release')
        require(self.report_ns is not None, 'report ready required')
        require(self.clock() - self.report_ns >= 2_000_000_000, 'two-second cooldown required')
        if self.report_released:
            return []
        self._write_release('destination.report-release')
        self.report_released = True
        return [dict(event='report_released')]


def decode_object(wire):
    require(isinstance(wire, bytes) and 0 < len(wire) <= 65536, 'control message size')

    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'duplicate control field')
            value[key] = item
        return value

    def nonfinite(_):
        raise ValueError('nonfinite control value')

    value = json.loads(wire, object_pairs_hook=unique, parse_constant=nonfinite)
    require(isinstance(value, dict), 'control object required')
    return value


def decode_control(wire):
    value = decode_object(wire)
    require(value.get('op') in ('readiness', 'release', 'report_release', 'cancel'),
            'unknown control operation')
    expected = {'op', 'value'} if value['op'] == 'readiness' else {'op'}
    require(set(value) == expected and (value['op'] != 'readiness' or isinstance(value['value'], dict)),
            'invalid control fields')
    return value


class CycleBarrier:
    """Sequential diagnostic barriers; ACK is not a resource-reclamation proof."""

    def __init__(self, *, role, cycles, root, output, capture, clock=time.monotonic_ns):
        require(role in ('source', 'destination') and type(cycles) is int
                and cycles in CYCLE_COUNTS, 'invalid role/cycle count')
        require(root.is_dir() and not root.is_symlink() and output.is_dir(), 'invalid barrier directories')
        self.role, self.cycles, self.root, self.output = role, cycles, root, output
        self.capture, self.clock = capture, clock
        self.cycle = -1
        self.active_ns = self.released_ns = self.acked_ns = self.report_ns = None
        self.final_released = False
        self.retained = set()

    def _inventory(self):
        names = set()
        with os.scandir(self.root) as entries:
            for entry in entries:
                if entry.name.endswith(('.active', '.ack', '.failed')):
                    require(entry.is_file(follow_symlinks=False), 'invalid marker entry')
                    names.add(entry.name)
        require(not any(n.endswith('.failed') for n in names), 'failed marker prevents progress')
        require(self.retained <= names, 'previous markers must be retained')
        prefix = 'connection' if self.role == 'source' else 'destination'
        allowed = {f'{prefix}-{i}.active' for i in range(self.cycle + 1)}
        if self.role == 'source':
            allowed |= {f'connection-{i}.ack' for i in range(self.cycle + 1)}
        require(names <= allowed, 'unexpected cycle marker')
        if self.role == 'source' and f'connection-{self.cycle}.ack' in names:
            require(self.released_ns is not None, 'ACK before release')
        ready = self.root / 'destination.report-ready'
        require(not ready.is_symlink(), 'invalid report marker')
        if self.role == 'destination' and ready.exists():
            require(ready.is_file() and self.cycle == self.cycles - 1
                    and self.released_ns is not None, 'premature final report')
        self.retained = names
        return names

    def _write(self, name, value='release'):
        with (self.root / name).open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(value + '\n')

    def poll(self):
        names = self._inventory()
        events = []
        prefix = 'connection' if self.role == 'source' else 'destination'
        if f'{prefix}-{self.cycle}.active' in names and self.active_ns is None:
            binding = self.capture()
            require(binding.get('status') == 'MEASURED_LIVE_SOCKET_SNAPSHOT'
                    and len(binding.get('sockets', [])) == 1, 'one live socket required')
            write_json(self.output / f'socket-binding-{self.cycle}.json', binding)
            self.active_ns = self.clock()
            events.append(dict(event='active', cycle=self.cycle))
        if self.role == 'source' and f'connection-{self.cycle}.ack' in names:
            require(self.released_ns is not None, 'ACK before release')
            if self.acked_ns is None:
                self.acked_ns = self.clock()
                events.append(dict(event='acked', cycle=self.cycle))
        ready = self.root / 'destination.report-ready'
        require(not ready.is_symlink(), 'invalid report marker')
        if self.role == 'destination' and ready.exists():
            require(ready.is_file() and self.cycle == self.cycles - 1
                    and self.released_ns is not None, 'premature final report')
            if self.report_ns is None:
                self.report_ns = self.clock()
                events.append(dict(event='report_ready', cycle=self.cycle))
        return events

    def request(self, operation, cycle):
        require(type(cycle) is int and 0 <= cycle < self.cycles, 'invalid cycle index')
        self._inventory()
        require(not self.final_released, 'cycle barrier already complete')
        if operation == 'start':
            require(cycle == self.cycle + 1, 'next cycle required')
            if self.cycle >= 0:
                origin = self.acked_ns if self.role == 'source' else self.released_ns
                require(origin is not None and self.clock() - origin >= 2_000_000_000,
                        'completed cycle and two-second cooldown required')
            if self.role == 'source':
                self._write(f'connection-{cycle}.start', 'start')
            self.cycle = cycle
            self.active_ns = self.released_ns = self.acked_ns = None
            return [dict(event='started', cycle=cycle)]
        require(cycle == self.cycle, 'current cycle required')
        if operation == 'release':
            require(self.active_ns is not None and self.released_ns is None,
                    'unreleased active cycle required')
            require(self.clock() - self.active_ns >= 2_000_000_000, 'two-second hold required')
            self._write(f'connection-{cycle}.release')
            self.released_ns = self.clock()
            return [dict(event='released', cycle=cycle)]
        require(operation == 'final_release' and cycle == self.cycles - 1, 'final cycle operation required')
        origin = self.acked_ns if self.role == 'source' else self.report_ns
        require(origin is not None and self.clock() - origin >= 2_000_000_000,
                'final two-second cooldown required')
        self._write('source.final-release' if self.role == 'source' else 'destination.report-release')
        self.final_released = True
        return [dict(event='final_released', cycle=cycle)]
