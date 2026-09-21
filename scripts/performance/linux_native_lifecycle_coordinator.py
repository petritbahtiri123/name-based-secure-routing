"""Coordinate a bounded native lifecycle cell over private management streams."""

from pathlib import PurePosixPath
import json
import queue
import re
import subprocess
import threading
import time

from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_native_lifecycle_control import decode_object
from scripts.performance.linux_native_lifecycle_remote import remote_command, remote_path
from scripts.performance.linux_native_peer import validate_endpoint
from scripts.performance.process_cancellation import not_cancelled


SEQUENCES = dict(source=('prepared', 'readiness_transferred', 'active', 'released', 'acked', 'complete'),
                 destination=('ready', 'active', 'released', 'report_ready', 'report_released', 'complete'))


def endpoint_arguments(config, role):
    target = config[role]
    argv = ['python3', '-B', '-m', 'scripts.performance.linux_native_lifecycle_endpoint', '--role', role]
    for field in ('binaries', 'build_manifest', 'authority', 'lifecycle', 'output', 'bind', 'cores'):
        argv.extend(['--' + field.replace('_', '-'), str(target[field])])
    for field in ('count', 'rate', 'shards'):
        argv.extend(['--' + field, str(config[field])])
    if role == 'source':
        address, _ = validate_endpoint(config['destination']['bind'], allow_zero=True)
        argv.extend(['--destination-address', address])
    return argv


def validate_config(value):
    require(isinstance(value, dict) and set(value) == {'schema', 'source_sha', 'count', 'rate', 'shards', 'source', 'destination'},
            'invalid coordinator fields')
    require(value['schema'] == 'nbsr-native-lifecycle-coordinator-v1'
            and isinstance(value['source_sha'], str) and re.fullmatch('[0-9a-f]{40}', value['source_sha']), 'invalid source/schema')
    for field, choices in [('count', (16, 32, 64, 128, 256, 512)), ('shards', (1, 2))]:
        require(type(value[field]) is int and value[field] in choices, 'invalid ' + field)
    require(type(value['rate']) is int and 1 <= value['rate'] <= 1000, 'invalid offered rate')
    for role in SEQUENCES:
        target = value[role]
        require(isinstance(target, dict) and set(target) == {'transport', 'host', 'checkout', 'binaries',
            'build_manifest', 'authority', 'lifecycle', 'output', 'bind', 'cores'}, 'invalid role configuration')
        remote_command(target, ['true'])  # Validation only; no remote operation.
        for field in ('binaries', 'build_manifest', 'authority', 'lifecycle', 'output'):
            remote_path(target[field])
        require(type(target['cores']) is int and target['cores'] in (1, 2, 4), 'invalid cores')
        _, port = validate_endpoint(target['bind'], allow_zero=True)
        require(role != 'source' or port == 0, 'source requires ephemeral bind')
        output = PurePosixPath(target['output'])
        require(not output.is_relative_to(PurePosixPath(target['checkout'])), 'output inside checkout')
        for field in ('authority', 'lifecycle'):
            private = PurePosixPath(target[field])
            require(not output.is_relative_to(private) and not private.is_relative_to(output), 'private/output overlap')
    source, destination = value['source'], value['destination']
    if (source['transport'], source['host']) == (destination['transport'], destination['host']):
        for field in ('output', 'lifecycle'):
            a, b = PurePosixPath(source[field]), PurePosixPath(destination[field])
            require(not a.is_relative_to(b) and not b.is_relative_to(a), 'same-host role paths overlap')
    return value


def drive(start, wait, send, finish, *, sleep):
    start('source')
    wait('source', 'prepared')
    start('destination')
    ready = wait('destination', 'ready')
    send('source', dict(op='readiness', value=ready['value']))
    wait('source', 'readiness_transferred')
    wait('source', 'active')
    wait('destination', 'active')
    sleep(2)
    send('destination', dict(op='release'))
    wait('destination', 'released')
    send('source', dict(op='release'))
    wait('source', 'released')
    wait('source', 'acked')
    wait('destination', 'report_ready')
    sleep(2)
    send('destination', dict(op='report_release'))
    wait('destination', 'report_released')
    wait('source', 'complete')
    wait('destination', 'complete')
    finish('source')
    finish('destination')


class EventLedger:
    def __init__(self, count):
        require(type(count) is int and count in (16, 32, 64, 128, 256, 512), 'invalid event count')
        self.count = count
        self.positions = dict.fromkeys(SEQUENCES, 0)
        self.last_time = dict.fromkeys(SEQUENCES, -1)
        self.received = {}

    def accept(self, role, wire):
        require(role in SEQUENCES, 'invalid role')
        value = decode_object(wire)
        position = self.positions[role]
        require(position < len(SEQUENCES[role]), 'event after completion')
        name = SEQUENCES[role][position]
        require(value.get('schema') == 'nbsr-native-lifecycle-control-v1'
                and value.get('role') == role and value.get('event') == name, 'event role/schema/order mismatch')
        fields = {'schema', 'role', 'event', 'timestamp_ns'}
        if name in ('active', 'released', 'acked', 'complete'):
            fields.add('count')
            require(type(value.get('count')) is int and value['count'] == self.count, 'event count mismatch')
        if name == 'ready':
            fields.add('value')
            require(isinstance(value.get('value'), dict), 'readiness object required')
        require(set(value) == fields and type(value.get('timestamp_ns')) is int
                and value['timestamp_ns'] >= 0 and value['timestamp_ns'] >= self.last_time[role], 'event fields/clock mismatch')
        self.positions[role] += 1
        self.last_time[role] = value['timestamp_ns']
        self.received[role, name] = value
        return value

    def eof(self, role):
        if self.positions[role] != len(SEQUENCES[role]):
            raise InterruptedError(role + ' control EOF before completion')


