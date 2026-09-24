"""Opt-in short source-only diagnostic observer; destination memory is absent."""

from contextlib import ExitStack
import json
import queue
import time

from scripts.performance.b5_stream import B5Stream
from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_loopback import digest, write_json
from scripts.performance.linux_native_lifecycle_control import decode_object
from scripts.performance.linux_native_live import LocalLiveGuard
from scripts.performance.linux_resources import LinuxResourceSampler


class SourceObserver:
    result_key = 'source_live_guard'

    def __init__(self, root, *, pid, cpus, payload_bytes, deadline_ns,
                 sampler_factory=LinuxResourceSampler, clock=time.monotonic_ns, on_record=None):
        require(on_record is None or callable(on_record), 'invalid source record callback')
        self.on_record = on_record
        self.root, self.clock = root, clock
        self.guard = LocalLiveGuard(role='source', payload_bytes=payload_bytes,
                                    max_progress=1024, max_resources=250)
        self.queue = queue.Queue(maxsize=250)
        self.sampler = sampler_factory({'source': pid}, cpus, interval_seconds=.5,
            max_records=250, record_sink=self.queue.put_nowait, terminal_roles=('source',))
        self.deadline, self.payload = deadline_ns, payload_bytes
        self.stack = ExitStack()
        self.started = self.stopped = False

    def __enter__(self):
        try:
            self.events = self.stack.enter_context((self.root / 'live-events.ndjson').open('xb'))
            self.input = self.stack.enter_context((self.root / 'stdout').open('rb'))
            raw = self.stack.enter_context((self.root / 'live-observed-stdout').open('xb'))
            self.stream = B5Stream(raw_sink=raw, groups=1, payload_bytes=self.payload,
                sampler=self.sampler, deadline_ns=self.deadline, max_line_bytes=65536,
                max_lines=1024, clock=self.clock, on_progress=self.progress)
            self.sampler.start()
            self.started = True
            return self
        except BaseException:
            self.stack.close()
            raise

    def record(self, kind, value, **fields):
        self.events.write((json.dumps(dict(kind=kind, value=value, **fields), allow_nan=False)+'\n').encode())
        self.events.flush()

    def drain_resources(self):
        while True:
            try:
                row = self.queue.get_nowait()
            except queue.Empty:
                return
            self.record('resource', row)
            self.guard.resource(row)

    def progress(self, row):
        self.drain_resources()
        received = self.clock()
        self.record('progress', row, received_ns=received)
        self.guard.progress(row, received_ns=received)
        if self.on_record is not None:
            self.on_record('paced_progress', row)

    def poll(self):
        self.drain_resources()
        self.stream.check(source_active=not self.stopped)
        # Bounded work per owner poll; a noisy child cannot postpone cancellation.
        for _ in range(4):
            wire = self.input.read(65536)
            if not wire:
                break
            self.stream.feed(wire, source_active=not self.stopped)

    def stop(self):
        if not self.stopped:
            self.sampler.stop()
            self.stopped = True
            self.drain_resources()

    def finish(self, returncode):
        require(self.stopped, 'stop sampler before reaping/finishing source')
        self.poll()
        require(not self.input.read(1), 'unconsumed bounded source stdout')
        final = self.stream.finish(returncode)
        self.record('final', final)
        self.guard.finish(final)
        if self.on_record is not None:
            self.on_record('paced_final', final)
        result = self.guard.qualification()
        write_json(self.root / 'live-result.json', result)
        return result

    def __exit__(self, kind, value, tb):
        try:
            if self.started and not self.stopped:
                self.stop()
        finally:
            self.stack.close()


def read_records(path, limit):
    with path.open('rb') as stream:
        for index in range(limit + 1):
            wire = stream.readline(65537)
            if not wire:
                break
            require(index < limit and len(wire) <= 65536 and wire.endswith(b'\n'), 'record replay bound')
            yield decode_object(wire)


def source_records(root):
    expected, final = [], False
    for row in read_records(root / 'stdout', 1024):
        require(not final, 'source record after final')
        if row.get('schema') in ('nbsr-b5-grouped-progress-v1', 'nbsr-b5-grouped-final-v1'):
            expected.append(row)
            final = row['schema'] == 'nbsr-b5-grouped-final-v1'
        else:
            require(row.get('event') == 'diagnostic'
                    and not str(row.get('schema', '')).startswith('nbsr-b5'), 'unknown stdout record')
    require(final, 'source final missing')
    return expected


def validate_resource(root, resource, previous):
    pid = json.loads((root / 'pid.json').read_bytes())['pid']
    cpus = json.loads((root / 'environment.json').read_bytes())['linux_environment']['selected_cpus']
    require(isinstance(resource, dict) and resource.get('pid') == pid
            and resource.get('affinity') == cpus, 'local resource ownership/affinity mismatch')
    require(all(type(resource.get(key)) is int and resource[key] >= 0
                for key in ('pid', 'start_ticks', 'cpu_ns', 'timestamp_ns')),
            'invalid resource identity/counter')
    if previous is not None:
        require(resource['start_ticks'] == previous['start_ticks']
                and resource['cpu_ns'] >= previous['cpu_ns']
                and resource['timestamp_ns'] > previous['timestamp_ns'],
                'local resource continuity mismatch')
    require(resource.get('memory_state') == ('UNAVAILABLE_ZOMBIE'
            if resource.get('state') == 'Z' else 'MEASURED'), 'resource memory state mismatch')


def replay(root, *, payload_bytes):
    require(digest(root / 'stdout') == digest(root / 'live-observed-stdout'),
            'observed/source stdout mismatch')
    expected = source_records(root)
    guard = LocalLiveGuard(role='source', payload_bytes=payload_bytes, max_progress=1024, max_resources=250)
    actual = []
    previous_resource = None
    with (root / 'live-events.ndjson').open('rb') as stream:
        for index in range(1276):
            wire = stream.readline(65537)
            if not wire:
                break
            require(index < 1275 and len(wire) <= 65536 and wire.endswith(b'\n'), 'local event replay bound')
            row = decode_object(wire)
            kind = row.get('kind')
            require(set(row) == ({'kind', 'value', 'received_ns'} if kind == 'progress' else {'kind', 'value'}),
                    'invalid local event fields')
            if kind == 'resource':
                resource = row['value']
                validate_resource(root, resource, previous_resource)
                previous_resource = resource
                guard.resource(resource)
            elif kind == 'progress':
                guard.progress(row['value'], received_ns=row['received_ns'])
                actual.append(row['value'])
            elif kind == 'final':
                guard.finish(row['value'])
                actual.append(row['value'])
            else:
                raise ValueError('unknown local event')
    require(guard.final is not None and actual == expected, 'local progress/final differs from stdout')
    result = guard.qualification()
    require(result == json.loads((root / 'live-result.json').read_bytes()), 'local guard result mismatch')
    return result
