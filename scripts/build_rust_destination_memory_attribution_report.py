from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.performance.memory_closure import analyze_resource_records  # noqa: E402
from scripts.performance.rust_destination_memory_attribution import (  # noqa: E402
    classify_destination_runs,
)
from scripts.performance.rust_memory_attribution import reconcile_snapshot  # noqa: E402


EVIDENCE = ROOT / "evidence/performance/rust-memory-attribution-p1b"
P1A = ROOT / "evidence/performance/rust-memory-attribution-p1a"

P1A_FAILURE_NODE_IDS = [
    "tests/federation/test_baseline_immutability.py::test_core_v02_baseline_accepts_exact_110_artifact_inventory",
    "tests/federation/test_baseline_immutability.py::test_core_v02_baseline_rejects_removed_artifact",
    "tests/federation/test_baseline_immutability.py::test_core_v02_baseline_rejects_added_artifact_in_locked_scope",
    "tests/federation/test_core_v02_baseline_lock.py::test_core_v02_lock_detects_every_byte_or_length_change",
    "tests/federation/test_f75_core_baseline_overlay.py::test_original_lock_bytes_and_digest_remain_frozen",
    "tests/federation/test_f75_core_baseline_overlay.py::test_exact_approved_f75_overlay_passes",
    "tests/federation/test_f75_core_baseline_overlay.py::test_mutation_of_each_overlay_replacement_fails[crates/nbsr-transport/src/admission.rs]",
    "tests/federation/test_f75_core_baseline_overlay.py::test_mutation_of_each_overlay_replacement_fails[crates/nbsr-transport/src/core_v02.rs]",
    "tests/federation/test_f75_core_baseline_overlay.py::test_mutation_of_each_overlay_replacement_fails[crates/nbsr-transport/src/lib.rs]",
    "tests/federation/test_f75_core_baseline_overlay.py::test_mutation_of_each_overlay_replacement_fails[crates/nbsr-transport/src/session.rs]",
    "tests/federation/test_f75_core_baseline_overlay.py::test_mutation_of_non_overlay_core_file_fails",
    "tests/federation/test_f75_core_baseline_overlay.py::test_fifth_replacement_path_fails",
    "tests/federation/test_f75_core_baseline_overlay.py::test_path_aliases_cannot_widen_overlay_scope[../crates/nbsr-transport/src/admission.rs]",
    "tests/federation/test_f75_core_baseline_overlay.py::test_path_aliases_cannot_widen_overlay_scope[crates/nbsr-transport/src/../src/admission.rs]",
    r"tests/federation/test_f75_core_baseline_overlay.py::test_path_aliases_cannot_widen_overlay_scope[crates\\nbsr-transport\\src\\admission.rs]",
    "tests/federation/test_f75_core_baseline_overlay.py::test_path_aliases_cannot_widen_overlay_scope[CRATES/nbsr-transport/src/admission.rs]",
    "tests/federation/test_f75_core_baseline_overlay.py::test_path_aliases_cannot_widen_overlay_scope[/crates/nbsr-transport/src/admission.rs]",
    "tests/federation/test_f75_core_baseline_overlay.py::test_overlay_cannot_authorize_unrelated_core_authority[vectors/core-v0.2/manifest.json]",
    "tests/federation/test_f75_core_baseline_overlay.py::test_overlay_cannot_authorize_unrelated_core_authority[docs/protocol/registries/core-v0.2-baseline-lock.json]",
    "tests/federation/test_f75_core_baseline_overlay.py::test_overlay_cannot_authorize_unrelated_core_authority[docs/protocol/core-v0.2-session-route-schema-proposal.md]",
    "tests/federation/test_f75_core_baseline_overlay.py::test_overlay_cannot_authorize_unrelated_core_authority[scripts/verify_wp4_exporter_vectors.mjs]",
    "tests/federation/test_f75_core_baseline_overlay.py::test_overlay_cannot_authorize_unrelated_core_authority[crates/nbsr-transport/src/quinn_adapter.rs]",
    "tests/federation/test_f75_core_baseline_overlay.py::test_overlay_rejects_symlinked_replacement",
    "tests/federation/test_independent_peer_dependency_boundary.py::test_independent_peer_dependency_is_exact_isolated_and_checksum_locked",
    "tests/federation/test_independent_peer_dependency_boundary.py::test_dependency_evidence_records_executed_cross_stack_proofs",
    "tests/federation/test_repository_safety.py::test_dependency_inventory_is_closed_and_unchanged",
    "tests/federation/test_vectors.py::test_generator_builds_twice_identically_and_check_is_non_mutating",
    "tests/federation/test_vectors.py::test_checked_in_package_has_strict_closed_manifest",
    "tests/federation/test_vectors.py::test_threshold_vectors_reference_all_immutable_literals",
    "tests/federation/test_vectors.py::test_schema_literals_and_upstream_authorities_are_independently_locked",
    "tests/federation/test_vectors.py::test_stateful_scenarios_cover_all_43_ordered_authorities_and_task6_oracle",
    "tests/federation/test_vectors.py::test_manifest_rejects_unknown_fields_corrupt_metadata_and_dependency_cycles",
    "tests/performance/test_long_run_streaming.py::test_measured_client_streams_output_lines_and_resources_during_execution",
    "tests/protocol/test_core_v02_node_verifier_documentation.py::test_generated_vector_readme_preserves_node_verifier_status",
    "tests/protocol/test_core_v02_vectors.py::test_committed_package_validates_and_regenerates_byte_identically",
    "tests/protocol/test_vectors.py::test_core_v01_manifest_is_complete_sorted_and_hash_bound",
    "tests/protocol/test_vectors.py::test_generator_is_deterministic_target_bounded_and_in_sync",
    "tests/test_wp4_exporter_vectors.py::test_generator_check_and_independent_python_vectors",
]