class Manager:
    """Own local management relays; remote cleanup requires endpoint evidence."""

    def __init__(self, count, output, *, timeout=120, cleanup_timeout=15, check_cancelled=not_cancelled):
        require(0 < timeout <= 120 and 0 < cleanup_timeout <= 15, 'invalid management deadline')
        self.ledger = EventLedger(count)
        self.output = output
        self.deadline = time.monotonic() + timeout
        self.cleanup_timeout = cleanup_timeout
        self.check_cancelled = check_cancelled
        self.children, self.readers, self.errors = {}, {}, {}
        self.messages = queue.Queue(maxsize=32)
        self.stop = threading.Event()
        self.eof_roles = set()
        self.log = (output / 'management.ndjson').open('x', encoding='utf-8', newline='\n')

    def record(self, **value):
        self.log.write(json.dumps(dict(timestamp_ns=time.monotonic_ns(), **value), allow_nan=False) + '\n')
        self.log.flush()

    def check(self):
        self.check_cancelled()
        if time.monotonic() >= self.deadline:
            raise TimeoutError('management deadline')

    def start_command(self, role, command):
        self.check()
        require(role in SEQUENCES and role not in self.children, 'duplicate/unknown role')
        self.record(action='start', role=role, command=command)
        errors = (self.output / (role + '-stderr.log')).open('xb')
        self.errors[role] = errors
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, bufsize=0)
        self.children[role] = child

        def read():
            try:
                while not self.stop.is_set():
                    wire = child.stdout.readline(65537)
                    value = wire if wire else None
                    while not self.stop.is_set():
                        try:
                            self.messages.put((role, value), timeout=.05)
                            break
                        except queue.Full:
                            pass
                    if not wire or len(wire) > 65536 or not wire.endswith(b'\n'):
                        break
            except (OSError, ValueError) as error:
                if not self.stop.is_set():
                    try:
                        self.messages.put((role, error), timeout=.1)
                    except queue.Full:
                        pass

        reader = threading.Thread(target=read, daemon=True)
        self.readers[role] = reader
        reader.start()
        return child

    def pump(self, delay=.02):
        self.check()
        try:
            role, wire = self.messages.get(timeout=delay)
        except queue.Empty:
            return
        if isinstance(wire, BaseException):
            raise InterruptedError('management reader failed') from wire
        if wire is None:
            self.ledger.eof(role)
            self.eof_roles.add(role)
            self.record(action='eof', role=role)
            return
        require(len(wire) <= 65536 and wire.endswith(b'\n'), 'bounded newline event required')
        value = self.ledger.accept(role, wire)
        self.record(action='receive', role=role, value=value)

    def wait(self, role, event):
        while (role, event) not in self.ledger.received:
            self.pump()
        self.check()
        return self.ledger.received[role, event]

    def send(self, role, value):
        self.check()
        wire = (json.dumps(value, allow_nan=False) + '\n').encode()
        require(len(wire) <= 65536, 'control message too large')
        child = self.children[role]
        result = queue.Queue(maxsize=1)

        def write():
            try:
                view = memoryview(wire)
                while view:
                    count = child.stdin.write(view)
                    require(count is not None and count > 0, 'control write failed')
                    view = view[count:]
                child.stdin.flush()
                result.put(None)
            except (OSError, ValueError) as error:
                result.put(error)

        threading.Thread(target=write, daemon=True).start()
        while True:
            self.check()
            try:
                error = result.get(timeout=.02)
                break
            except queue.Empty:
                self.pump(0)
        if error is not None:
            raise InterruptedError('control write failed') from error
        self.record(action='send', role=role, value=value)

    def sleep(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.pump(min(.02, max(0, deadline - time.monotonic())))

    def finish(self, role):
        child = self.children[role]
        while child.poll() is None or role not in self.eof_roles:
            self.pump()
        require(child.returncode == 0, 'endpoint relay failed: ' + role)
        self.record(action='exit', role=role, code=child.returncode)

    def close(self):
        # EOF reaches cooperative remote controllers. Never kill remote PIDs by name.
        for child in self.children.values():
            try:
                child.stdin.close()
            except (OSError, ValueError):
                pass
        deadline = time.monotonic() + self.cleanup_timeout
        while any(child.poll() is None for child in self.children.values()) and time.monotonic() < deadline:
            time.sleep(.02)
        outcomes = {}
        self.stop.set()
        for role, child in self.children.items():
            forced = child.poll() is None
            if forced:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            self.readers[role].join(timeout=2)
            child.stdout.close()
            self.errors[role].close()
            outcomes[role] = dict(exit_code=child.returncode, local_relay_forced=forced,
                                 remote_cleanup='UNCONFIRMED' if forced or child.returncode != 0 else 'REQUIRES_EVIDENCE')
        for role, errors in self.errors.items():
            if role not in self.children:
                errors.close()
        self.record(action='cleanup', outcomes=outcomes)
        self.log.close()
        return outcomes
