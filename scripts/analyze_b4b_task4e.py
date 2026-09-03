"""Conservative Task 4e extraction; never auto-promotes hotspots to causality."""
from __future__ import annotations

import argparse
import collections
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.analyze_b4b_task4c import (
    CSWITCH_ROW, handshake_percentiles, parse_profile_rows, role_pid, role_resources, sha256,
)


def scheduling(lines, tids):
    result = {tid: dict(switch_out_count=0, wait_us=0, ready_us=0,
                       unresolved_intervals=0, longest_off_cpu_us=0,
                       reasons={}, last_switch_out=None) for tid in tids}
    pending = {}
    wake = {}
    for row in csv.reader(lines, skipinitialspace=True):
        if len(row) < 2 or not row[1].strip().isdigit():
            continue
        time = int(row[1])
        if row[0] == "ReadyThread" and len(row) > 5:
            tid = int(row[5])
            if tid in pending:
                wake.setdefault(tid, time)
        elif row[0] == "CSwitch" and len(row) > 13:
            new, old = int(row[3]), int(row[9])
            if new in pending:
                start, state = pending.pop(new)
                ready = wake.pop(new, None)
                value = result[new]
                value["longest_off_cpu_us"] = max(value["longest_off_cpu_us"], time-start)
                if state in ("Ready", "DeferredReady"):
                    value["ready_us"] += time-start
                elif ready is not None and start <= ready <= time:
                    value["wait_us"] += ready-start
                    value["ready_us"] += time-ready
                else:
                    value["unresolved_intervals"] += 1
            if old in tids:
                value = result[old]
                value["switch_out_count"] += 1
                reason = row[13].strip()
                value["reasons"][reason] = value["reasons"].get(reason, 0)+1
                value["last_switch_out"] = dict(time_us=time, state=row[12], reason=reason)
                pending[old] = (time, row[12])
                wake.pop(old, None)
    for tid in tids:
        result[tid]["open_interval_at_end"] = tid in pending
    return result


def analyze(capture, output):
    if output.exists():
        raise FileExistsError(output)
    metadata = json.loads((capture / "metadata.json").read_text(encoding="utf-8-sig"))
    manifests = {k: json.loads((capture/k/"manifest.json").read_text()) for k in ("control", "profiled")}
    rows = parse_profile_rows((capture/"cpu-profile-detail.txt").read_text(errors="replace"))
    cpu = collections.defaultdict(list)
    for line in (capture/"cswitch-process-thread.txt").read_text().splitlines():
        match = CSWITCH_ROW.match(line)
        if match:
            cpu[int(match[2])].append((int(match[1]), int(match[3])))
    cells, tids = [], set()
    for record in manifests["profiled"]["records"]:
        clients = record["clients"]
        cell = {"clients": clients, "roles": {}}
        for kind in ("control", "profiled"):
            r = next(r for r in manifests[kind]["records"] if r["clients"] == clients)
            path = capture/kind/"raw"/f"clients-{clients}-connections-1-r1"/"admission-source.stdout"
            cell[kind] = {key: r.get(key) for key in (
                "successful_admissions", "errors", "timeouts", "admission_elapsed_seconds",
                "failure_detail", "cleanup", "admission_p99_latency_ns",
            )}
            cell[kind]["handshake"] = handshake_percentiles(path.read_text())
            cell[kind]["admissions_per_second"] = r["successful_admissions"]/r["admission_elapsed_seconds"]
        for role in ("admission-source", "admission-destination"):
            pid = role_pid(record, role)
            cpu_us, tid = max(cpu[pid])
            tids.add(tid)
            weights = rows.get(pid, [])
            total = sum(w for w, _ in weights)
            cell["roles"][role] = dict(
                pid=pid, highest_cpu_thread=tid, thread_cpu_us=cpu_us,
                resources=role_resources(record, role),
                hotspots=[dict(weight=w, fraction=w/total, function=f)
                          for w, f in sorted(weights, reverse=True)[:20]],
            )
        cell["observer_overhead_fraction"] = 1-cell["profiled"]["admissions_per_second"]/cell["control"]["admissions_per_second"]
        cells.append(cell)
    with (capture/"kernel-events.csv").open(errors="replace") as stream:
        schedule = scheduling(stream, tids)
    for cell in cells:
        for role in cell["roles"].values():
            role["scheduling"] = schedule[role["highest_cpu_thread"]]
    output.mkdir(parents=True)
    result = dict(classification="PARTIAL / UNRESOLVED", metadata=metadata, cells=cells,
                  limitations=["One control/profile pair; not capacity evidence",
                               "Missing wakeups remain unresolved, not imputed",
                               "CPU summary units are microseconds, not context-switch counts",
                               "Hotspot association alone does not establish handshake causality"])
    (output/"analysis.json").write_text(json.dumps(result, indent=2)+"\n")
    files = [p for p in capture.rglob("*") if p.is_file()]
    external = dict(capture_root=str(capture), files={str(p.relative_to(capture)): dict(
        bytes=p.stat().st_size, sha256=sha256(p)) for p in files})
    (output/"external-trace-manifest.json").write_text(json.dumps(external, indent=2)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.capture, args.output)
