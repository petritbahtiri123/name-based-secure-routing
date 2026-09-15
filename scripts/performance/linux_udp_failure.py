"""Bounded, failure-only UDP queue observations for already owned Linux peers."""

import os
from pathlib import Path
import re
import time

from scripts.performance.linux_loopback import parse_proc_stat


def read_bounded(path, limit=8 * 1024 * 1024):
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("proc observation bound exceeded")
    return data.decode("ascii")


def parse_udp(text, inodes, *, family):
    lines = text.splitlines()
    remote = {"udp": "rem_address", "udp6": "remote_address"}.get(family)
    if (
        not lines
        or remote is None
        or lines[0].split()[:3] != ["sl", "local_address", remote]
        or lines[0].split()[-1] != "drops"
        or len(lines) > 8193
    ):
        raise ValueError("unrecognized UDP table")
    result, seen = [], set()
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 13 or not parts[9].isdigit() or not parts[12].isdigit():
            raise ValueError("invalid UDP row")
        inode, drops = int(parts[9]), int(parts[12])
        if inode in seen or not 0 <= drops < 2**64:
            raise ValueError("duplicate inode or invalid drops")
        seen.add(inode)
        if inode not in inodes:
            continue
        if not re.fullmatch(r"[0-9A-Fa-f]{8}:[0-9A-Fa-f]{8}", parts[4]):
            raise ValueError("invalid UDP queues")
        tx, rx = (int(value, 16) for value in parts[4].split(":"))
        result.append(
            dict(
                family=family,
                inode=inode,
                local_address=parts[1],
                remote_address=parts[2],
                tx_queue_bytes=tx,
                rx_queue_bytes=rx,
                drops=drops,
            )
        )
    return result


def capture_owned_udp(processes, expected_starts, *, proc_root=Path("/proc")):
    result = dict(
        schema="nbsr-linux-udp-failure-v1",
        timestamp_ns=time.monotonic_ns(),
        scope="After workload failure, before cleanup; live socket cumulative counters only. "
        "Closed sockets and precise drop timestamps are not observed.",
        roles={},
    )
    if len(processes) > 64:
        return {**result, "status": "UNAVAILABLE", "reason": "process bound exceeded"}
    for role, process in processes.items():
        try:
            pid = process.pid
            if pid not in expected_starts or process.poll() is not None:
                raise ValueError("missing prior owned live identity")
            base = proc_root / str(pid)

            def identity():
                text = read_bounded(base / "stat", 65536)
                value = parse_proc_stat(text, 1, 1)
                if int(text.split(" ", 1)[0]) != pid or value["start_ticks"] != expected_starts[pid]:
                    raise ValueError("process identity changed")
                return value

            initial = identity()
            inodes = set()
            for count, fd in enumerate((base / "fd").iterdir()):
                if count >= 8192:
                    raise ValueError("FD observation bound exceeded")
                try:
                    target = os.readlink(fd)
                except FileNotFoundError:
                    continue
                match = re.fullmatch(r"socket:\[([0-9]+)\]", target)
                if match:
                    inodes.add(int(match[1]))
            rows = []
            for family in ("udp", "udp6"):
                rows.extend(parse_udp(read_bounded(base / "net" / family), inodes, family=family))
            final = identity()
            cpu_sample_monotonic_ns = time.monotonic_ns()
            if initial["state"] == "Z" or final["state"] == "Z" or final["flags"] & 4:
                raise ValueError("process exited during observation")
            result["roles"][role] = dict(
                status="MEASURED_FAILURE_SNAPSHOT",
                pid=pid,
                start_ticks=final["start_ticks"],
                # identity() parses with ticks=1; retain raw kernel ticks here.
                cpu_ticks=final["cpu_ns"] // 1_000_000_000,
                cpu_sample_monotonic_ns=cpu_sample_monotonic_ns,
                all_socket_inode_count=len(inodes),
                udp_socket_count=len(rows),
                live_socket_drops=sum(row["drops"] for row in rows),
                sockets=rows,
            )
        except (OSError, ValueError, RuntimeError) as error:
            result["roles"][role] = dict(status="UNAVAILABLE", pid=process.pid, error_type=type(error).__name__, error=str(error)[:256])
    return result
