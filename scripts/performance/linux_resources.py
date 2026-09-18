"""Linux-only resource semantics; portable imports for synthetic proc tests."""
from copy import deepcopy
import math
from pathlib import Path
import re
import threading

from scripts.performance.linux_loopback import parse_proc_stat, sample_process


def parse_smaps_rollup(text: str) -> dict:
    required = {'Rss', 'Pss', 'Private_Clean', 'Private_Dirty', 'Private_Hugetlb'}
    fields = {}
    for line in text.splitlines():
        name = line.split(':', 1)[0]
        if name not in required:
            continue
        match = re.fullmatch(r'[^:]+:\s*([0-9]+)\s+kB\s*', line)
        if name in fields or match is None:
            raise ValueError(f'invalid or duplicate memory field: {name}')
        fields[name] = int(match[1]) * 1024
    if set(fields) != required:
        raise ValueError('missing required memory fields')
    return dict(rss_bytes=fields['Rss'], pss_bytes=fields['Pss'],
                private_resident_bytes=fields['Private_Clean'] + fields['Private_Dirty'],
                private_hugetlb_bytes=fields['Private_Hugetlb'], memory_basis='linux_smaps_rollup')


def sample_linux_process(pid, cpus, *, proc_root=Path('/proc'), ticks=None, page_size=None):
    base = proc_root / str(pid)
    initial_text = (base / 'stat').read_text()
    if int(initial_text.split(' ', 1)[0]) != pid:
        raise RuntimeError('process identity changed')
    initial = parse_proc_stat(initial_text, 1, 1)
    try:
        first = sample_process(pid, cpus, proc_root, ticks, page_size)
    except PermissionError as error:
        error.add_note('sample_linux_process phase=before_smaps')
        raise
    if initial['start_ticks'] != first['start_ticks']:
        raise RuntimeError('process identity changed')
    memory, failure = None, None
    if first['state'] != 'Z':
        try:
            memory = parse_smaps_rollup((base / 'smaps_rollup').read_text())
        except OSError as error:
            failure = error
    try:
        final = sample_process(pid, cpus, proc_root, ticks, page_size)
    except PermissionError as error:
        error.add_note('sample_linux_process phase=after_smaps')
        raise
    if final['start_ticks'] != first['start_ticks']:
        raise RuntimeError('process identity changed')
    if final['state'] == 'Z':
        memory = dict.fromkeys(('rss_bytes', 'pss_bytes', 'private_resident_bytes', 'private_hugetlb_bytes'))
        memory['memory_basis'] = 'linux_smaps_rollup'
        state = 'UNAVAILABLE_ZOMBIE'
    else:
        if failure is not None:
            raise failure
        if memory is None:
            raise RuntimeError('zombie process returned to live state')
        state = 'MEASURED'
    return {**final, **memory, 'memory_state': state}


