"""Explicit Linux B3 capture; no Windows metric aliases or global backend state."""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time

from scripts.performance.linux_loopback import physical_cpu_sets
from scripts.performance.linux_resources import sample_linux_process

FIELDS = ('cpu_ns', 'rss_bytes', 'pss_bytes', 'private_resident_bytes', 'private_hugetlb_bytes', 'fd_count')


def environment(cores):
    if platform.system() != 'Linux':
        raise RuntimeError('explicit Linux platform requires Linux')
    taskset, lscpu = shutil.which('taskset'), shutil.which('lscpu')
    if not taskset or not lscpu:
        raise RuntimeError('taskset and lscpu required')
    topology = json.loads(subprocess.check_output([lscpu, '-J', '-e=CPU,CORE,SOCKET,NODE,ONLINE'], text=True))
    allowed = sorted(os.sched_getaffinity(0))
    cpus = physical_cpu_sets(topology, allowed, [cores])[cores]
    observed = {}
    for name in ('cpu.max', 'cpu.stat', 'cpuset.cpus.effective', 'memory.max', 'pids.max'):
        path = Path('/sys/fs/cgroup') / name
        try:
            observed[str(path)] = path.read_text()
        except OSError as error:
            observed[str(path)] = {'status': 'UNAVAILABLE', 'error': type(error).__name__}
    return dict(platform='linux', kernel=platform.platform(), python=platform.python_version(),
                topology=topology, inherited_cpus=allowed, selected_cpus=cpus,
                taskset=taskset, taskset_version=subprocess.check_output([taskset, '--version'], text=True).strip(),
                lscpu_version=subprocess.check_output([lscpu, '--version'], text=True).strip(),
                proc_cgroup=Path('/proc/self/cgroup').read_text(),
                proc_mountinfo=Path('/proc/self/mountinfo').read_text(), cgroup_observed=observed,
                scope='Linux shared physical-core-selected logical pool; guest/cgroup observations, not dedicated hardware proof')


class LinuxCapture:
    def __init__(self, cpus, taskset, *, sample_fn=sample_linux_process, max_records=10000):
        if not cpus or len(set(cpus)) != len(cpus) or any(type(cpu) is not int or cpu < 0 for cpu in cpus):
            raise ValueError('invalid CPU pool')
        if not taskset or type(max_records) is not int or max_records < 1:
            raise ValueError('invalid capture configuration')
        self.cpus, self.taskset = sorted(cpus), str(taskset)
        self._sample, self._cap = sample_fn, max_records
        self._identities, self._previous = {}, {}
        self._count = 0

    def command(self, argv):
        return [self.taskset, '-c', ','.join(map(str, self.cpus)), *argv]

    def capture_once(self, resources, destination, clients, *, phase, cycle):
        expected = {'destination': [destination], 'source': list(clients)}
        ids = {role: tuple(p.pid for p in processes) for role, processes in expected.items()}
        if not ids['source'] or len(set(ids['source'] + ids['destination'])) != sum(map(len, ids.values())):
            raise RuntimeError('missing or duplicate expected process')
        if self._identities and ids != self._identities:
            raise RuntimeError('process identity/count changed across phases')
        self._identities = ids
        for role, processes in expected.items():
            if self._count >= self._cap:
                raise RuntimeError('Linux B3 sample cap exceeded')
            samples = []
            for process in processes:
                if process.poll() is not None:
                    raise RuntimeError('expected live process exited before phase capture')
                row = deepcopy(self._sample(process.pid, self.cpus))
                if (row.get('pid') != process.pid or row.get('state') == 'Z'
                        or row.get('memory_state') != 'MEASURED' or row.get('affinity') != self.cpus):
                    raise RuntimeError('live resource identity/memory/affinity unavailable')
                for field in (*FIELDS, 'start_ticks', 'timestamp_ns'):
                    if type(row.get(field)) is not int or row[field] < 0:
                        raise RuntimeError('invalid Linux resource metric')
                prior = self._previous.get(process.pid)
                if prior is not None and (row['start_ticks'] != prior[0] or row['cpu_ns'] < prior[1]
                                          or row['timestamp_ns'] <= prior[2]):
                    raise RuntimeError('Linux process continuity failed')
                self._previous[process.pid] = row['start_ticks'], row['cpu_ns'], row['timestamp_ns']
                samples.append(row)
            resources.append(dict(platform='linux', role=role, phase=phase, cycle=cycle,
                timestamp_ns=max(row['timestamp_ns'] for row in samples), processes=samples,
                process_count=len(samples), memory_basis='linux_smaps_rollup',
                thread_count=sum(len(row['thread_ids']) for row in samples),
                **{field: sum(row[field] for row in samples) for field in FIELDS}))
            self._count += 1

    def capture(self, resources, destination, clients, *, phase, cycle, seconds, cadence):
        if not all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in (seconds, cadence)):
            raise ValueError('invalid capture duration/cadence')
        deadline = time.monotonic() + seconds
        while True:
            self.capture_once(resources, destination, clients, phase=phase, cycle=cycle)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(cadence, remaining))
