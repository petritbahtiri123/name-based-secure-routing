"""Retain shared-guest-core failure; never infer a production ceiling."""

import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
from scripts.performance.linux_native_pair import verify_index
from scripts.performance.linux_loopback import digest

root = Path(sys.argv[1])
verify_index(root)
records = json.loads((root / "records.json").read_bytes())
assert len(records) == 1
record = records[0]
assert (record["label"], record["count"], record["repeat"], record["status"]) == ("n2048-r1", 2048, 1, "FAIL_RETAINED")
cell = root / record["label"]
verify_index(cell)
config = json.loads((cell / "config.json").read_bytes())
sha = "1c103518a4a6cb63ef36869401565c224825c9b9"
assert config["source_sha"] == sha and config["count"] == 2048 and config["rate"] == 100 and config["shards"] == 2
assert config["memory_observer"] is True and config["bundle_mode"] == "live-bundles"
samples = {}
roles = {}
for role in ("source", "destination"):
    peer = cell / role / "peer"
    verify_index(cell / role)
    verify_index(peer)
    env = json.loads((peer / "environment.json").read_bytes())
    build = json.loads((peer / "build-manifest.json").read_bytes())
    name = "perf_rust_source" if role == "source" else "wp8_interop_server"
    assert env["repository_sha"] == build["source_sha"] == sha and env["bundle_mode"] == "live-bundles"
    assert env["count"] == 2048 and env["offered_rate"] == 100 and env["source_shards"] == 2
    assert env["linux_environment"]["selected_cpus"] == [0] and build["build_profile"] == "release"
    assert digest(peer / "executed-binary") == build["binary_sha256"][name] == env["binary_sha256"][name]
    values = [json.loads(line) for line in (peer / "resources.ndjson").read_text(encoding="utf-8").splitlines()]
    pid = json.loads((peer / "pid.json").read_bytes())["pid"]
    assert len(values) > 2 and len({v["start_ticks"] for v in values}) == 1
    assert all(v["pid"] == pid and v["affinity"] == [0] for v in values)
    assert all(b["timestamp_ns"] > a["timestamp_ns"] and b["cpu_ns"] >= a["cpu_ns"] for a, b in zip(values, values[1:]))
    samples[role] = values
    roles[role] = dict(
        samples=len(values),
        peak_rss_bytes=max(v["rss_bytes"] for v in values),
        forced_cleanup=json.loads((peer / "forced-cleanup.json").read_bytes()),
        failure_udp=json.loads((peer / "failure-udp.json").read_bytes()),
        events=[json.loads(line)["event"] for line in (cell / role / "events.ndjson").read_text(encoding="utf-8").splitlines()],
    )
    assert roles[role]["forced_cleanup"]["group_killed"] is True
end = min(v[-1]["timestamp_ns"] for v in samples.values())
windows = {}
for seconds in (1, 2, 5, 10):
    start = end - seconds * 10**9
    cpu = {}
    bounds = {}
    for role, values in samples.items():
        contained = [v for v in values if start <= v["timestamp_ns"] <= end]
        assert len(contained) > 1
        cpu[role] = contained[-1]["cpu_ns"] - contained[0]["cpu_ns"]
        bounds[role] = [contained[0]["timestamp_ns"], contained[-1]["timestamp_ns"]]
    windows[str(seconds)] = dict(
        window_start_ns=start,
        window_end_ns=end,
        fully_contained_sample_bounds=bounds,
        cpu_ns=cpu,
        shared_guest_cpu_fraction_estimate=sum(cpu.values()) / (seconds * 10**9),
    )
rows = [json.loads(line) for line in (cell / "source/peer/stdout").read_text(encoding="utf-8").splitlines()]
failed = [r for r in rows if r.get("success") is False]
assert len({r["logical_client_id"] for r in failed}) == len(failed)
assert record["owned_processes_absent_before_stop"] == {"source": True, "destination": True}
print(
    json.dumps(
        dict(
            classification="FAILED_PARTIAL_SHARED_GUEST_CORE_PRESSURE",
            requested=2048,
            source_materialized_observation_rows=sum(r.get("phase") == "b3_materialized_streams_ready" for r in rows),
            source_errors=dict(Counter(r["error"] for r in failed)),
            source_recorded_successes=sum(r.get("success") is True for r in rows),
            final_ownership="NOT_MEASURED: cancelled after failure",
            owned_processes_absent_before_stop=record["owned_processes_absent_before_stop"],
            shared_cpu_windows=windows,
            roles=roles,
            cpu_basis="DERIVED contained-sample estimates using tick-quantized process CPU deltas on common Docker/WSL monotonic clock; both roles pinned guestCPU0; excludes observer/kernel work outside owned processes",
            attribution="Shared allocated guestCPU pressure is measured; cumulative destination socket drops lack event timing. No claim every timeout is caused by CPU or drops.",
            limits="One failed diagnostic; no repeatable boundary, throughput/admission ceiling, physical-core/server proof, memory pressure proof or production optimization claim",
        ),
        indent=2,
    )
)