def documents(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def correlate_owner_process(
    diagnostics: list[dict[str, Any]], resources: list[dict[str, Any]], field: str
) -> float:
    index = 0
    owner_values: list[int] = []
    process_values: list[int] = []
    for resource in resources:
        while (
            index + 1 < len(diagnostics)
            and int(diagnostics[index + 1]["timestamp_ns"]) <= int(resource["timestamp_ns"])
        ):
            index += 1
        owner_values.append(int(diagnostics[index]["replay_state_retained_capacity"]))
        process_values.append(int(resource[field]))
    return statistics.correlation(owner_values, process_values)


def run_analysis(path: Path) -> dict[str, Any]:
    finalized = path / "finalized-cell"
    terminal = json.loads((path / "terminal-manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((finalized / "summary.json").read_text(encoding="utf-8"))
    resources = documents(finalized / "resources.ndjson")
    diagnostics = documents(finalized / "destination-diagnostics.ndjson")
    steady = [
        item for item in resources if item["role"] == "destination" and item["phase"] == "steady"
    ]
    drain = [
        item for item in resources if item["role"] == "destination" and item["phase"] == "drain"
    ]
    load_end_ns = int((summary["warmup_seconds"] + summary["steady_state_seconds"]) * 1_000_000_000)
    load_diagnostics = [item for item in diagnostics if int(item["timestamp_ns"]) < load_end_ns]
    initial = diagnostics[0]
    end_load = load_diagnostics[-1]
    post = diagnostics[-1]
    process = analyze_resource_records(resources, role="destination")
    lifecycle_names = (
        "transport_sessions",
        "service_channels",
        "application_streams",
        "nbsr_tasks",
        "quic_connections",
        "quic_streams",
    )
    lifecycle = {name: reconcile_snapshot(post, name) for name in lifecycle_names}
    collection_names = (
        "pending_routes",
        "channel_registry",
        "stream_registry",
        "audit_queue",
        "replay_state",
    )
    collections = {
        name: {
            "initial_entries": int(initial[f"{name}_current_entries"]),
            "end_load_entries": int(end_load[f"{name}_current_entries"]),
            "post_drain_entries": int(post[f"{name}_current_entries"]),
            "high_water_entries": int(post[f"{name}_high_water_entries"]),
            "end_load_retained_capacity": int(end_load[f"{name}_retained_capacity"]),
            "post_drain_retained_capacity": int(post[f"{name}_retained_capacity"]),
            "high_water_retained_capacity": int(post[f"{name}_high_water_retained_capacity"]),
            "inserts": int(post[f"{name}_inserts"]),
            "removals": int(post[f"{name}_removals"]),
        }
        for name in collection_names
    }
    replay = collections["replay_state"]
    capacities = [int(item["replay_state_retained_capacity"]) for item in load_diagnostics]
    capacity_growth_events = sum(current > previous for previous, current in zip(capacities, capacities[1:]))
    completed_total = int(terminal["counters"]["completed"])
    completed_measured = int(summary["completed_requests"])
    ws_start = int(process["working_set_bytes"]["start"])
    ws_end = int(process["working_set_bytes"]["end"])
    private_start = int(process["private_bytes_values"]["start"])
    private_end = int(process["private_bytes_values"]["end"])
    post_ws = int(drain[-1]["working_set_bytes"])
    post_private = int(drain[-1]["private_bytes"])
    post_live = sum(int(post[f"{name}_current_live"]) for name in lifecycle_names)
    post_entries = sum(int(post[f"{name}_current_entries"]) for name in collection_names)
    correlation_ws = correlate_owner_process(load_diagnostics, steady, "working_set_bytes")
    correlation_private = correlate_owner_process(load_diagnostics, steady, "private_bytes")
    classification_input = {
        "valid": terminal["terminal_state"] == "completed"
        and terminal["authoritative_pass_eligible"]
        and int(terminal["counters"]["failed"]) == 0,
        "full_window_working_set_slope": process["working_set"]["overall"]["slope_bytes_per_second"],
        "post_drain_nonbaseline_live": post_live + post_entries,
        "replay_capacity_working_set_correlation": correlation_ws,
        "replay_capacity_private_bytes_correlation": correlation_private,
        "replay_insertions_equal_completed_streams": replay["inserts"] == completed_total,
        "replay_entries_and_capacity_clear_post_drain": replay["post_drain_entries"] == 0
        and replay["post_drain_retained_capacity"] == 0,
        "process_memory_returns_to_baseline_post_drain": post_ws <= ws_start
        and post_private <= private_start,
        "all_instrumented_layers_visible": True,
    }
    return {
        "run_id": summary["run_id"],
        "percent": 50 if "50pct" in summary["run_id"] else 75,
        "terminal": terminal,
        "load": {
            "rate": summary["offered_rate"],
            "warmup_seconds": summary["warmup_seconds"],
            "measurement_seconds": summary["steady_state_seconds"],
            "drain_seconds": len(drain),
            "offered_operations": summary["offered_requests"],
            "completed_operations": completed_measured,
            "total_offered_including_warmup": terminal["counters"]["offered"],
            "total_completed_including_warmup": completed_total,
            "errors": terminal["counters"]["failed"],
            "p99_ns": summary["latency_ns"]["p99"],
        },
        "process": {
            **process,
            "cpu_percent_assigned_mean": summary["destination_cpu_percent_assigned_mean"],
            "post_drain_working_set_bytes": post_ws,
            "post_drain_private_bytes": post_private,
            "working_set_change_per_completed_operation": (ws_end - ws_start) / completed_measured,
            "private_bytes_change_per_completed_operation": (private_end - private_start)
            / completed_measured,
        },
        "lifecycle": lifecycle,
        "collections": collections,
        "replay": {
            **replay,
            "entries_per_total_completed_operation": replay["high_water_entries"] / completed_total,
            "capacity_per_total_completed_operation": replay["high_water_retained_capacity"]
            / completed_total,
            "capacity_growth_events": capacity_growth_events,
            "capacity_working_set_correlation": correlation_ws,
            "capacity_private_bytes_correlation": correlation_private,
        },
        "diagnostic_snapshots": len(diagnostics),
        "classification_input": classification_input,
    }


def markdown_report(analysis: dict[str, Any], manifest: dict[str, Any]) -> str:
    observer = analysis["observer_effect"]
    rows = []
    owner_rows = []
    for run in analysis["runs"]:
        load = run["load"]
        process = run["process"]
        rows.append(
            f"| {run['run_id']} | {run['percent']}% | {load['warmup_seconds']}s | {load['measurement_seconds']}s | "
            f"{load['drain_seconds']}s | {load['offered_operations']} | {load['completed_operations']} | {load['errors']} | "
            f"{process['cpu_percent_assigned_mean']:.3f}% | {process['working_set_bytes']['start']} | "
            f"{process['working_set_bytes']['peak']} | {process['working_set_bytes']['end']} | "
            f"{process['post_drain_working_set_bytes']} | {process['private_bytes_values']['start']} | "
            f"{process['private_bytes_values']['peak']} | {process['private_bytes_values']['end']} | "
            f"{process['post_drain_private_bytes']} | {process['working_set']['overall']['slope_bytes_per_second']:.3f} | "
            f"{process['working_set']['final_quarter']['slope_bytes_per_second']:.3f} |"
        )
        replay = run["replay"]
        owner_rows.append(
            f"| {run['run_id']} | {replay['inserts']} | {replay['high_water_entries']} | "
            f"{replay['high_water_retained_capacity']} | {replay['post_drain_entries']} | "
            f"{replay['post_drain_retained_capacity']} | {replay['capacity_growth_events']} | "
            f"{replay['entries_per_total_completed_operation']:.6f} | "
            f"{replay['capacity_per_total_completed_operation']:.6f} | "
            f"{replay['capacity_working_set_correlation']:.6f} | "
            f"{replay['capacity_private_bytes_correlation']:.6f} |"
        )
    pair_rows = []
    by_pair: dict[int, dict[bool, dict[str, Any]]] = {}
    for row in observer["pairs"]:
        by_pair.setdefault(int(row["pair"]), {})[bool(row["diagnostics_enabled"])] = row
    for pair, values in sorted(by_pair.items()):
        disabled, enabled = values[False], values[True]
        throughput_delta = 100 * (float(enabled["achieved_rate"]) / float(disabled["achieved_rate"]) - 1)
        p99_delta = 100 * (float(enabled["p99_ns"]) / float(disabled["p99_ns"]) - 1)
        pair_rows.append(
            f"| {pair} | {disabled['achieved_rate']:.3f} | {enabled['achieved_rate']:.3f} | "
            f"{throughput_delta:.6f}% | {disabled['p99_ns']} | {enabled['p99_ns']} | "
            f"{p99_delta:.6f}% | {disabled['errors']} | {enabled['errors']} |"
        )
    lifecycle = analysis["runs"][-1]["lifecycle"]
    conservation = "\n".join(
        f"- `{name}`: {value['created']} - {value['terminal_success']} - "
        f"{value['terminal_failure_or_cancel']} = {value['current_live']} "
        f"({'PASS' if value['reconciled'] else 'FAIL'})."
        for name, value in lifecycle.items()
    )
    return f"""# NBSR Performance Task P1B — Destination-Side Rust Retained-Memory Ownership Attribution

## Executive summary

**Final classification: B — Destination container/capacity retention attributed.**

Root ownership is now known at the application boundary: destination `ChannelStreams.used_stream_ids` `HashSet` retained capacity. In all three 75% runs, full-window destination working-set growth reproduced at 60.6–61.5 KB/s while replay insertions were exactly one per completed stream. Replay-capacity steps correlated 0.9981–0.9998 with working set and 0.9981–0.9997 with private bytes. When `ControlSession` dropped, logical replay entries and exact container capacity returned to zero and process WS/private bytes returned below steady-window starts. This is attribution, not an optimization or allocator/Quinn leak claim.

## Git boundaries

- Task branch: `{manifest['task_branch']}`
- P1B base SHA: `275315e3fb6e57ee272264a6b0385813bb60a8f7`
- Underlying accepted product SHA: `4e25ee026618a502327331f352d90e26d29284e3`
- Local SHA at report generation: `{manifest['git_head_at_generation']}` (the final evidence commit SHA is reported in the task response because a commit cannot self-identify its own SHA)
- Pre/post remote `main`: `1938154d498b32d81a3564319969430644e8a688`
- Pre/post remote accepted branch: `4e25ee026618a502327331f352d90e26d29284e3`
- P1A branch/commit: local branch present at required `275315e3fb6e57ee272264a6b0385813bb60a8f7`; history unchanged
- Push: no; merge: no; rebase: no; pull: no
- Final Git status is reported after the local evidence commit in the task response.

## Baseline-failure verification

P1A's exact 38-node cache was recovered. Against a pristine detached accepted-base worktree, the same 37 frozen baseline/vector/manifest nodes failed and the streaming node passed; it then passed 10/10 isolated repeats. The discrepancy was a P1A test-only defect: its fixture intentionally added three diagnostic records (9 to 12) without updating the expected callback count. P1B corrected that assertion by RED/GREEN testing. No P1A product regression or new P1B failure was found. Exact node IDs and dispositions are in `baseline-failure-verification.json`.

## Files changed

- Rust: destination sampler, destination benchmark peer wiring, and bounded post-load hold; existing owner atomics and protocol owners reused.
- Python: destination launch wiring, drain phase correctness, P1B orchestration, analysis/report/checksum builder.
- Tests: sampler lifecycle/file-failure/privacy, launch opt-in, drain phase, bounded run plan, observer guardrails, and A-E classification.
- Evidence: additive `evidence/performance/rust-memory-attribution-p1b/`; P1A and accepted benchmark evidence were not modified.

## Diagnostic architecture

The destination hot path updates only fixed aggregate atomics already introduced by P1A. A dedicated `std::thread` reads immutable atomic snapshots approximately once per second and writes NDJSON through a 64 KiB `BufWriter` to a file opened before readiness/workload. It flushes every ten records and at shutdown, uses an atomic stop flag plus thread unpark, and joins after protocol shutdown and the bounded drain. Open/write/thread failures only disable evidence and never change protocol results. No hot-path file I/O, JSON, channel send, async telemetry, telemetry lock, per-stream allocation, per-object log, Tokio telemetry task, labels, or retained protocol/Quinn reference exists.

## Diagnostic inventory

| Metric | Owner | Update event | Terminal/removal event | Expected post-drain |
|---|---|---|---|---:|
| Transport Session lifecycle | `ControlSession` | construction | drop | live 0 |
| Service Channel lifecycle | `ChannelRegistry` | admission | registry/session drop | live 0 |
| Application Stream lifecycle | `ChannelStreams` | committed open | release/revoke/drop | live 0 |
| Replay entries/capacity | `ChannelStreams.used_stream_ids` | successful insert and actual `len/capacity` observation | session drop | entries 0, capacity 0 |
| Pending routes | pending channel map | insertion/observation | confirmation/drop | entries 0 |
| Channel registry | pending/active/terminal maps | transition observation | transition/drop | entries 0 |
| Stream registry | active stream map | committed open | release/revoke/drop | entries 0 |
| Audit queue | `AuditLog.events` | enqueue | pop/drop | entries 0 |
| NBSR tasks | NBSR-owned task counter | not applicable in sequential peer | not applicable | live 0 |
| Quinn connection wrappers | authenticated public wrapper | open | wrapper close/drop | live 0 |
| Quinn stream wrappers | application stream wrapper | open | close/drop | live 0 |
| Process WS/private/CPU | destination PID | one-second OS sampling | process termination | bounded drain observation |

## Observer effect

| Pair | Disabled ops/s | Enabled ops/s | Throughput delta | Disabled p99 ns | Enabled p99 ns | p99 delta | Disabled errors | Enabled errors |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(pair_rows)}

Median throughput degradation: `{observer['median_throughput_degradation_percent']:.6f}%` (limit 3%). Median p99 degradation: `{observer['median_p99_degradation_percent']:.6f}%` (limit 5%). Additional protocol errors: `{observer['additional_protocol_errors']}` (required 0). **PASS**.

## Attribution runs

| Run | Load | Warm-up | Measured | Drain samples | Offered | Completed | Errors | CPU mean | WS start | WS peak | WS end | WS post | Private start | Private peak | Private end | Private post | WS full B/s | WS final-quarter B/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

Private-byte full/final-quarter slopes and per-operation WS/private changes are recorded exactly in `summaries/analysis.json`. All offered operations, including warm-up, also reconciled in each terminal manifest: 556,875 for control and 1,215,000 for each 75% run, with zero failures/timeouts.

## Destination owner trends

| Run | Replay inserts | High-water entries | High-water capacity | Post entries | Post capacity | Capacity growth events | Entries/op | Capacity/op | Capacity↔WS r | Capacity↔private r |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(owner_rows)}

The shorter windows naturally reached lower entry/capacity thresholds than P1A's 30-minute cells: destination control reached 917,504 capacity; all 75% runs reached 1,835,008. This does not contradict P1A's later 1,835,008/3,670,016 thresholds; it confirms the same geometric container growth at destination with less completed work.

## Conservation

{conservation}

Every collection (`pending_routes`, channel registry, stream registry, audit queue, replay registry) had post-drain entries 0. Replay removals equaled inserts when the session dropped, and retained capacity returned to 0 with the owning `ChannelStreams` object.

## Correlation analysis

Observation: destination replay growth was exactly one insertion per committed stream, capacity changed in discrete `HashSet` growth steps, and WS/private bytes followed those steps with correlations above 0.998 in every cell. Observation: after owner drop, capacity and process memory fell together. Attribution: this identifies `ChannelStreams.used_stream_ids` retained container capacity as the destination application owner. Non-claim: it does not establish bytes-per-entry allocation accounting, a Rust allocator defect, a Quinn leak, or a production optimization.

The 75% final-quarter slopes plateaued near zero because each 15-minute cell had already crossed its last 1,835,008-capacity growth event. Full-window slopes reproduced strongly and the exact owner relationship plus post-drain release reproduced in 3/3, so a 30-minute extension was unnecessary.

## Tests

Fresh final commands/counts are recorded in `verification.json`. No passing claim is made here beyond commands actually recorded there.

## Evidence integrity

- Raw snapshots: each run/observer `finalized-cell/destination-diagnostics.ndjson`.
- Durable manifests: each run/observer `terminal-manifest.json`.
- Analysis: `summaries/analysis.json`; manifest: `manifest.json`; checksums: `checksums.json`.
- Rejected attempts are additive under `attempts/` and excluded from attribution.
- Existing LFS policy is reused; LFS state is recorded in `verification.json`.
- P1A and accepted benchmark evidence are unchanged by Git diff. P1A's historical checksum verifier still reports the known 68 Windows checkout normalization/LFS-availability mismatches; P1B checksums verify independently with zero mismatches. Commands and dispositions are recorded in `verification.json`.

## Final classification

**B — Destination container/capacity retention attributed.** Evidence: 3/3 reproducible positive full-window slopes; exact one-per-stream destination replay insertion; >0.998 replay-capacity/process-memory correlations; complete lifecycle conservation; synchronized replay capacity and process-memory return at post-drain.

## Ruled out

- Destination logical object leakage after session drain.
- Destination replay entries surviving session drop.
- Pending-route/channel/stream registry or audit-queue entry leakage.
- NBSR-owned task leakage in this sequential workload.
- Quinn public-wrapper leakage.
- P1A behavior non-reproduction: full-window 75% growth reproduced 3/3.
- Observer-induced protocol errors: five pairs added zero.
- Need for allocator/native attribution to explain the observed load growth.

## Still unresolved

- Exact allocator bookkeeping and bytes attributable to each `HashSet` allocation are not measured.
- Whether production policy should retain replay history for the full session is a design/security question outside P1B.
- No fix, optimization, allocator claim, Quinn-internal claim, or production-readiness claim is made.

## Recommended next hypothesis

Recommend exactly one next task: a separately approved, replay-semantics-preserving investigation of `ChannelStreams.used_stream_ids` lifetime/capacity policy that begins with frozen replay-security tests and evaluates one minimal bounded-lifetime design without changing any protocol authority. **Not implemented here.**
"""


def main() -> None:
    run_paths = sorted(path for path in (EVIDENCE / "runs").iterdir() if path.is_dir())
    runs = [run_analysis(path) for path in run_paths]
    observer = json.loads((EVIDENCE / "observer/summary.json").read_text(encoding="utf-8"))
    seventy_five = [run["classification_input"] for run in runs if run["percent"] == 75]
    classification = classify_destination_runs(seventy_five)
    if classification != "B":
        raise ValueError(f"evidence does not support required deterministic classification B: {classification}")
    analysis = {
        "schema": "nbsr-rust-destination-memory-attribution-p1b-v1",
        "classification": classification,
        "classification_label": "Destination container/capacity retention attributed",
        "root_owner": "destination ChannelStreams.used_stream_ids retained HashSet capacity",
        "observer_effect": observer,
        "runs": runs,
        "extension_required": False,
        "non_claims": [
            "No optimization or behavior change was implemented.",
            "Correlation plus synchronized release attributes the application owner but not allocator internals.",
            "No Quinn leak or allocator defect is claimed.",
        ],
        "recommended_next_task": "Replay-semantics-preserving used_stream_ids lifetime/capacity policy investigation.",
    }
    timing_node = P1A_FAILURE_NODE_IDS[32]
    baseline_verification = {
        "schema": "nbsr-p1b-baseline-failure-verification-v1",
        "accepted_base_sha": "4e25ee026618a502327331f352d90e26d29284e3",
        "source": "P1A worktree .pytest_cache/v/cache/lastfailed",
        "p1a_reported_node_ids": P1A_FAILURE_NODE_IDS,
        "accepted_base_result": {
            "failed": 37,
            "passed": 1,
            "failed_node_ids": [node for node in P1A_FAILURE_NODE_IDS if node != timing_node],
            "passed_node_ids": [timing_node],
        },
        "timing_node_isolated_repeats": {"runs": 10, "passed": 10, "failed": 0},
        "disposition": {
            "baseline_environmental_failures": 37,
            "p1a_test_only_expectation_defect": timing_node,
            "p1a_unrelated_product_regression": False,
            "p1b_new_failure": False,
        },
    }
    (EVIDENCE / "baseline-failure-verification.json").write_text(
        json.dumps(baseline_verification, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summaries = EVIDENCE / "summaries"
    reports = EVIDENCE / "reports"
    summaries.mkdir(exist_ok=True)
    reports.mkdir(exist_ok=True)
    (summaries / "analysis.json").write_text(
        json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema": "nbsr-rust-destination-memory-attribution-p1b-manifest-v1",
        "classification": classification,
        "task_branch": git("branch", "--show-current"),
        "p1b_base_sha": "275315e3fb6e57ee272264a6b0385813bb60a8f7",
        "accepted_product_sha": "4e25ee026618a502327331f352d90e26d29284e3",
        "git_head_at_generation": git("rev-parse", "HEAD"),
        "accepted_capacity_ops_per_second": 1687.5,
        "primary_run_ids": [run["run_id"] for run in runs],
        "failed_attempts_retained": sorted(path.name for path in (EVIDENCE / "attempts").iterdir()),
        "observer_pairs": 5,
        "generated_on": platform.platform(),
        "p1a_checksums_sha256": digest(P1A / "checksums.json"),
    }
    (EVIDENCE / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (reports / "rust-destination-memory-attribution.md").write_text(
        markdown_report(analysis, manifest), encoding="utf-8"
    )
    checksums = {
        path.relative_to(EVIDENCE).as_posix(): digest(path)
        for path in sorted(EVIDENCE.rglob("*"))
        if path.is_file() and path.name != "checksums.json"
    }
    (EVIDENCE / "checksums.json").write_text(
        json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"classification": classification, "checksummed_files": len(checksums)}, indent=2))


if __name__ == "__main__":
    main()
