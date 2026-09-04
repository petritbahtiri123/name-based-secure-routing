from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_b4b_task4i import RATES, ownership_high_water, summarize
from scripts.run_b4b_v2 import write_json


def analyze(root: Path) -> dict:
    prior = json.loads((root / "analysis.json").read_text(encoding="utf-8"))
    rebuilt=[]
    for rate in RATES:
        paths=sorted((root / "raw" / f"rate-{rate}").glob("r*.json"))
        if not paths:
            continue
        records=[json.loads(path.read_text(encoding="utf-8")) for path in paths if "-host" not in path.name]
        rebuilt.append(summarize(rate,records,None if not rebuilt else rebuilt[0]))
    analysis={**prior,"cells":rebuilt,"classification":"PASS" if any(c["status"]=="STABLE" for c in rebuilt) and any(c["status"]=="SATURATED" for c in rebuilt) else "PARTIAL"}
    write_json(root / "analysis.json", analysis)
    cells = []
    for cell in analysis["cells"]:
        rate = int(cell["offered_rate"])
        records = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((root / "raw" / f"rate-{rate}").glob("r*.json"))
            if "-host" not in path.name
        ]
        ownership = []
        for path in sorted((root / "raw" / f"rate-{rate}").glob("*/lifecycle-diagnostics.ndjson")):
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
            ownership.append(ownership_high_water(rows))
        high_water_keys = {key for row in ownership for key in row}
        cells.append({
            "offered_rate": rate,
            "status": cell["status"],
            "host_counters_median": {
                key: statistics.median(float(record["host_counters"][key]) for record in records)
                for key in records[0]["host_counters"]
                if isinstance(records[0]["host_counters"][key], (int, float))
            },
            "destination_cleanup_seconds_median": statistics.median(
                float(record["destination_cleanup_wait_seconds"]) for record in records
            ),
            "ownership_high_water_median": {
                key: statistics.median(row.get(key, 0) for row in ownership)
                for key in sorted(high_water_keys)
            },
        })
    result = {"schema": "nbsr-b4b-task4i-telemetry-v1", "cells": cells}
    write_json(root / "telemetry-summary.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.root)
