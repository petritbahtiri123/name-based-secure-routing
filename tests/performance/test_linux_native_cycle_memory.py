import importlib
import json

import pytest

from tests.performance.test_linux_native_cycle_run import config
from scripts.performance import linux_native_cycle_run as run


def module():
    return importlib.import_module("scripts.performance.linux_native_cycle_memory")


def sample(timestamp=100, pid=7, start_ticks=9):
    return dict(
        pid=pid,
        start_ticks=start_ticks,
        affinity=[0],
        timestamp_ns=timestamp,
        cpu_ns=10,
        state="S",
        memory_state="MEASURED",
        memory_basis="linux_smaps_rollup",
        rss_bytes=4096,
        pss_bytes=3072,
        private_resident_bytes=2048,
        private_hugetlb_bytes=0,
    )


def test_observer_is_opt_in_and_bound_to_remote_command():
    value = config() | dict(memory_observer=True)
    run.validate_config(value)
    assert "--memory-observer" in run.endpoint_arguments(value, "source")
    assert "--memory-observer" not in run.endpoint_arguments(config(), "source")
    with pytest.raises(ValueError):
        run.validate_config(config() | dict(memory_observer=1))


def test_bounded_one_hz_memory_capture(tmp_path):
    now = [100]
    calls = []
    first = sample(100)
    last = sample(2_000_000_000) | dict(state="Z")
    (tmp_path / "resources.ndjson").write_text(json.dumps(first) + "\n" + json.dumps(last) + "\n")

    def capture(pid, cpus):
        calls.append((pid, cpus))
        return sample(now[0])

    with module().CycleMemoryObserver(tmp_path, pid=7, start_ticks=9, cpus=[0], cycles=2, sample=capture, clock=lambda: now[0]) as observer:
        observer.poll()
        now[0] += 100_000_000
        observer.poll()
        assert len(calls) == 1
        now[0] += 900_000_000
        observer.poll()
        observer.stop()
        result = observer.finish(0)
    assert result["measured_samples"] == 2
    assert result["observer_neutrality"] == "NOT_ESTABLISHED"
    assert module().verify_memory(tmp_path, pid=7, start_ticks=9, cpus=[0], cycles=2) == result


@pytest.mark.parametrize(
    "mutation", ["pid", "epoch", "affinity", "missing", "negative", "boolean", "basis", "bounds", "frequency", "duplicate"]
)
def test_invalid_memory_record_rejects(tmp_path, mutation):
    m = module()
    rows = [
        dict(capture_started_ns=100, capture_finished_ns=200, value=sample(150)),
        dict(capture_started_ns=1_000_000_100, capture_finished_ns=1_000_000_200, value=sample(1_000_000_150)),
    ]
    value = rows[1]["value"]
    if mutation == "pid":
        value["pid"] = 8
    elif mutation == "epoch":
        value["start_ticks"] = 10
    elif mutation == "affinity":
        value["affinity"] = [1]
    elif mutation == "missing":
        del value["pss_bytes"]
    elif mutation == "negative":
        value["private_resident_bytes"] = -1
    elif mutation == "boolean":
        value["private_resident_bytes"] = True
    elif mutation == "basis":
        value["memory_basis"] = "estimated"
    elif mutation == "bounds":
        value["private_resident_bytes"] = 5000
    elif mutation == "frequency":
        rows[1]["capture_started_ns"] = 200
    else:
        rows.append(rows[-1])
    (tmp_path / "memory.ndjson").write_text("".join(json.dumps(r) + "\n" for r in rows))
    with pytest.raises(ValueError):
        m.verify_memory(tmp_path, pid=7, start_ticks=9, cpus=[0], cycles=2)


def test_absent_memory_is_not_zero(tmp_path):
    with pytest.raises((ValueError, FileNotFoundError)):
        module().verify_memory(tmp_path, pid=7, start_ticks=9, cpus=[0], cycles=2)


