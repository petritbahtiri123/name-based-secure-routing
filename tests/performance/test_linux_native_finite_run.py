from pathlib import Path
from types import SimpleNamespace

import pytest


def config():
    value = dict(schema="nbsr-native-finite-coordinator-v1", source_sha="a" * 40, path="direct", payload=1024, streams=8, depth=1)
    for role, ip in [("source", "192.0.2.1"), ("destination", "192.0.2.2")]:
        value[role] = dict(
            transport="docker",
            host=role,
            checkout="/repo",
            binaries="/bins",
            build_manifest="/build.json",
            authority="/private/tls",
            output="/evidence",
            bind=ip + ":0",
            cores=1,
        )
    return value


def test_command_preserves_shape_and_native_bind():
    from scripts.performance.linux_native_finite_run import validate_config, endpoint_arguments

    value = validate_config(config())
    argv = endpoint_arguments(value, "source")
    assert argv[argv.index("--destination-address") + 1] == "192.0.2.2"
    assert argv[argv.index("--streams") + 1] == "8"
    assert "--operations-per-stream" not in argv
    assert "--phase-control" not in argv


@pytest.mark.parametrize("field,value", [("streams", True), ("streams", 0), ("path", "plain"), ("depth", 3), ("payload", 7)])
def test_config_rejects_invalid_workload(field, value):
    from scripts.performance.linux_native_finite_run import validate_config

    item = config()
    item[field] = value
    with pytest.raises(ValueError):
        validate_config(item)


def test_same_host_overlap_and_private_output_are_rejected():
    from scripts.performance.linux_native_finite_run import validate_config

    item = config()
    item["destination"]["host"] = "source"
    with pytest.raises(ValueError):
        validate_config(item)
    item = config()
    item["source"]["output"] = "/private"
    with pytest.raises(ValueError):
        validate_config(item)


def test_no_collection_without_fresh_owned_event(tmp_path, monkeypatch):
    from scripts.performance import linux_native_finite_run as run

    actions = []

    class Manager:
        def __init__(self, *a, **k):
            self.children = {"source": object()}
            self.ledger = SimpleNamespace(positions=dict(source=0, destination=0))

        def start_command(self, *a):
            raise RuntimeError("startup failed")

        wait = send = finish = lambda *a: None

        def close(self):
            actions.append("closed")
            return {}

    monkeypatch.setattr(run, "Manager", Manager)
    monkeypatch.setattr(run, "collect", lambda *a, **k: pytest.fail("unsafe collection"))
    root = tmp_path / "out"
    with pytest.raises(RuntimeError, match="startup failed"):
        run.execute(config(), root, before_collection=lambda: pytest.fail("observer after failed drive"))
    assert actions == ["closed"] and (root / "source-collection-skipped.json").exists()
    assert (root / "failure.json").exists() and (root / "checksums.sha256").exists()


def test_checkout_output_rejected_before_creation(tmp_path, monkeypatch):
    from scripts.performance import linux_native_finite_run as run

    monkeypatch.setattr(run, "ROOT", Path(tmp_path))
    with pytest.raises(ValueError):
        run.execute(config(), tmp_path / "inside")
    assert not (tmp_path / "inside").exists()


@pytest.mark.parametrize("observer_fails", [False, True])
def test_pre_collection_observer_order_and_failure_preserve_evidence(tmp_path, monkeypatch, observer_fails):
    from scripts.performance import linux_native_finite_run as run

    actions = []

    class Manager:
        def __init__(self, *args, **kwargs):
            self.children = dict(source=object(), destination=object())
            self.ledger = SimpleNamespace(positions=dict(source=1, destination=1))

        start_command = wait = send = finish = lambda *args: None

        def close(self):
            actions.append("closed")
            return {}

    def observe():
        actions.append("observed")
        if observer_fails:
            raise RuntimeError("observer failed")

    def collect(target, role, output, **kwargs):
        actions.append("collected-" + role)
        if not observer_fails:
            raise ValueError("collection sentinel")

    monkeypatch.setattr(run, "Manager", Manager)
    monkeypatch.setattr(run, "drive", lambda *args: actions.append("completed"))
    monkeypatch.setattr(run, "collect", collect)
    root = tmp_path / "out"
    error, message = (RuntimeError, "observer failed") if observer_fails else (ValueError, "collection sentinel")
    with pytest.raises(error, match=message):
        run.execute(config(), root, before_collection=observe)
    assert actions == ["completed", "closed", "observed", "collected-source", "collected-destination"]
    assert (root / "failure.json").exists() and (root / "checksums.sha256").exists()


def test_invalid_pre_collection_observer_rejected_before_creation(tmp_path):
    from scripts.performance import linux_native_finite_run as run

    root = tmp_path / "out"
    with pytest.raises(ValueError, match="invalid pre-collection observer"):
        run.execute(config(), root, before_collection=True)
    assert not root.exists()
