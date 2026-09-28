from pathlib import Path
import json
import statistics as st

root = Path("C:/NBSR-build/soak75-fd138398-20260926")
rows = json.loads((root / "records.json").read_text())
result = []
for i, row in enumerate(rows, 1):
    cell = root / f"nbsr-r{i}"

    def read(name):
        return [json.loads(line) for line in (cell / name).read_text().splitlines()]

    progress = [p for p in read("source.stdout.ndjson") if p.get("event") == "b5_grouped_progress" and p["phase"] == "steady"]
    third = max(1, len(progress) // 3)
    drift = {
        k: dict(early_median=st.median(p[k] for p in progress[:third]), late_median=st.median(p[k] for p in progress[-third:]))
        for k in ["goodput_bytes_per_second", "p99_latency_ns"]
    }
    for d in drift.values():
        d["fractional_change"] = d["late_median"] / d["early_median"] - 1
    resources = read("resources.ndjson")
    origin = row["qualification"].get("resource_phase_origin_monotonic_ns")
    memory = {}
    for role in ["source", "destination_0"]:
        r = [r for r in resources if r["role"] == role and (origin is None or r["monotonic_timestamp_ns"] >= origin)]
        memory[role] = {
            k: dict(first=r[0][k], last=r[-1][k], minimum=min(v[k] for v in r), maximum=max(v[k] for v in r))
            for k in ["private_bytes", "working_set_bytes", "thread_count", "handle_count"]
        }
        memory[role]["median_cpu_percent_one_core"] = st.median(v["cpu_percent_one_core"] for v in r)
    result.append(
        dict(
            repeat=i,
            record=row,
            observed_steady_seconds=progress[-1]["elapsed_ns"] / 1e9,
            windows=len(progress),
            last_observed_progress=progress[-1],
            thirds=drift,
            resource_diagnostics=memory,
        )
    )
print(
    json.dumps(
        dict(
            scope="Windows single-core 75% reference load. Window latency is sampled, not a pooled run percentile. Periodic ownership unqualified; no full B5 acceptance inferred. Failed-run counters cover observed progress only.",
            rows=result,
        ),
        indent=2,
    )
)
