"""Bounded read-only NIC inventory; never a hardware-ceiling qualification."""

import argparse
import json
from pathlib import Path
import platform
import re
import subprocess
import time

from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.linux_b5_reference import git_state


COUNTERS = ('rx_bytes', 'tx_bytes', 'rx_packets', 'tx_packets',
            'rx_dropped', 'tx_dropped', 'rx_errors', 'tx_errors')


def read_value(path, *, numeric=False):
    try:
        with path.open() as stream:
            text = stream.read(65537).strip()
        if len(text) > 65536:
            raise ValueError('field exceeds inventory bound')
        value = int(text) if numeric else text
        if numeric and value < 0:
            raise ValueError('negative counter/value')
        return dict(status='MEASURED', value=value)
    except PermissionError as error:
        return dict(status='ADMIN_REQUIRED', value=None, error=str(error))
    except OSError as error:
        return dict(status='UNAVAILABLE', value=None, error=str(error))
    except ValueError as error:
        return dict(status='INVALID', value=None, error=str(error))


def run_command(argv):
    result = dict(argv=argv, status='UNAVAILABLE', returncode=None, stdout='', stderr='')
    try:
        process = subprocess.run(argv, capture_output=True, text=True, timeout=5, check=False)
        result.update(returncode=process.returncode, stdout=process.stdout, stderr=process.stderr)
        # ethtool can return zero while a netlink subquery was denied.
        # Preserve partial stdout, but never silently qualify the whole query.
        if any(s in process.stderr.lower() for s in ('operation not permitted', 'permission denied')):
            result['status'] = 'ADMIN_REQUIRED'
        elif process.returncode == 0:
            result['status'] = 'MEASURED'
        elif argv == ['systemd-detect-virt'] and process.returncode == 1 and process.stdout.strip() == 'none':
            result['status'] = 'MEASURED_NO_VIRTUALIZATION_REPORTED'
        else:
            result['status'] = 'UNAVAILABLE'
    except FileNotFoundError as error:
        result.update(status='TOOL_UNAVAILABLE', stderr=str(error))
    except PermissionError as error:
        result.update(status='ADMIN_REQUIRED', stderr=str(error))
    except subprocess.TimeoutExpired as error:
        result.update(status='TIMED_OUT', stderr=str(error))
    except OSError as error:
        result.update(status='UNAVAILABLE', stderr=str(error))
    return result


def collect_network(interface, *, sys_root=Path('/sys'), proc_root=Path('/proc'), runner=run_command):
    require(re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_.:-]{0,14}', interface)
            and interface not in ('.', '..'), 'invalid Linux interface name')
    net = sys_root / 'class/net' / interface
    require(net.is_dir(), 'requested interface does not exist')
    started = time.monotonic_ns()
    fields = {name: read_value(net / name, numeric=name in ('type', 'mtu', 'carrier', 'speed'))
              for name in ('type', 'mtu', 'operstate', 'carrier', 'speed', 'duplex')}
    stats = {name: read_value(net / 'statistics' / name, numeric=True) for name in COUNTERS}
    irq = {}
    device = net / 'device'
    try:
        # MSI IRQ lists are bounded; never enumerate unrelated /proc/irq entries.
        entries = list((device / 'msi_irqs').iterdir()) if (device / 'msi_irqs').is_dir() else []
        require(len(entries) <= 4096, 'unbounded MSI IRQ inventory')
        for entry in sorted(entries):
            if entry.name.isdecimal():
                irq[entry.name] = read_value(proc_root / 'irq' / entry.name / 'smp_affinity_list')
        if not entries and (device / 'irq').exists():
            legacy = read_value(device / 'irq', numeric=True)
            if legacy['status'] == 'MEASURED' and legacy['value'] > 0:
                irq[str(legacy['value'])] = read_value(proc_root / 'irq' / str(legacy['value']) / 'smp_affinity_list')
    except OSError as error:
        irq = {'unavailable': dict(status='UNAVAILABLE', value=None, error=str(error))}
    try:
        queues = sorted(p.name for p in (net / 'queues').iterdir() if re.fullmatch('(rx|tx)-[0-9]+', p.name))
        require(len(queues) <= 8192, 'unbounded queue inventory')
    except OSError:
        queues = None
    commands = [runner(['ethtool', *options, interface])
                for options in ([], ['-i'], ['-l'], ['-g'], ['-k'], ['-x'])]
    commands.append(runner(['systemd-detect-virt']))
    return dict(schema='nbsr-linux-network-inventory-v1', interface=interface,
        started_monotonic_ns=started, completed_monotonic_ns=time.monotonic_ns(),
        fields=fields, statistics=stats, queues=queues, irq_affinity=irq, commands=commands,
        device_classification='DEVICE_BACKING_REPORTED' if device.is_dir() else 'NO_DEVICE_BACKING_REPORTED',
        external_hardware='NOT_PROVEN', hardware_ceiling='NOT_PROVEN', dedicated_data_path='NOT_PROVEN',
        scope='interface-wide single snapshot; not process traffic, wire accounting, rate, saturation or bare-metal attestation')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interface', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(platform.system() == 'Linux', 'Linux procfs/sysfs required')
    sha, dirty = git_state()
    require(not dirty, 'clean source checkout required')
    require(not args.output.exists(), 'new output directory required')
    result = collect_network(args.interface)
    result['source_sha'] = sha
    result['kernel'] = dict(system=platform.system(), release=platform.release(), machine=platform.machine())
    require(git_state() == (sha, ''), 'source changed during inventory')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'inventory.json').write_text(json.dumps(result, indent=2) + '\n')
    seal_output(args.output)
    print(json.dumps(dict(output=str(args.output), external_hardware='NOT_PROVEN')))


if __name__ == '__main__':
    main()
