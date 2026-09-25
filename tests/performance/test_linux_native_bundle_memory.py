import json

import pytest

from scripts.performance import linux_native_lifecycle as native
from scripts.performance import linux_native_lifecycle_coordinator as coordinator
from scripts.performance import linux_native_lifecycle_pair as pair
from scripts.performance.linux_native_cycle_memory import verify_memory, CycleMemoryObserver
from scripts.performance.linux_b5_placement import seal_output
from tests.performance.test_linux_native_lifecycle_coordinator import config
from tests.performance.test_linux_native_lifecycle_pair import peers, write, SHA
from tests.performance.test_linux_native_cycle_memory import sample


def test_bundle_memory_opt_in_config_remote_and_cli():
    value = config() | dict(memory_observer=True)
    assert coordinator.validate_config(value) == value
    assert "--memory-observer" in coordinator.endpoint_arguments(value, "source")
    assert "--memory-observer" not in coordinator.endpoint_arguments(config(), "source")
    argv = coordinator.endpoint_arguments(value, "source")[4:]
    assert native.argument_parser().parse_args(argv).memory_observer is True
    with pytest.raises(ValueError):
        coordinator.validate_config(config() | dict(memory_observer=1))


def test_bundle_memory_keeps_bounded_existing_budget(tmp_path):
    observer = CycleMemoryObserver(tmp_path, pid=7, start_ticks=9, cpus=[0], cycles=None)
    assert observer.cap == 121


@pytest.mark.parametrize("role", ["source", "destination"])
@pytest.mark.parametrize("tamper", [False, "mode", "summary", "after-exit"])
def test_bundle_raw_memory_binding(tmp_path, role, tamper):
    roots = peers(tmp_path)
    root = roots[0 if role == "source" else 1]
    exited = json.loads((root / "exit.json").read_bytes())
    terminal = exited["final_sample"]
    timestamp = 10**15 if tamper == "after-exit" else 100
    value = sample(timestamp, pid=terminal["pid"], start_ticks=terminal["start_ticks"])
    (root / "memory.ndjson").write_text(json.dumps(dict(capture_started_ns=timestamp, capture_finished_ns=timestamp, value=value)) + "\n")
    env = json.loads((root / "environment.json").read_bytes())
    env["memory_observer"] = tamper != "mode"
    write(root, "environment.json", env)
    summary = verify_memory(root, pid=value["pid"], start_ticks=value["start_ticks"], cpus=[0], cycles=None)
    if tamper == "summary":
        summary["measured_samples"] += 1
    exited["cycle_memory"] = summary
    result = json.loads((root / "result.json").read_bytes())
    result["process"] = exited
    write(root, "exit.json", exited)
    write(root, "result.json", result)
    seal_output(root)
    if tamper:
        with pytest.raises(ValueError):
            pair.check_peer(root, role, SHA, 16, memory_observer=True)
    else:
        assert pair.check_peer(root, role, SHA, 16, memory_observer=True)["outcome"]["successful"] == 16
        with pytest.raises(ValueError):
            pair.check_peer(root, role, SHA, 16)