class LinuxResourceSampler:
    """Bounded samples; terminal observation requires explicit per-role opt-in.

    The owner must keep opted-in children unreaped through stop/join. Their one
    terminal snapshot preserves identity/CPU, never invents live memory values.
    """

    def __init__(self, processes, cpus, *, interval_seconds, max_records,
                 record_sink=None, sample_fn=sample_linux_process, terminal_roles=(), role_cpus=None):
        if (not isinstance(processes, dict) or not processes
                or any(not isinstance(role, str) or not role or type(pid) is not int or pid <= 0
                       for role, pid in processes.items())
                or len(set(processes.values())) != len(processes)):
            raise ValueError('nonempty distinct owned process identities required')
        cpus = list(cpus)
        if not cpus or any(type(cpu) is not int or cpu < 0 for cpu in cpus) or len(set(cpus)) != len(cpus):
            raise ValueError('nonempty unique CPU set required')
        if (type(interval_seconds) not in (int, float) or not math.isfinite(interval_seconds)
                or interval_seconds <= 0 or type(max_records) is not int or max_records < 1):
            raise ValueError('invalid sampler bounds')
        self._processes, self._cpus = dict(processes), sorted(cpus)
        role_cpus = {role: self._cpus for role in processes} if role_cpus is None else role_cpus
        if (type(role_cpus) is not dict or set(role_cpus) != set(processes)
                or any(type(value) is not list or not value
                       or any(type(cpu) is not int or cpu not in self._cpus for cpu in value)
                       or len(set(value)) != len(value) for value in role_cpus.values())):
            raise ValueError('exact nonempty per-role CPU subsets required')
        self._role_cpus = {role: sorted(value) for role, value in role_cpus.items()}
        terminal_roles = tuple(terminal_roles)
        if (any(type(role) is not str or role not in processes for role in terminal_roles)
                or len(set(terminal_roles)) != len(terminal_roles)):
            raise ValueError('terminal roles must be distinct owned roles')
        self._terminal_roles = frozenset(terminal_roles)
        self._interval, self._cap = interval_seconds, max_records
        self._sink, self._sample = record_sink, sample_fn
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._records = []
        self._error = None

    def start(self):
        with self._lock:
            if self._thread is not None:
                raise RuntimeError('sampler can only start once')
            self._thread = threading.Thread(target=self._run, name='linux-resource-sampler', daemon=True)
            self._thread.start()

    def records_snapshot(self):
        with self._lock:
            return deepcopy(self._records)

    def check_health(self, require_running=False):
        with self._lock:
            if self._error is not None:
                raise RuntimeError('Linux resource sampling failed') from self._error
            if require_running and (self._thread is None or not self._thread.is_alive() or self._stop.is_set()):
                raise RuntimeError('Linux resource sampling not running')

    def stop(self):
        if self._thread is None:
            raise RuntimeError('sampler not started')
        self._stop.set()
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            with self._lock:
                self._error = self._error or RuntimeError('sampler thread failed to stop')
        self.check_health()
        records = self.records_snapshot()
        if not records:
            raise RuntimeError('no authoritative Linux resource samples')
        return records

    def _run(self):
        previous = {}
        terminal_seen = set()
        try:
            while not self._stop.is_set():
                for role, pid in self._processes.items():
                    if role in terminal_seen:
                        continue
                    with self._lock:
                        if len(self._records) >= self._cap:
                            raise RuntimeError('resource record cap exceeded')
                    expected_cpus = self._role_cpus[role]
                    sample = deepcopy(self._sample(pid, list(expected_cpus)))
                    for field in ('pid', 'start_ticks', 'cpu_ns', 'timestamp_ns'):
                        if type(sample.get(field)) is not int or sample[field] < 0:
                            raise RuntimeError('invalid integer resource identity/counter')
                    terminal = sample.get('state') == 'Z'
                    prior = previous.get(role)
                    if terminal:
                        memory_valid = (role in self._terminal_roles and prior is not None
                            and sample.get('memory_state') == 'UNAVAILABLE_ZOMBIE'
                            and all(field in sample and sample[field] is None for field in (
                                'rss_bytes', 'pss_bytes', 'private_resident_bytes', 'private_hugetlb_bytes')))
                    else:
                        memory_valid = sample.get('memory_state') == 'MEASURED'
                    if (sample['pid'] != pid or not memory_valid
                            or sample.get('affinity') != expected_cpus):
                        raise RuntimeError('lost live resource identity/memory/affinity')
                    if prior is not None and (sample['start_ticks'] != prior[0]
                                              or sample['cpu_ns'] < prior[1]
                                              or sample['timestamp_ns'] <= prior[2]):
                        raise RuntimeError('resource identity/counter continuity failed')
                    previous[role] = sample['start_ticks'], sample['cpu_ns'], sample['timestamp_ns']
                    sample['role'] = role
                    with self._lock:
                        self._records.append(sample)
                    if self._sink is not None:
                        self._sink(deepcopy(sample))
                    if terminal:
                        terminal_seen.add(role)
                self._stop.wait(self._interval)
        except BaseException as error:
            with self._lock:
                self._error = self._error or error
