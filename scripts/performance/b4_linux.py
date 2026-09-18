"""Per-run Linux B4 observation; no Windows resource aliases or shard inference."""
import json
import math
from pathlib import Path
import subprocess
import time
import traceback

from scripts.performance.linux_loopback import sample_process
from scripts.performance.linux_resources import sample_linux_process
from scripts.performance.process_cancellation import not_cancelled


def sample_b4_process(pid, cpus):
    """Failure-only exit observation; the B4 owner must confirm child completion."""
    try:
        return sample_linux_process(pid, cpus)
    except PermissionError:
        partial = sample_process(pid, cpus, allow_exiting=True)
        if partial['state'] == 'Z':
            state = 'UNAVAILABLE_ZOMBIE'
        elif partial['flags'] & 4 and partial['fd_count_state'] == 'UNAVAILABLE_EXITING':
            state = 'UNAVAILABLE_EXITING'
        else:
            raise
        return {**partial, **dict.fromkeys(('rss_bytes', 'pss_bytes',
                    'private_resident_bytes', 'private_hugetlb_bytes')),
                'memory_basis': 'linux_smaps_rollup', 'memory_state': state}


def failure_details(error):
    """Failure-only bounded traceback; retain terminal exception notes, no locals."""
    detail = ''.join(traceback.format_exception(error))
    return {'error_type': type(error).__name__, 'error': str(error)[:4096],
            'traceback': detail[-65536:], 'traceback_truncated': len(detail) > 65536}


def parse_host(stat, meminfo, *, timestamp_ns):
    lines = {line.split()[0]: line.split()[1:] for line in stat.splitlines() if line.split()}
    values = [int(v) for v in lines.get('cpu', [])]
    if len(values) < 8 or any(v < 0 for v in values):
        raise ValueError('Linux aggregate CPU counters unavailable')
    memory = {}
    for line in meminfo.splitlines():
        fields = line.split()
        if fields and fields[0] in ('MemTotal:', 'MemAvailable:'):
            if len(fields) != 3 or fields[2] != 'kB' or int(fields[1]) < 0:
                raise ValueError('Linux memory counter invalid')
            memory[fields[0]] = int(fields[1]) * 1024
    if set(memory) != {'MemTotal:', 'MemAvailable:'}:
        raise ValueError('Linux host memory unavailable')
    ctxt, running = int(lines['ctxt'][0]), int(lines['procs_running'][0])
    if min(ctxt, running) < 0:
        raise ValueError('Linux host counter invalid')
    return dict(timestamp_ns=timestamp_ns, status='MEASURED',
                cpu_jiffies=dict(zip(('user', 'nice', 'system', 'idle', 'iowait', 'irq', 'softirq', 'steal'), values)),
                context_switches_total=ctxt, runnable_tasks=running,
                mem_total_bytes=memory['MemTotal:'], mem_available_bytes=memory['MemAvailable:'])


def sample_host():
    return parse_host(Path('/proc/stat').read_text(), Path('/proc/meminfo').read_text(),
                      timestamp_ns=time.monotonic_ns())


