from copy import deepcopy
from types import SimpleNamespace
import pytest
from scripts.performance.b3_linux import LinuxCapture
from scripts.run_b3_session_lifecycle import COUNTERS
from tests.performance.test_b3_linux import reading


def cell():
    counter = 100

    def sample(pid, cpus):
        nonlocal counter
        counter += 10
        return dict(reading(pid, cpus), timestamp_ns=counter, cpu_ns=counter)

    source = SimpleNamespace(pid=10, poll=lambda: None)
    destination = SimpleNamespace(pid=20, poll=lambda: None)
    capture = LinuxCapture([2], "/taskset", sample_fn=sample)
    rows = []
    for cycle in range(2):
        if cycle == 0:
            capture.capture_once(rows, destination, [source], phase="idle", cycle=cycle)
        capture.capture_once(rows, destination, [source], phase="active", cycle=cycle)
        if cycle == 1:
            source.poll = lambda: 0
        capture.capture_once(rows, destination, [source], phase="cooldown", cycle=cycle, allow_exited_sources=cycle == 1)
    return dict(
        name="cycles-2-r1",
        kind="cycles",
        cycles=2,
        channels=1,
        streams=1,
        sessions=1,
        destination_completion=True,
        destination_completion_records=[0, 1],
        completion_environment={"NBSR_PERF_LIFECYCLE_COMPLETION_MARKERS": "1"},
        samples=rows,
        cleanup=dict(
            all_zero=True,
            counter_scope="historical-go-destination-8-fields",
            counters=dict.fromkeys(COUNTERS, 0),
            source_processes_exited=True,
            destination_exited=True,
        ),
        client_results=[
            dict(status="PASS", samples=[dict(sample_id=i, success=True, bytes_transmitted=1024, bytes_received=1024) for i in range(2)])
        ],
    )


def test_go_exit_is_unavailable_not_zero_or_full_ownership():
    from scripts.performance.b3_go_linux_analysis import analyze_cell

    result = analyze_cell(cell(), [2])
    assert result["source_ownership"] == "NOT_MEASURED"
    assert result["roles"]["source"]["cooldown"][-1]["private_resident_bytes"] is None
    assert result["roles"]["destination"]["cooldown"][-1]["private_resident_bytes"] == 50


@pytest.mark.parametrize(
    "mutation",
    [
        "early_exit",
        "destination_exit",
        "identity",
        "affinity",
        "metric",
        "cpu",
        "clock",
        "missing_phase",
        "marker",
        "ownership",
        "response",
        "resume",
    ],
)
def test_go_analysis_rejects_broken_evidence(mutation):
    from scripts.performance.b3_go_linux_analysis import analyze_cell

    value = cell()
    source = [r for r in value["samples"] if r["role"] == "source"]
    last = source[-1]
    if mutation == "early_exit":
        last["cycle"] = 0
    elif mutation == "destination_exit":
        last["role"] = "destination"
    elif mutation == "identity":
        last["processes"][0]["start_ticks"] += 1
    elif mutation == "affinity":
        source[0]["processes"][0]["affinity"] = [4]
    elif mutation == "metric":
        source[0]["private_resident_bytes"] += 1
    elif mutation == "cpu":
        source[-2]["processes"][0]["cpu_ns"] = 0
    elif mutation == "clock":
        source[-2]["processes"][0]["timestamp_ns"] = 0
    elif mutation == "missing_phase":
        value["samples"].remove(source[1])
    elif mutation == "marker":
        value["destination_completion_records"] = [0]
    elif mutation == "ownership":
        value["cleanup"]["counters"][COUNTERS[0]] = 1
    elif mutation == "response":
        value["client_results"][0]["samples"][0]["success"] = False
    elif mutation == "resume":
        value["samples"].append(deepcopy(source[-2]))
    with pytest.raises(ValueError):
        analyze_cell(value, [2])


@pytest.mark.parametrize("ids", [[0, 0], [None, 1], [False, 1], [1, 0]])
def test_distinct_ordered_operations_required(ids):
    from scripts.performance.b3_go_linux_analysis import analyze_cell

    value = cell()
    for sample, identity in zip(value["client_results"][0]["samples"], ids):
        sample["sample_id"] = identity
    with pytest.raises(ValueError):
        analyze_cell(value, [2])
