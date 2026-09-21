"""Per-host private control endpoint for the native lifecycle benchmark."""

import copy
import json
import io
import os
import platform
import queue
import re
import sys
import threading
import time

from scripts.performance import linux_native_lifecycle as native
from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.linux_loopback import ROOT, write_json
from scripts.performance.linux_native_lifecycle_control import LifecycleBarrier, decode_control
from scripts.performance.linux_native_peer import validate_endpoint
from scripts.performance.linux_socket_ownership import snapshot, validate_binding
from scripts.performance.process_cancellation import Cancellation


def read_optional_json(path):
    require(not path.is_symlink(), 'symlink control artifact')
    try:
        return json.loads(path.read_bytes())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


class EndpointControl:
    def __init__(self, args, output, *, capture=None):
        self.args = args
        self.prepared = self.ready_sent = self.transferred = False
        self.barrier = LifecycleBarrier(role=args.role, count=args.count, root=args.lifecycle,
            output=output, capture=capture or self.capture)

    def capture(self):
        peer = self.args.output
        pid = json.loads((peer / 'pid.json').read_bytes())['pid']
        with (peer / 'resources.ndjson').open() as stream:
            first = json.loads(stream.readline())
        require(first['pid'] == pid, 'resource/PID identity mismatch')
        binary = json.loads((peer / 'command.json').read_bytes())['argv'][3]
        address, _ = validate_endpoint(self.args.bind, allow_zero=True)
        value = snapshot(pid, first['start_ticks'], binary, address)
        require(value['status'] == 'MEASURED_LIVE_SOCKET_SNAPSHOT', 'live socket observation unavailable')
        require(len({entry['inode'] for entry in value['sockets']}) == len(value['sockets']),
                'unique live socket inodes required')
        for entry in value['sockets']:
            validate_binding(value, pid=pid, start_ticks=first['start_ticks'], binary=binary, local=entry['local'])
        return value

    def validate_readiness(self, value, address):
        require(isinstance(value, dict), 'invalid readiness object')
        host, _ = validate_endpoint(value.get('endpoint'), allow_zero=False)
        require(host == address and value.get('alpn') == 'nbsr-quic-1', 'readiness address/ALPN mismatch')

    def poll(self):
        events = []
        if self.args.role == 'source' and not self.prepared:
            value = read_optional_json(self.args.output / 'source-prepared.json')
            if value is not None:
                require(isinstance(value, dict) and value.get('status') == 'PREPARED_NOT_CONNECTED',
                        'invalid prepared record')
                self.prepared = True
                events.append(dict(event='prepared'))
        if self.args.role == 'destination' and not self.ready_sent:
            value = read_optional_json(self.args.output / 'ready.json')
            if value is not None:
                address, _ = validate_endpoint(self.args.bind, allow_zero=True)
                self.validate_readiness(value, address)
                self.ready_sent = True
                events.append(dict(event='ready', value=value))
        return events + self.barrier.poll()

    def request(self, message):
        operation = message['op']
        if operation == 'cancel':
            raise InterruptedError('control cancellation requested')
        if operation != 'readiness':
            return self.barrier.request(operation)
        require(self.args.role == 'source', 'source only readiness transfer')
        require(self.prepared, 'source must be prepared')
        require(not self.transferred, 'readiness transfer permitted once')
        self.validate_readiness(message['value'], self.args.destination_address)
        path = self.args.ready_input
        require(not path.exists() and not path.is_symlink(), 'fresh readiness path required')
        # Exclusive creation cannot overwrite stale state. The native source
        # already tolerates an incomplete JSON write within its bounded wait.
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(message['value'], sort_keys=True, allow_nan=False) + '\n')
        self.transferred = True
        return [dict(event='readiness_transferred')]


def read_commands(stream, messages, stop=None):
    """Bounded frames; stop real pipe reads before interpreter finalization."""
    stop = stop if stop is not None else threading.Event()

    def put(value):
        while not stop.is_set():
            try:
                messages.put(value, timeout=.05)
                return True
            except queue.Full:
                pass
        return False

    fd, blocking = None, None
    try:
        try:
            fd = stream.fileno()
        except (AttributeError, io.UnsupportedOperation):
            pass  # In-memory unit-test streams have no blocking OS descriptor.
        if fd is None:
            while not stop.is_set():
                wire = stream.readline(65537)
                if not put(wire or None) or not wire:
                    return
        else:
            blocking = os.get_blocking(fd)
            os.set_blocking(fd, False)
            pending = bytearray()
            while not stop.is_set():
                try:
                    chunk = os.read(fd, min(4096, 65537 - len(pending)))
                except BlockingIOError:
                    stop.wait(.01)
                    continue
                if not chunk:
                    if pending:
                        put(bytes(pending))
                    put(None)
                    return
                pending.extend(chunk)
                while b'\n' in pending:
                    end = pending.index(b'\n') + 1
                    if not put(bytes(pending[:end])):
                        return
                    del pending[:end]
                if len(pending) >= 65537:
                    put(bytes(pending))
                    return
    except BaseException as error:
        put(error)
    finally:
        if fd is not None and blocking is not None:
            os.set_blocking(fd, blocking)