class LinuxB4Backend:
    def __init__(self, cpus, taskset, *, sample_fn=sample_b4_process, host_fn=sample_host, max_records=10000,
                 verify_execution=None, check_cancelled=not_cancelled):
        if (not cpus or len(set(cpus)) != len(cpus) or any(type(v) is not int or v < 0 for v in cpus)
                or not taskset or type(max_records) is not int or max_records < 1):
            raise ValueError('invalid Linux observation bounds/placement')
        self.cpus, self.taskset = sorted(cpus), str(taskset)
        self.sample_fn, self.host_fn, self.cap = sample_fn, host_fn, max_records
        self.previous, self.host, self.round = {}, [], 0
        self.verify_execution = verify_execution
        self.check_cancelled = check_cancelled
        self.capture_valid = True
        self.exiting = {}

    def command(self, argv):
        return [self.taskset, '-c', ','.join(map(str, self.cpus)), *argv]

    def sample(self, processes, samples):
        self.check_cancelled()
        self.round += 1
        for role, process in processes.items():
            if process.poll() is not None:
                continue
            if len(samples) >= self.cap:
                raise RuntimeError('Linux B4 resource cap exceeded')
            try:
                row = dict(self.sample_fn(process.pid, self.cpus))
            except (ProcessLookupError, FileNotFoundError):
                if process.poll() is None:
                    raise
                continue
            if (row.get('pid') != process.pid or row.get('affinity') != self.cpus
                    or row.get('memory_state') not in ('MEASURED', 'UNAVAILABLE_ZOMBIE', 'UNAVAILABLE_EXITING')):
                raise RuntimeError('Linux B4 identity/affinity/memory unavailable')
            for field in ('start_ticks', 'cpu_ns', 'timestamp_ns'):
                if type(row.get(field)) is not int or row[field] < 0:
                    raise ValueError('invalid Linux B4 identity/CPU counter')
            if row['memory_state'] == 'MEASURED':
                for field in ('rss_bytes', 'pss_bytes', 'private_resident_bytes', 'private_hugetlb_bytes', 'fd_count'):
                    if type(row.get(field)) is not int or row[field] < 0:
                        raise ValueError('Linux B4 live resource metric unavailable')
                if not row.get('thread_ids'):
                    raise ValueError('Linux B4 thread evidence unavailable')
            prior = self.previous.get(role)
            now = (process.pid, row['start_ticks'], row['cpu_ns'], row['timestamp_ns'])
            if prior and (now[:2] != prior[:2] or now[2] < prior[2] or now[3] <= prior[3]):
                raise RuntimeError('Linux B4 process continuity failed')
            if row['memory_state'] == 'UNAVAILABLE_EXITING':
                if (prior is None or type(row.get('flags')) is not int or not row['flags'] & 4
                        or row.get('fd_count_state') != 'UNAVAILABLE_EXITING'
                        or any(row.get(key, 'missing') is not None for key in (
                            'fd_count', 'rss_bytes', 'pss_bytes', 'private_resident_bytes', 'private_hugetlb_bytes'))):
                    raise RuntimeError('unverified Linux B4 exit transition')
                self.exiting[role] = process
            elif role in self.exiting and row['memory_state'] != 'UNAVAILABLE_ZOMBIE':
                raise RuntimeError('Linux B4 exiting process returned live')
            self.previous[role] = now
            samples.append({**row, 'role': role, 'sample_round': self.round, 'platform': 'linux'})
        if not self.host or time.monotonic_ns() - self.host[-1]['timestamp_ns'] >= 1_000_000_000:
            if len(self.host) >= self.cap:
                raise RuntimeError('Linux B4 host cap exceeded')
            row = self.host_fn()
            if self.host:
                old = self.host[-1]
                if row['timestamp_ns'] <= old['timestamp_ns']:
                    raise RuntimeError('Linux host clock reversed')
                if 'cpu_jiffies' in row:
                    # Linux iowait can decrease; retain it raw without using it as monotonic CPU.
                    if any(row['cpu_jiffies'][k] < old['cpu_jiffies'][k] for k in row['cpu_jiffies'] if k != 'iowait'):
                        raise RuntimeError('Linux host CPU counter reset')
                    if row['context_switches_total'] < old['context_switches_total']:
                        raise RuntimeError('Linux context switch counter reset')
            self.host.append(row)

    def summarize(self, samples):
        if not samples:
            raise RuntimeError('Linux B4 resources missing')
        transitions = {}
        for role, process in self.exiting.items():
            code = process.poll()
            if process.pid != self.previous[role][0] or code is None:
                raise RuntimeError('Linux B4 exit transition not confirmed')
            transitions[role] = dict(pid=process.pid, start_ticks=self.previous[role][1],
                                     confirmed_exit_code=code,
                                     scope='owned Popen completion; partial sample is not final CPU/memory')
        roles = {r['role'] for r in samples}
        cpu = 0
        for role in roles:
            rows = [r for r in samples if r['role'] == role]
            if len(rows) < 2:
                raise RuntimeError('Linux B4 role has insufficient resource samples')
            cpu += rows[-1]['cpu_ns'] - rows[0]['cpu_ns']
        fields = ('rss_bytes', 'pss_bytes', 'private_resident_bytes', 'private_hugetlb_bytes', 'fd_count')
        rounds = [[r for r in samples if r['sample_round'] == n and r['memory_state'] == 'MEASURED']
                  for n in sorted({r['sample_round'] for r in samples})]
        return {'exit_transitions': transitions, 'cpu_seconds': cpu / 1e9, 'cpu_scope': 'sampled process intervals; terminal fragments may be missing',
                'memory_basis': 'linux_smaps_rollup; sequential samples in each round, not atomic peaks',
                **{'peak_' + k: max(sum(r[k] for r in rows) for rows in rounds) for k in fields},
                'peak_threads': max(sum(len(r['thread_ids']) for r in rows) for rows in rounds),
                'peak_processes': max(map(len, rounds))}

    def shard_cpu(self, mapping):
        return {'status': 'NOT_MEASURED', 'reason': 'non-Windows shard OS thread IDs are zero',
                'shards': sorted(mapping)}

    def preserve(self, directory, samples, processes=None):
        for name, rows in [('linux-resources.ndjson', samples), ('linux-host.ndjson', self.host)]:
            (directory / name).write_text(''.join(json.dumps(r, allow_nan=False) + '\n' for r in rows), encoding='utf-8')
        # Admission streams already have file-backed retention / the existing drain.
        # Preserve established-peer pipes after owned children have stopped.
        for role, process in (processes or {}).items():
            if role.startswith('established-') and process.poll() is not None:
                try:
                    stdout, stderr = process.communicate(timeout=1)
                    for name, value in [('stdout', stdout), ('stderr', stderr)]:
                        if value is not None:
                            (directory / f'{role}.{name}').write_text(value, encoding='utf-8')
                except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                    self.capture_valid = False
                    (directory / f'{role}.capture-error.json').write_text(
                        json.dumps({'error_type': type(error).__name__}), encoding='utf-8')

    def measure(self, run, args, kwargs, counter_path):
        from scripts.run_b4b_v2 import valid_record
        duration, warmup = kwargs['duration'], kwargs['warmup']
        cap = math.ceil((duration + warmup + 120) / .1) * 4 + 16
        self.check_cancelled()
        child = LinuxB4Backend(self.cpus, self.taskset, sample_fn=self.sample_fn, host_fn=self.host_fn, max_records=cap,
                              check_cancelled=self.check_cancelled)
        if self.verify_execution is not None:
            self.verify_execution()
        started = time.monotonic()
        record = run(*args, **kwargs, backend=child)
        record['observed_elapsed_seconds'] = time.monotonic() - started
        expected = {'established-source', 'established-destination'}
        if args[0]:
            expected |= {'admission-source', 'admission-destination'}
        roles = {r['role'] for r in record['resource_samples']}
        record['resource_capture'] = {'valid': roles == expected and len(child.host) >= 2 and child.capture_valid,
                                      'expected_roles': sorted(expected), 'observed_roles': sorted(roles)}
        record['host_counters'] = {'status': 'MEASURED' if len(child.host) >= 2 else 'UNAVAILABLE',
                                    'platform': 'linux', 'samples': len(child.host),
                                    'scope': 'whole-host proc counters, not Windows queue/commit aliases'}
        record['admission_rate'] = record['successful_admissions'] / record['admission_elapsed_seconds']
        record['effective_cores'] = record['resources']['cpu_seconds'] / record['observed_elapsed_seconds']
        record['valid'] = valid_record(record) and record['resource_capture']['valid']
        return record
