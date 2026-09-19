"""Bounded live owned-FD/IPv4 binding observation; not whole-flow exclusivity."""

import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import time

from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_loopback import parse_proc_stat
from scripts.performance.linux_udp_failure import parse_udp, read_bounded


def snapshot(pid, start_ticks, binary, address, *, proc_root=Path('/proc')):
    result = dict(schema='nbsr-linux-live-socket-v1', pid=pid, start_ticks=start_ticks,
                  binary=str(binary), started_ns=time.monotonic_ns(),
                  scope='Live FD binding during this observation only; not exclusive ownership, '
                        'whole-flow continuity, remote-peer identity or cleanup proof')
    try:
        require(type(pid) is int and pid > 0 and type(start_ticks) is int and start_ticks >= 0,
                'invalid owned identity')
        base = proc_root / str(pid)
        def identity():
            text = read_bounded(base / 'stat', 65536)
            value = parse_proc_stat(text, 1, 1)
            require(int(text.split(' ', 1)[0]) == pid and value['start_ticks'] == start_ticks
                    and value['state'] != 'Z' and not value['flags'] & 4, 'owned live identity changed')
            require(os.readlink(base / 'exe') == str(binary), 'owned executable changed')
            return os.readlink(base / 'ns' / 'net')
        namespace = identity()
        fds = {}
        for count, fd in enumerate((base / 'fd').iterdir()):
            require(count < 8192, 'FD observation bound exceeded')
            target = os.readlink(fd)
            match = re.fullmatch(r'socket:\[([0-9]+)\]', target)
            if match:
                fds[fd] = int(match[1])
        rows = parse_udp(read_bounded(base / 'net' / 'udp'), set(fds.values()), family='udp')
        sockets = []
        for row in rows:
            host, port = row['local_address'].split(':')
            require(len(host) == 8 and len(port) == 4, 'malformed IPv4 socket endpoint')
            local = str(ipaddress.IPv4Address(int(host, 16).to_bytes(4, sys.byteorder)))
            if local != address:
                continue
            for fd, inode in fds.items():
                if inode == row['inode']:
                    require(os.readlink(fd) == f'socket:[{inode}]', 'owned FD changed')
                    sockets.append(dict(fd=int(fd.name), inode=inode, local=[local, int(port, 16)]))
        require(sockets and namespace == identity(), 'no stable matching UDP binding')
        result.update(status='MEASURED_LIVE_SOCKET_SNAPSHOT', sockets=sockets, network_namespace=namespace)
    except (OSError, ValueError, RuntimeError) as error:
        result.update(status='UNAVAILABLE', error_type=type(error).__name__, error=str(error)[:256])
    result['finished_ns'] = time.monotonic_ns()
    return result


def validate_binding(value, *, pid, start_ticks, binary, local):
    require(value.get('schema') == 'nbsr-linux-live-socket-v1'
            and value.get('status') == 'MEASURED_LIVE_SOCKET_SNAPSHOT', 'live ownership unavailable')
    require(value['pid'] == pid and value['start_ticks'] == start_ticks
            and value['binary'] == str(binary), 'peer identity mismatch')
    require(value['finished_ns'] >= value['started_ns']
            and any(row['local'] == list(local) for row in value['sockets']), 'captured endpoint not owned')


def validate_history(value, text, *, resource_start_ns, resource_end_ns):
    """Validate the collector's bounded attempts against retained process time."""
    require(type(resource_start_ns) is int and type(resource_end_ns) is int
            and 0 <= resource_start_ns <= resource_end_ns, 'invalid resource time interval')
    lines = text.splitlines()
    require(1 <= len(lines) <= 20, 'socket observation history bound violated')
    previous_end = resource_start_ns
    for index, line in enumerate(lines):
        row = json.loads(line)
        require(isinstance(row, dict)
                and all(row.get(k) == value[k] for k in ('schema', 'pid', 'start_ticks', 'binary')),
                'socket observation history identity mismatch')
        start, end = row.get('started_ns'), row.get('finished_ns')
        require(type(start) is int and type(end) is int
                and previous_end <= start <= end <= resource_end_ns, 'socket observation time mismatch')
        previous_end = end
        if index == len(lines) - 1:
            require(row == value and row['status'] == 'MEASURED_LIVE_SOCKET_SNAPSHOT',
                    'socket observation report differs from terminal attempt')
        else:
            require(row.get('status') == 'UNAVAILABLE', 'observation continued after success')
