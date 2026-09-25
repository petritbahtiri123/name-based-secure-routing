"""Scoped Go/Linux lifecycle evidence; source ownership is not instrumented."""

import argparse
import json
from pathlib import Path
import statistics

from scripts.performance.b3_linux_analysis import FIELDS, load_input
from scripts.run_b3_session_lifecycle import COUNTERS


def require(condition, message):
    if not condition:
        raise ValueError(message)


def analyze_cell(cell, cpus):
    cycles = cell["cycles"]
    require(
        type(cycles) is int and cycles > 0 and cell.get("sessions") == 1 and cell.get("kind") in ("cycles", "channels", "streams"),
        "unsupported Go shape",
    )
    require(
        cell.get("destination_completion") is True
        and cell.get("destination_completion_records") == list(range(cycles))
        and cell.get("completion_environment") == {"NBSR_PERF_LIFECYCLE_COMPLETION_MARKERS": "1"},
        "missing destination completion barrier",
    )
    cleanup = cell["cleanup"]
    require(
        all(cleanup.get(k) is True for k in ("all_zero", "source_processes_exited", "destination_exited"))
        and cleanup.get("counter_scope") == "historical-go-destination-8-fields"
        and set(cleanup.get("counters", {})) == set(COUNTERS)
        and all(type(v) is int and v == 0 for v in cleanup["counters"].values()),
        "invalid cleanup",
    )
    results = cell["client_results"]
    require(len(results) == 1 and results[0].get("status") == "PASS", "invalid source result")
    samples = results[0]["samples"]
    require(
        all(type(s.get("sample_id")) is int and s["sample_id"] == i for i, s in enumerate(samples)),
        "missing or duplicate operation identity",
    )
    require(
        len(samples) == cycles * cell["channels"] * cell["streams"]
        and all(s.get("success") is True and s.get("bytes_transmitted") == s.get("bytes_received") == 1024 for s in samples),
        "incomplete round trips",
    )
    previous, identities, exited = {}, {}, set()
    for row in cell["samples"]:
        role = row.get("role")
        require(
            row.get("phase") in ("idle", "active", "cooldown") and type(row.get("cycle")) is int and 0 <= row["cycle"] < cycles,
            "invalid phase or cycle",
        )
        require(
            role in ("source", "destination")
            and row.get("platform") == "linux"
            and row.get("memory_basis") == "linux_smaps_rollup"
            and row.get("process_count") == 1
            and len(row.get("processes", [])) == 1,
            "invalid process sample",
        )
        p = row["processes"][0]
        identity = (p.get("pid"), p.get("start_ticks"))
        require(all(type(v) is int and v >= 0 for v in identity) and identity[0] > 0, "invalid identity")
        require(role not in identities or identities[role] == identity, "changed identity")
        identities[role] = identity
        prior = previous.get(role)
        require(
            type(p.get("timestamp_ns")) is int
            and p["timestamp_ns"] > 0
            and row.get("timestamp_ns") == p["timestamp_ns"]
            and (prior is None or p["timestamp_ns"] > prior["timestamp_ns"]),
            "nonmonotonic clock",
        )
        if row.get("memory_state") == "UNAVAILABLE_EXPECTED_EXIT":
            require(
                role == "source"
                and row.get("phase") == "cooldown"
                and row.get("cycle") == cycles - 1
                and prior is not None
                and p.get("state") == "EXITED"
                and p.get("exit_code") == 0
                and p.get("memory_state") == "UNAVAILABLE_EXPECTED_EXIT"
                and all(row.get(f) is None and p.get(f) is None for f in (*FIELDS, "cpu_ns")),
                "invalid expected exit",
            )
            live = prior if role not in exited else prior["_last_live"]
            require(p.get("last_live_cpu_ns") == live["cpu_ns"] and p.get("last_live_timestamp_ns") == live["timestamp_ns"], "unbound exit")
            p = dict(p, _last_live=live)
            exited.add(role)
        else:
            require(
                role not in exited
                and row.get("memory_state") == p.get("memory_state") == "MEASURED"
                and p.get("state") not in ("Z", "EXITED")
                and p.get("affinity") == cpus,
                "invalid live sample",
            )
            for field in (*FIELDS, "cpu_ns"):
                value = len(p.get("thread_ids", [])) if field == "thread_count" else p.get(field)
                require(
                    type(value) is int and value >= 0 and type(row.get(field)) is int and row[field] == value, "invalid metric aggregate"
                )
            require(prior is None or p["cpu_ns"] >= prior["cpu_ns"], "decreasing CPU")
        previous[role] = p
    require(
        set(identities) == {"source", "destination"} and identities["source"][0] != identities["destination"][0],
        "missing or overlapping identities",
    )
    require(exited == {"source"}, "missing verified final source exit")
    roles = {}
    for role in ("source", "destination"):
        rows = [r for r in cell["samples"] if r["role"] == role]
        require(any(r["phase"] == "idle" and r["cycle"] == 0 for r in rows), "missing idle")
        for phase in ("active", "cooldown"):
            require(sorted({r["cycle"] for r in rows if r["phase"] == phase}) == list(range(cycles)), "missing phase")
        phases = {}
        for phase in ("idle", "active", "cooldown"):
            phases[phase] = []
            for cycle in sorted({r["cycle"] for r in rows if r["phase"] == phase}):
                selected = [r for r in rows if r["phase"] == phase and r["cycle"] == cycle]
                phases[phase].append(
                    dict(
                        cycle=cycle,
                        **{f: None if any(r[f] is None for r in selected) else statistics.median(r[f] for r in selected) for f in FIELDS},
                    )
                )
        roles[role] = phases
    return dict(
        name=cell["name"],
        roles=roles,
        source_ownership="NOT_MEASURED",
        destination_ownership="CLEAN_8_COUNTERS",
        memory_cause="INCONCLUSIVE",
        completed_operations=len(samples),
        classification="DIAGNOSTIC_SCOPED",
    )


def analyze_roots(roots):
    require(bool(roots) and len({str(Path(p).resolve()) for p in roots}) == len(roots), "duplicate roots")
    results, inputs, identity = [], [], None
    for root in roots:
        cells, current, provenance = load_input(root, "go-rust")
        require(identity is None or identity == current, "incompatible provenance")
        identity = current
        inputs.append(provenance)
        results.extend(analyze_cell(c, current["platform"]["selected_cpus"]) for c in cells)
    require(len({r["name"] for r in results}) == len(results), "duplicate cells")
    return dict(
        schema="nbsr-go-b3-linux-analysis-v1",
        classification="DIAGNOSTIC_SCOPED",
        inputs=inputs,
        cells=results,
        limitation="No source ownership, observer qualification, isolated cost or capacity claim.",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    document = analyze_roots(args.roots)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(document, output, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