@pytest.mark.parametrize("tamper", [False, True, "after-exit", "past-terminal-cpu"])
def test_peer_binds_memory_mode_and_raw_summary(tmp_path, tamper):
    from scripts.performance import linux_native_lifecycle_pair as pair
    from scripts.performance.linux_b5_placement import seal_output
    from tests.performance.test_linux_native_cycle_pair import cycle_peers, write, SHA

    root, _ = cycle_peers(tmp_path)
    terminal = json.loads((root / "exit.json").read_bytes())["final_sample"]
    value = sample(100, pid=terminal["pid"], start_ticks=terminal["start_ticks"])
    start = end = 100
    if tamper == "after-exit":
        start = end = value["timestamp_ns"] = 10**15
    if tamper == "past-terminal-cpu":
        value["cpu_ns"] = 10**12
    (root / "memory.ndjson").write_text(json.dumps(dict(capture_started_ns=start, capture_finished_ns=end, value=value)) + "\n")
    env = json.loads((root / "environment.json").read_bytes())
    env["memory_observer"] = True
    write(root, "environment.json", env)
    summary = module().verify_memory(root, pid=value["pid"], start_ticks=value["start_ticks"], cpus=[0], cycles=2)
    if tamper is True:
        summary["measured_samples"] += 1
    exited = json.loads((root / "exit.json").read_bytes())
    exited["cycle_memory"] = summary
    result = json.loads((root / "result.json").read_bytes())
    result["process"] = exited
    write(root, "exit.json", exited)
    write(root, "result.json", result)
    seal_output(root)
    if tamper:
        with pytest.raises(ValueError):
            pair.check_peer(root, "source", SHA, 2, cycles=2, memory_observer=True)
    else:
        assert pair.check_peer(root, "source", SHA, 2, cycles=2, memory_observer=True)["outcome"]["successful"] == 2
        with pytest.raises(ValueError):
            pair.check_peer(root, "source", SHA, 2, cycles=2)


@pytest.mark.parametrize("invented", [False, True])
def test_final_zombie_can_follow_terminal_clock_without_inventing_memory(tmp_path, invented):
    m = module()
    live = sample(100)
    terminal = sample(1_000_000_100) | dict(state="Z")
    zombie = sample(1_000_000_200) | dict(state="Z", memory_state="UNAVAILABLE_ZOMBIE")
    for key in m.FIELDS:
        zombie[key] = None
    if invented:
        zombie["rss_bytes"] = 0
    rows = [
        dict(capture_started_ns=100, capture_finished_ns=100, value=live),
        dict(capture_started_ns=1_000_000_200, capture_finished_ns=1_000_000_200, value=zombie),
    ]
    (tmp_path / "memory.ndjson").write_text("".join(json.dumps(r) + "\n" for r in rows))
    if invented:
        with pytest.raises(ValueError):
            m.verify_memory(tmp_path, pid=7, start_ticks=9, cpus=[0], cycles=2, lifetime=(live, terminal))
    else:
        assert m.verify_memory(tmp_path, pid=7, start_ticks=9, cpus=[0], cycles=2, lifetime=(live, terminal))["measured_samples"] == 1


def test_memory_observer_preserves_exiting_gap_until_owned_zombie(tmp_path):
    now = [100]
    first = sample(100)
    terminal = sample(3_000_000_000) | dict(state='Z')
    (tmp_path/'resources.ndjson').write_text(json.dumps(first)+'\n'+json.dumps(terminal)+'\n')
    def capture(pid, cpus):
        if now[0]==100:
            return first
        return sample(now[0]) | dict(state='R',flags=4,memory_state='UNAVAILABLE_EXITING', **dict.fromkeys(module().FIELDS))
    with module().CycleMemoryObserver(tmp_path,pid=7,start_ticks=9,cpus=[0],cycles=None,sample=capture,clock=lambda:now[0]) as observer:
        observer.poll()
        now[0] += 1_000_000_000
        observer.poll()
        assert observer.stopped
        assert observer.finish(0)['measured_samples']==1
    rows=[json.loads(v) for v in (tmp_path/'memory.ndjson').read_text().splitlines()]
    rows[-1]['value']['flags']=0
    (tmp_path/'memory.ndjson').write_text(''.join(json.dumps(v)+'\n' for v in rows))
    with pytest.raises(ValueError):
        module().verify_memory(tmp_path,pid=7,start_ticks=9,cpus=[0],cycles=None)


@pytest.mark.parametrize('next_state', ['MEASURED', 'UNAVAILABLE_EXITING'])
def test_memory_cannot_resume_after_verified_exit_gap(tmp_path, next_state):
    values=[sample(100), sample(1_000_000_100) | dict(state='R', flags=4, memory_state='UNAVAILABLE_EXITING', **dict.fromkeys(module().FIELDS))]
    last = sample(2_000_000_100)
    if next_state=='UNAVAILABLE_EXITING':
        last |= dict(state='R', flags=4, memory_state=next_state, **dict.fromkeys(module().FIELDS))
    values.append(last)
    (tmp_path/'memory.ndjson').write_text(''.join(json.dumps(dict(capture_started_ns=v['timestamp_ns'],capture_finished_ns=v['timestamp_ns'],value=v))+'\n' for v in values))
    with pytest.raises(ValueError, match='order'):
        module().verify_memory(tmp_path,pid=7,start_ticks=9,cpus=[0],cycles=None)
