"""Destination resource ownership ends before late management telemetry may end."""

from contextlib import ExitStack
import json
import queue
import time

from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_native_live import LocalLiveGuard
from scripts.performance.linux_native_source_observer import read_records, source_records, validate_resource
from scripts.performance.linux_resources import LinuxResourceSampler


class DestinationObserver:
    result_key = 'destination_live_resources'

    def __init__(self, root, *, pid, cpus, payload_bytes, deadline_ns,
                 sampler_factory=LinuxResourceSampler, clock=time.monotonic_ns):
        self.root, self.clock, self.deadline = root, clock, deadline_ns
        self.events_path = root.parent / 'destination-live-events.ndjson'
        self.guard = LocalLiveGuard(role='destination', payload_bytes=payload_bytes,
                                    max_progress=1024, max_resources=250)
        self.queue = queue.Queue(maxsize=250)
        self.sampler = sampler_factory({'destination': pid}, cpus, interval_seconds=.5,
            max_records=250, record_sink=self.queue.put_nowait, terminal_roles=('destination',))
        self.stack = ExitStack()
        self.started = self.stopped = False
        self.resource_count = 0

    def __enter__(self):
        try:
            with self.events_path.open('xb'):
                pass
            self.resources = self.stack.enter_context((self.root / 'destination-live-resources.ndjson').open('xb'))
            self.sampler.start()
            self.started = True
            return self
        except BaseException:
            self.stack.close()
            raise

    def record(self, kind, value, **extra):
        with self.events_path.open('ab') as stream:
            stream.write((json.dumps(dict(kind=kind, value=value, **extra), allow_nan=False)+'\n').encode())

    def drain_resources(self):
        while True:
            try:
                row = self.queue.get_nowait()
            except queue.Empty:
                return
            self.resources.write((json.dumps(row, allow_nan=False)+'\n').encode())
            self.resources.flush()
            self.record('resource', row)
            self.guard.resource(row)
            self.resource_count += 1

    def poll(self):
        require(self.clock() < self.deadline, 'destination live observer deadline')
        self.sampler.check_health(require_running=not self.stopped)
        self.drain_resources()

    def stop(self):
        if not self.stopped:
            self.sampler.stop()
            self.stopped = True
            self.drain_resources()

    def source_event(self, kind, value, *, received_ns):
        require(kind in ('paced_progress', 'paced_final'), 'unknown relayed source event')
        self.poll()
        if kind == 'paced_progress':
            self.record('progress', value, received_ns=received_ns)
            self.guard.progress(value, received_ns=received_ns)
        else:
            require(type(received_ns) is int and received_ns >= self.guard.last_received,
                    'invalid local final receipt clock')
            self.stop()
            self.record('final', value, received_ns=received_ns)
            self.guard.finish(value)

    def finish(self, returncode):
        require(self.stopped and returncode == 0, 'owned destination collection did not finish cleanly')
        return dict(resource_collection_complete=True, samples=self.resource_count,
                    scope='owned destination samples only; source telemetry is joined at endpoint completion')

    def __exit__(self, kind, value, tb):
        try:
            if self.started and not self.stopped:
                self.stop()
        finally:
            self.stack.close()


def replay_destination(endpoint, source_peer, *, payload_bytes):
    peer = endpoint / 'peer'
    guard = LocalLiveGuard(role='destination', payload_bytes=payload_bytes, max_progress=1024, max_resources=250)
    resources, telemetry = [], []
    previous = None
    for row in read_records(endpoint / 'destination-live-events.ndjson', 1275):
        kind = row.get('kind')
        require(set(row) == ({'kind', 'value'} if kind == 'resource' else {'kind', 'value', 'received_ns'}),
                'invalid destination local event fields')
        if kind == 'resource':
            validate_resource(peer, row['value'], previous)
            guard.resource(row['value'])
            resources.append(row['value'])
            previous = row['value']
        elif kind == 'progress':
            guard.progress(row['value'], received_ns=row['received_ns'])
            telemetry.append(row['value'])
        elif kind == 'final':
            require(type(row['received_ns']) is int and row['received_ns'] >= guard.last_received,
                    'invalid final receipt clock')
            guard.finish(row['value'])
            telemetry.append(row['value'])
        else:
            raise ValueError('unknown destination local event')
    require(guard.final is not None and telemetry == source_records(source_peer),
            'destination/source telemetry mismatch')
    require(resources == list(read_records(peer / 'destination-live-resources.ndjson', 250)),
            'destination owned/local resource mismatch')
    result = guard.qualification()
    require(result == json.loads((endpoint / 'result.json').read_bytes())['destination_live_guard'],
            'destination live result mismatch')
    return result
