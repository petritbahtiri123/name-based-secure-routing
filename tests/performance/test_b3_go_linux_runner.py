import hashlib
import json
from types import SimpleNamespace
import pytest
from scripts import run_b3_v2 as runner
from scripts import run_b3_session_lifecycle as lifecycle


def test_go_binary_roles_are_explicit():
    assert runner.binary_names("linux", "go-rust") == {"go": "nbsr-go-peer", "server": "wp8_interop_server"}
    assert runner.binary_names("windows", "go-rust") == {"go": "nbsr-go-peer.exe", "server": "wp8_interop_server.exe"}
    assert runner.binary_names("linux") == {"rust": "perf_rust_source", "server": "wp8_interop_server"}


def test_go_manifest_cannot_pass_as_rust(tmp_path):
    binaries = {role: tmp_path / name for role, name in {"go": "nbsr-go-peer", "server": "wp8_interop_server"}.items()}
    for path in binaries.values():
        path.write_bytes(b"release")
    manifest = dict(
        source_sha="a" * 40,
        build_profile="release",
        build_commands=["build"],
        toolchains={"go": "pinned", "rust": "pinned"},
        binary_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in binaries.values()},
    )
    path = tmp_path / "build.json"
    path.write_text(json.dumps(manifest))
    assert runner.validate_linux_manifest(path, binaries, "go-rust") == manifest
    with pytest.raises(ValueError):
        runner.validate_linux_manifest(path, binaries)


@pytest.mark.parametrize(
    "axis,materialized,allocator",
    [("bundles", False, False), ("live-bundles", False, False), ("streams", True, False), ("cycles", False, True)],
)
def test_go_port_rejects_unsupported_workloads(axis, materialized, allocator):
    args = SimpleNamespace(axis=axis, materialized_streams=materialized, allocator_snapshots=allocator)
    with pytest.raises(ValueError):
        runner.go_specs(args, [{"sessions": 1}])


def test_go_cycles_preserve_count_and_require_completion():
    args = SimpleNamespace(axis="cycles", materialized_streams=False, allocator_snapshots=False)
    specs = [runner.spec_for("cycles", 50, 1)]
    prepared = runner.go_specs(args, specs)
    assert prepared[0]["destination_completion"] is True
    assert prepared[0]["cycles"] == 50 and prepared[0]["streams"] == 64
    assert prepared[0]["start_rate"] == 0
    assert "destination_completion" not in specs[0]


def test_linux_go_requires_barrier_and_report_gated_exit():
    assert lifecycle.capture_contract("go-rust", {"sessions": 1, "destination_completion": True}, True) == (True, True)
    with pytest.raises(ValueError):
        lifecycle.capture_contract("go-rust", {"sessions": 1}, True)
    assert lifecycle.capture_contract("go-rust", {"sessions": 1}, False) == (False, False)
    assert lifecycle.capture_contract("rust-rust", {"sessions": 1}, True) == (True, False)
    assert lifecycle.capture_contract("rust-rust", {"sessions": 2}, True) == (True, True)