def watch_control(control, messages, emit, stop, errors):
    received = 0
    try:
        while not stop.wait(.01):
            for event in control.poll():
                emit(event)
            try:
                wire = messages.get_nowait()
            except queue.Empty:
                continue
            if wire is None:
                raise InterruptedError('control EOF before completion')
            if isinstance(wire, BaseException):
                raise wire
            received += 1
            require(received <= 8, 'control command count exceeded')
            require(isinstance(wire, bytes) and wire.endswith(b'\n'), 'unterminated control frame')
            for event in control.request(decode_control(wire)):
                emit(event)
    except BaseException as error:
        errors.append(error)


def preserve_markers(lifecycle, output):
    output.mkdir()
    for path in lifecycle.iterdir():
        if not re.fullmatch(r'(?:connection|destination)-[0-9]+\.(?:start|active|release|ack|failed)'
                            r'|destination\.report-(?:ready|release)', path.name):
            continue
        require(path.is_file() and not path.is_symlink(), 'invalid public marker')
        with path.open('rb') as stream:
            wire = stream.read(65537)
        require(len(wire) <= 65536, 'public marker size bound')
        (output / path.name).write_bytes(wire)


def execute_endpoint(args, *, input_stream=None, output_stream=None, delegate=native.execute):
    require(platform.system() == 'Linux', 'Linux required')
    args = copy.copy(args)
    require(args.ready_input is None, 'control endpoint manages readiness input')
    require(args.role == 'source' or not args.prepare_before_readiness, 'source only preparation')
    require(not args.output.is_symlink(), 'symlink output root')
    output = args.output.resolve()
    require(not output.is_relative_to(ROOT), 'evidence must be outside checkout')
    for private in (args.authority.resolve(), args.lifecycle.resolve()):
        require(not private.is_relative_to(output) and not output.is_relative_to(private),
                'private fixture and public output must be disjoint')
    require(args.lifecycle.is_dir() and not args.lifecycle.is_symlink()
            and {p.name for p in args.lifecycle.iterdir()} == {'00'}, 'fresh lifecycle fixture required')
    input_stream = input_stream if input_stream is not None else sys.stdin.buffer
    output_stream = output_stream if output_stream is not None else sys.stdout
    output.mkdir(parents=False, exist_ok=False)
    args.output = output / 'peer'
    args.prepare_before_readiness = args.role == 'source'
    args.ready_input = output / 'transferred-readiness.json' if args.role == 'source' else None
    stop, errors, watcher, reader = threading.Event(), [], None, None
    try:
        if args.role == 'source':
            for i in range(args.count):
                with (args.lifecycle / f'connection-{i}.start').open('x') as stream:
                    stream.write('start\n')
        write_json(output / 'controller.json', dict(schema='nbsr-native-lifecycle-control-v1',
            role=args.role, count=args.count, peer_output=str(args.output),
            control_input='bounded private stdin JSON lines', timing='DIAGNOSTIC_ONLY',
            hold_seconds=2, cooldown_seconds=2, child_ownership='delegated to linux_native_lifecycle.execute'))
        control = EndpointControl(args, output)
        messages = queue.Queue(maxsize=8)
        with (output / 'events.ndjson').open('x', encoding='utf-8', newline='\n') as log:
            def emit(value):
                event = dict(schema='nbsr-native-lifecycle-control-v1', role=args.role,
                             timestamp_ns=time.monotonic_ns(), **value)
                wire = json.dumps(event, sort_keys=True, allow_nan=False) + '\n'
                log.write(wire)
                log.flush()
                output_stream.write(wire)
                output_stream.flush()

            reader = threading.Thread(target=read_commands, args=(input_stream, messages, stop), daemon=True)
            reader.start()
            watcher = threading.Thread(target=watch_control, args=(control, messages, emit, stop, errors), daemon=True)
            watcher.start()
            try:
                with Cancellation() as cancellation:
                    def check_cancelled():
                        cancellation.check()
                        if errors:
                            raise InterruptedError(str(errors[0])) from errors[0]

                    outcome = delegate(args, check_cancelled=check_cancelled)
                stop.set()
                watcher.join(timeout=2)
                require(not watcher.is_alive(), 'control watcher did not stop')
                check_cancelled()
                for event in control.poll():
                    emit(event)
                require(control.barrier.acked if args.role == 'source' else control.barrier.report_released,
                        'delegate completed before control barriers')
                preserve_markers(args.lifecycle, output / 'markers')
                write_json(output / 'result.json', dict(status='PASS_FUNCTIONAL_ENDPOINT', role=args.role,
                    peer=outcome, sustainable_capacity='NOT_ESTABLISHED', physical_hardware='NOT_PROVEN'))
                emit(dict(event='complete', count=args.count))
                return outcome
            finally:
                stop.set()
                watcher.join(timeout=2)
    except BaseException as error:
        write_json(output / 'failure.json', dict(status='INVALID_PARTIAL', error_type=type(error).__name__, error=str(error)))
        if not (output / 'markers').exists():
            try:
                preserve_markers(args.lifecycle, output / 'markers')
            except (OSError, ValueError) as marker_error:
                write_json(output / 'marker-preservation-error.json', dict(error=str(marker_error)))
        raise
    finally:
        stop.set()
        if watcher is not None and watcher.is_alive():
            watcher.join(timeout=2)
        if reader is not None:
            reader.join(timeout=2)
        seal_output(output)


def main():
    execute_endpoint(native.argument_parser().parse_args())


if __name__ == '__main__':
    main()
