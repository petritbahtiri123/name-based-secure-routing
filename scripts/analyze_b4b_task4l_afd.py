"""Map AFD drop events to recorded socket binds; never infer from execution PID."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path


def map_drops(rows, cells):
    cells = [{**c, "drops": Counter(), "sizes": Counter(), "reasons": Counter(),
              "peers": set(), "owner_pids": set()} for c in cells]
    state = {}
    unmatched = 0
    counts = Counter()
    for event in rows:
        counts[event["id"]] += 1
        data = event["data"]
        key = (data["Process"], data["Endpoint"])
        if event["id"] == 1000 and data["EnterExit"] == "0":
            state[key] = {"owner_pid": int(data["ProcessId"], 16)}
        if event["id"] == 1030 and data["EnterExit"] == "1" and data["Status"] == "0":
            address = bytes.fromhex(data["Address"])
            if len(address) >= 4 and int.from_bytes(address[:2], "little") in (2, 23):
                state.setdefault(key, {})["port"] = int.from_bytes(address[2:4], "big")
        if event["id"] != 1033:
            continue
        stamp = datetime.fromisoformat(event["utc"]).timestamp()
        matches = [c for c in cells if c["start"] <= stamp <= c["end"]]
        if len(matches) > 1:
            raise ValueError("overlapping run windows")
        if not matches:
            unmatched += 1
            continue
        cell = matches[0]
        socket = state.get(key, {})
        port = socket.get("port")
        role = ("admission_destination" if port == cell["admission_port"] else
                "established_destination" if port == cell["established_port"] else
                "other_or_unmapped")
        cell["drops"][role] += 1
        cell["reasons"][data["Reason"]] += 1
        if role == "admission_destination":
            cell["sizes"][data["BufferLength"]] += 1
            cell["peers"].add(data["Address"])
            if "owner_pid" in socket:
                cell["owner_pids"].add(socket["owner_pid"])
    for cell in cells:
        cell["peers"] = len(cell["peers"])
        cell["owner_pids"] = sorted(cell["owner_pids"])
    return {"event_counts": counts, "unmatched_window_drops": unmatched, "cells": cells}


def analyze(root):
    analysis = json.loads((root / "etw/analysis.json").read_text())
    comparison = json.loads((root / "observer-comparison.json").read_text())
    cells = []
    for rate, modes in analysis["records"].items():
        for record in modes["etw"]:
            def port(command):
                return int(command[command.index("--endpoint") + 1].rsplit(":", 1)[1])
            cells.append({"rate": rate, "repeat": record["repeat"],
                          "start": record["started_unix_ns"] / 1e9,
                          "end": record["ended_unix_ns"] / 1e9,
                          "admission_port": port(record["commands"]["admission_clients"][0]),
                          "established_port": port(record["commands"]["established_client"]),
                          "admissions_s": record["admission_rate"]})
    with (root / "afd-events.jsonl").open() as stream:
        result = map_drops((json.loads(line) for line in stream), cells)
    result.update(classification="DIAGNOSTIC; socket drops do not establish hardware capacity",
                  timing_comparable=comparison["timing_comparable"],
                  limitation="Capture block order and observer gate limit transfer to unobserved runs")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = analyze(args.root)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
