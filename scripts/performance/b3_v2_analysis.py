"""Per-process B3 analysis: ownership and OS memory are separate evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics


def slope(points):
    if len(points) < 2:
        return None
    mx = statistics.fmean(x for x, _ in points)
    my = statistics.fmean(y for _, y in points)
    denominator = sum((x - mx) ** 2 for x, _ in points)
    return sum((x - mx) * (y - my) for x, y in points) / denominator if denominator else None


def analyze_cycles(cell):
    cleanup = cell.get("cleanup", {})
    if any(type(cleanup.get(key)) is not bool for key in ("all_zero", "source_cycle_all_zero")):
        raise ValueError("incomplete ownership evidence")
    expected = list(range(cell["cycles"]))
    roles = {}
    for role in ("source", "destination"):
        samples = [s for s in cell["samples"] if s["role"] == role and s["phase"] == "cooldown"]
        if sorted({s["cycle"] for s in samples}) != expected:
            raise ValueError(f"{role}: incomplete same-process cooldown series")
        if any(s.get("process_count", 1) != 1 for s in samples):
            raise ValueError("cycle samples must represent exactly one process per role")
        points = []
        for cycle in expected:
            rows = [s for s in samples if s["cycle"] == cycle]
            points.append({"cycle": cycle, **{
                field: statistics.median(s[field] for s in rows)
                for field in ("private_bytes", "working_set_bytes", "handle_count", "thread_count")
            }})
        private = [(p["cycle"], p["private_bytes"]) for p in points]
        tail = private[len(private) // 2:]
        roles[role] = {"cycle_medians": points,
                       "private_slope_bytes_per_cycle": slope(private),
                       "second_half_private_slope_bytes_per_cycle": slope(tail),
                       "private_first_to_last_delta": private[-1][1] - private[0][1],
                       "handle_first_to_last_delta": points[-1]["handle_count"] - points[0]["handle_count"],
                       "thread_first_to_last_delta": points[-1]["thread_count"] - points[0]["thread_count"]}
    clean = cleanup["all_zero"] and cleanup["source_cycle_all_zero"]
    return {"name": cell["name"], "cycles": cell["cycles"],
            "materialized_streams": cell.get("materialized_streams", False),
            "ownership": "CLEAN" if clean else "RESOURCE_GROWTH",
            "memory_cause": "INCONCLUSIVE", "roles": roles,
            "limitation": "OS private bytes include runtime, allocator and retained harness results; slopes alone prove neither leaks nor allocator attribution."}


def analyze_scale(cells):
    result = []
    for kind in sorted({c["kind"] for c in cells}):
        selected = [c for c in cells if c["kind"] == kind]
        residency = {c.get("materialized_streams", False) for c in selected}
        if len(residency) != 1:
            raise ValueError("different stream residency workloads must be analyzed separately")
        for role in ("source", "destination"):
            points = []
            for count in sorted({c["active_count"] for c in selected}):
                rows = []
                for cell in selected:
                    if cell["active_count"] != count:
                        continue
                    if not cell["cleanup"].get("all_zero"):
                        raise ValueError("failed cleanup cannot enter valid scale analysis")
                    phases = {}
                    for phase in ("idle", "active"):
                        samples = [s for s in cell["samples"] if s["role"] == role and s["phase"] == phase]
                        if not samples:
                            raise ValueError(f"missing {role} {phase} samples")
                        phases[phase] = {f: statistics.median(s[f] for s in samples)
                                         for f in ("private_bytes", "working_set_bytes", "handle_count", "thread_count")}
                    rows.append({"name": cell["name"], **phases,
                                 "incremental_private_bytes": phases["active"]["private_bytes"] - phases["idle"]["private_bytes"]})
                values = [r["active"]["private_bytes"] for r in rows]
                mean = statistics.fmean(values)
                cv = statistics.stdev(values) / mean * 100 if len(values) > 1 and mean else None
                points.append({"count": count, "repeats": len(rows), "active_private_cv_percent": cv,
                               "repeat_gate": len(rows) >= (5 if cv is not None and cv > 5 else 3),
                               "active_private_median": statistics.median(values),
                               "active_private_range": [min(values), max(values)],
                               "incremental_private_median": statistics.median(r["incremental_private_bytes"] for r in rows),
                               "rows": rows})
            result.append({"kind": kind, "role": role, "points": points,
                           "materialized_streams": selected[0].get("materialized_streams", False),
                           "derived_active_private_slope_bytes_per_unit": slope([(p["count"], p["active_private_median"]) for p in points]),
                           "derived_incremental_private_slope_bytes_per_unit": slope([(p["count"], p["incremental_private_median"]) for p in points]),
                           "resource_scope": selected[0]["resource_scope"]})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("roots", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cells = [c for root in args.roots for c in json.loads((root / "records.json").read_text())]
    document = {"schema": "nbsr-b3-v2-analysis-v1",
                "inputs": [str(root) for root in args.roots],
                "cycles": [analyze_cycles(c) for c in cells if c["kind"] == "cycles"],
                "scale": analyze_scale([c for c in cells if c["kind"] != "cycles"])}
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(document, output, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
