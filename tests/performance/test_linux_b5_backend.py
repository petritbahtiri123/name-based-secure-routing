from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('stage', ['verify', 'observe', 'source-drain', 'destination-drain'])
def test_pending_cancellation_reaches_registered_peer_safe_points(stage):
    from scripts.performance.linux_b5_backend import LinuxB5Backend
    def cancelled():
        raise InterruptedError('SIGTERM fixture')
    value = LinuxB5Backend({'platform': 'linux', 'selected_cpus': [2], 'taskset': '/usr/bin/taskset'},
                          check_cancelled=cancelled)
    child = SimpleNamespace(pid=123)
    with pytest.raises(InterruptedError, match='SIGTERM'):
        if stage == 'verify':
            value.verify_affinity(child, 4, '/fixture')
        elif stage == 'observe':
            value.observe_source(child)
        elif stage == 'source-drain':
            value.complete_source(child, None, 10**30)
        else:
            value.complete_destination(child, 'destination_0', None, None, 10**30)


def backend():
    from scripts.performance.linux_b5_backend import LinuxB5Backend
    return LinuxB5Backend({"platform": "linux", "selected_cpus": [2], "taskset": "/usr/bin/taskset"})


def test_prelaunch_affinity_is_part_of_recorded_command():
    value = backend()
    value.validate({"endpoint_groups": 1}, {"source_mask": 4, "endpoint_masks": [4], "logical_processors_available": 1})
    assert value.command(["/peer", "--role", "server"]) == ["/usr/bin/taskset", "-c", "2", "/peer", "--role", "server"]
    with pytest.raises(ValueError):
        value.validate({"endpoint_groups": 2}, {"source_mask": 4, "endpoint_masks": [4, 4], "logical_processors_available": 1})


def test_source_sampler_stops_before_reaping():
    events = []
    source = SimpleNamespace(pid=123, wait=lambda timeout: events.append("wait") or 0)
    sampler = SimpleNamespace(check_health=lambda **kw: None,
        records_snapshot=lambda: [{"role": "source", "pid": 123, "state": "Z"}],
        stop=lambda: events.append("stop"))
    backend().complete_source(source, sampler, 10**30)
    assert events == ["stop", "wait"]


def test_split_placement_records_exact_role_commands_and_rejects_widening():
    from scripts.performance.linux_b5_backend import LinuxB5Backend
    value = LinuxB5Backend({"platform": "linux", "selected_cpus": [2, 4],
                           "taskset": "/usr/bin/taskset"}, placement="split")
    plan = dict(source_mask=4, endpoint_masks=[16], logical_processors_available=2)
    value.validate({"endpoint_groups": 1}, plan)
    assert value.command(["/source"], mask=4)[2] == "2"
    assert value.command(["/destination"], mask=16)[2] == "4"
    with pytest.raises(ValueError):
        value.command(["/peer"], mask=20)
    with pytest.raises(ValueError):
        value.validate({"endpoint_groups": 1}, plan | {"endpoint_masks": [4]})


def test_split_placement_requires_two_distinct_cpus():
    from scripts.performance.linux_b5_backend import LinuxB5Backend
    for cpus in ([2], [2, 2], [2, True]):
        with pytest.raises(ValueError):
            LinuxB5Backend({"platform": "linux", "selected_cpus": cpus,
                            "taskset": "/usr/bin/taskset"}, placement="split")


def test_source_sampler_failure_prevents_reaping():
    def fail(**kwargs):
        raise RuntimeError("sampler failed")
    source = SimpleNamespace(wait=lambda **kw: pytest.fail("must not reap before validated sampling"))
    sampler = SimpleNamespace(check_health=fail)
    with pytest.raises(RuntimeError, match="sampler failed"):
        backend().complete_source(source, sampler, 10**30)


@pytest.mark.parametrize("changed", [False, True])
def test_destination_terminal_sample_precedes_reap(monkeypatch, changed):
    from scripts.performance import linux_b5_backend as module
    events = []
    prior = dict(role="destination_0", pid=456, start_ticks=11, cpu_ns=20, timestamp_ns=30)
    final = dict(pid=456, start_ticks=12 if changed else 11, cpu_ns=21, timestamp_ns=31, state="Z")
    monkeypatch.setattr(module, "observe_owned_exit", lambda pid: 0)
    monkeypatch.setattr(module, "sample_linux_process", lambda pid, cpus: events.append("sample") or final)
    server = SimpleNamespace(pid=456, wait=lambda timeout: events.append("wait") or 0)
    sampler = SimpleNamespace(records_snapshot=lambda: [prior])
    if changed:
        with pytest.raises(RuntimeError, match="terminal"):
            backend().complete_destination(server, "destination_0", sampler, lambda r: events.append("sink"), 10**30)
        assert events == ["sample"]
    else:
        backend().complete_destination(server, "destination_0", sampler, lambda r: events.append("sink"), 10**30)
        assert events == ["sample", "sink", "wait"]
