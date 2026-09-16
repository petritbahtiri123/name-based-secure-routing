"""External, bounded diagnostic observer; no writes to observed processes."""
import json
import os
from pathlib import Path
import signal
import sys
import time


def identity(text):
    close = text.rfind(')')
    fields = text[close + 2:].split()
    if close < 0 or len(fields) < 20:
        raise ValueError('malformed task stat')
    return int(text.split(' ', 1)[0]), int(fields[19])


def read_task(path):
    before = identity((path / 'stat').read_text())
    values = (path / 'schedstat').read_text().split()
    if len(values) != 3 or any(not v.isascii() or not v.isdecimal() for v in values):
        raise ValueError('malformed scheduler counters')
    after = identity((path / 'stat').read_text())
    if before != after:
        raise ValueError('task identity changed')
    return dict(tid=before[0], start_ticks=before[1],
                **dict(zip(('runtime_ns', 'runqueue_ns', 'timeslices'), map(int, values))))


def sample_process(base, role):
    before = identity((base / 'stat').read_text())
    tasks = sorted((base / 'task').iterdir(), key=lambda p: int(p.name))
    start = time.monotonic_ns()
    values = [read_task(task) for task in tasks]
    if [p.name for p in tasks] != sorted((p.name for p in (base / 'task').iterdir()), key=int):
        raise ValueError('task set changed')
    if identity((base / 'stat').read_text()) != before:
        raise ValueError('process identity changed')
    return dict(event='scheduler_sample', role=role, pid=before[0], start_ticks=before[1],
                timestamp_ns=start, end_ns=time.monotonic_ns(), tasks=values)


def main():
    prefix = Path(sys.argv[1])
    stopped = False

    def stop(*_args):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    targets = {'/tmp/binaries/perf_rust_source': 'source',
               '/tmp/binaries/wp8_interop_server': 'destination_0'}
    with prefix.with_suffix('.ndjson').open('x') as output:
        def emit(value):
            output.write(json.dumps(value) + '\n')
            output.flush()

        emit(dict(event='observer_start', pid=os.getpid(), timestamp_ns=time.monotonic_ns(),
                  affinity=sorted(os.sched_getaffinity(0)), targets=targets, interval_seconds=1))
        prefix.with_suffix('.ready').write_text('ready\n')
        deadline = time.monotonic() + 660
        while not stopped and time.monotonic() < deadline:
            iteration = time.monotonic()
            for base in Path('/proc').iterdir():
                if not base.name.isdecimal():
                    continue
                try:
                    name = os.readlink(base / 'exe')
                except (FileNotFoundError, PermissionError, ProcessLookupError):
                    continue
                role = targets.get(name)
                if role is None:
                    continue
                try:
                    emit(sample_process(base, role))
                except (OSError, ValueError) as error:
                    emit(dict(event='sample_unavailable', role=role, pid=int(base.name),
                              timestamp_ns=time.monotonic_ns(), error=str(error)))
            try:
                cpu = dict(line.split() for line in Path('/sys/fs/cgroup/cpu.stat').read_text().splitlines())
                emit(dict(event='cgroup_cpu', timestamp_ns=time.monotonic_ns(),
                          counters={k: int(v) for k, v in cpu.items()}))
            except (OSError, ValueError) as error:
                emit(dict(event='cgroup_unavailable', error=str(error)))
            time.sleep(max(0, 1 - (time.monotonic() - iteration)))
        emit(dict(event='observer_end', timestamp_ns=time.monotonic_ns(), stopped=stopped))


if __name__ == '__main__':
    main()
