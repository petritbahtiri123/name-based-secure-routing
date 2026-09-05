"""Bounded ETW network observation; TCP/IP receive is not socket delivery."""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_b4b_task4k import checksums


def network_flows(rows, source_pid, destination_pid, server_port):
    flows = collections.defaultdict(lambda: {"send": [], "receive": [], "reply": []})
    for row in rows:
        if len(row) != 8 or row[0] not in ("UdpSend", "UdpRecv") or not row[1].isdigit():
            continue
        match = re.search(r"\(\s*(\d+)\)", row[2])
        if not match:
            continue
        pid, remote, local = int(match[1]), int(row[5]), int(row[7])
        if remote == server_port and pid == source_pid and row[0] == "UdpSend":
            flows[local]["send"].append(int(row[1]))
        elif remote == server_port and pid == destination_pid and row[0] == "UdpRecv":
            flows[local]["receive"].append(int(row[1]))
        elif local == server_port and pid == destination_pid and row[0] == "UdpSend":
            flows[remote]["reply"].append(int(row[1]))
    result = []
    for port, events in sorted(flows.items()):
        if not events["send"]:
            continue
        start = min(events["send"])
        receive = min(events["receive"], default=None)
        reply = min(events["reply"], default=None)
        if any(t is not None and t < start for t in (receive, reply)):
            raise ValueError("window does not contain first outbound or port was reused")
        result.append({"client_port": port, "first_send_us": start,
                       "first_tcpip_receive_delay_us": receive - start if receive is not None else None,
                       "first_reply_delay_us": reply - start if reply is not None else None,
                       "first_source_send_times_us": events["send"][:4],
                       "socket_delivery": "NOT MEASURED", "quic_retransmission": "NOT ESTABLISHED"})
    return result


def gap_progress(rows, pid, begin, end):
    last_in, last_out = {}, {}
    cpu, switches, max_off = collections.Counter(), collections.Counter(), collections.Counter()
    sends = receives = 0
    for row in rows:
        if len(row) < 3 or not row[1].isdigit():
            continue
        stamp, kind = int(row[1]), row[0]
        if kind == "CSwitch" and len(row) >= 10:
            if f"({pid})" in row[8]:
                tid = int(row[9])
                start = last_in.pop(tid, None)
                if start is not None:
                    cpu[tid] += max(0, min(stamp, end) - max(start, begin))
                last_out[tid] = stamp
            if f"({pid})" in row[2]:
                tid = int(row[3])
                last_in[tid] = stamp
                out = last_out.pop(tid, None)
                if begin <= stamp <= end:
                    switches[tid] += 1
                    if out is not None:
                        max_off[tid] = max(max_off[tid], stamp - max(out, begin))
        if begin <= stamp <= end and f"({pid})" in row[2]:
            sends += kind == "UdpSend"
            receives += kind == "UdpRecv"
    return {"begin_us": begin, "end_us": end, "matched_cpu_us_by_tid": dict(cpu),
            "switch_ins_by_tid": dict(switches), "max_matched_off_cpu_us_by_tid": dict(max_off),
            "udp_sends": sends, "udp_receives": receives,
            "limitation": "matched CSwitch intervals only; incomplete boundary intervals not imputed"}


def analyze(capture: Path, output: Path):
    if output.exists():
        raise FileExistsError(output)
    workload = json.loads((capture / "etw/analysis.json").read_text())
    result = {"classification": "PARTIAL / UNRESOLVED:socket-delivery-to-first-reply",
              "claim_class": "DIAGNOSTIC", "selected_windows": [],
              "limitations": ["Both ETW observer gates failed; no transferred causal timing",
                              "Only first repeat per rate exported; not whole-trace flow statistics",
                              "TCP/IP receive does not establish socket enqueue or application read",
                              "No AFD drop events captured; no socket-loss or buffer-limit claim",
                              "Timer events were not decoded by installed xperf; no timer-causality claim"]}
    for rate in ("200", "250"):
        record = workload["records"][rate]["etw"][0]
        pids = {r["role"]: r["pid"] for r in record["resource_samples"]}
        command = record["commands"]["admission_clients"][0]
        port = int(command[command.index("--endpoint") + 1].split(":")[-1])
        path = capture / f"window-{rate}-r1-us.csv"
        with path.open() as stream:
            flows = network_flows(csv.reader(stream, skipinitialspace=True),
                                  pids["admission-source"], pids["admission-destination"], port)
        slow = max((flow for flow in flows if flow["first_reply_delay_us"] is not None),
                   key=lambda flow: flow["first_reply_delay_us"])
        with path.open() as stream:
            progress = gap_progress(csv.reader(stream, skipinitialspace=True), pids["admission-destination"],
                                    slow["first_send_us"], slow["first_send_us"] + slow["first_reply_delay_us"])
        result["selected_windows"].append({"offered_rate": int(rate), "repeat": 1,
                                            "source_pid": pids["admission-source"],
                                            "destination_pid": pids["admission-destination"],
                                            "server_port": port, "flow_count": len(flows), "flows": flows,
                                            "longest_reply_gap_progress": progress})
    output.mkdir(parents=True)
    (output / "analysis.json").write_text(json.dumps(result, indent=2) + "\n", newline="\n")
    inputs = [capture / name for name in ("metadata.json", "observer-comparison.json", "trace-stats.txt",
                                         "etw/analysis.json", "none/analysis.json", "kernel.etl",
                                         "etw/environment.json", "none/environment.json",
                                         "etw/checksums.sha256", "none/checksums.sha256",
                                         "window-200-r1-us.csv", "window-250-r1-us.csv",
                                         "profile-250-r1.txt")]
    entries = []
    for path in inputs:
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        entries.append({"path": str(path), "bytes": path.stat().st_size, "sha256": digest})
    (output / "external-inputs.json").write_text(json.dumps(entries, indent=2) + "\n", newline="\n")
    checksums(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.capture, args.output)
