from types import SimpleNamespace
import json
import pytest
from scripts.performance import linux_native_peer as peer
from scripts.performance import native_debug_correctness as debug
from scripts.performance.linux_native_pair import analyze_pair
from scripts.performance.linux_b5_placement import seal_output
from tests.performance.test_linux_native_pair import fixture, put, SHA
from tests.performance.test_linux_native_post_close import enable_reports


def test_current_debug_rejection_before_execution(tmp_path, monkeypatch):
    bins = tmp_path / "bins"
    bins.mkdir()
    for name in peer.NAMES.values():
        (bins / name).write_bytes(b"fake executable")
    manifest = tmp_path / "build.json"
    manifest.write_text(
        json.dumps(
            dict(
                source_sha="a" * 40,
                build_profile="debug",
                binary_sha256={n: peer.digest(bins / n) for n in peer.NAMES.values()},
                build_commands=["cargo build --locked --offline"],
                toolchains={"rust": "fixture"},
            )
        )
    )
    monkeypatch.setattr(peer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(peer, "git_state", lambda: ("a" * 40, ""))
    monkeypatch.setattr(peer.os, "environ", {})

    class NoSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def bind(self, *args):
            pass

    monkeypatch.setattr(peer.socket, "socket", lambda *a: NoSocket())
    monkeypatch.setattr(peer.subprocess, "Popen", lambda *a, **k: pytest.fail("unexpected process"))
    args = SimpleNamespace(
        output=tmp_path / "out",
        authority=tmp_path / "unused-private",
        binaries=bins,
        bind="127.0.0.1:0",
        role="destination",
        ready_input=None,
        destination_address=None,
        build_manifest=manifest,
    )
    with pytest.raises(ValueError, match="release build manifest"):
        peer.execute(args)
    assert not args.output.exists()


def build_manifest(hashes):
    return dict(
        schema="nbsr-debug-correctness-build-v1",
        source_sha="b" * 40,
        runtime_source_sha=SHA,
        build_profile="debug",
        binary_sha256=hashes,
        build_commands=["cargo build --locked --offline --features benchmark-harness"],
        toolchains={"rust": "fixture"},
        evidence_class=debug.CLASS,
        source_sha256=dict.fromkeys(
            ("crates/nbsr-transport/Cargo.toml", "crates/nbsr-transport/Cargo.lock", "crates/nbsr-transport/src/lib.rs", *debug.FIXTURES),
            "c" * 64,
        ),
    )


def debug_pair(tmp_path):
    source, destination = fixture(tmp_path)
    hashes = json.loads((source / "environment.json").read_text())["binary_sha256"]
    build = build_manifest(hashes)
    pin = debug.manifest_digest(build)
    for role, root in [("source", source), ("destination", destination)]:
        enable_reports(root, role)
        env = json.loads((root / "environment.json").read_text())
        env["cell"]["streams"] = 2
        env.update(debug.qualification(pin))
        put(root, "environment.json", env)
        put(root, "build-manifest.json", build)
        result = json.loads((root / "result.json").read_text())
        result.update(debug.qualification(pin), status=debug.status("PASS_FINITE_PEER", pin))
        result.pop("application_gbps", None)
        put(root, "result.json", result)
        command = json.loads((root / "command.json").read_text())
        if role == "source":
            command["argv"][command["argv"].index("--p2a-streams") + 1] = "2"
            row = json.loads((root / "validated-result.json").read_text())
            row["streams"] = 2
            put(root, "validated-result.json", row)
            put(root, "stdout", row)
        else:
            command["environment_overrides"]["NBSR_P2A_STREAMS"] = "2"
            put(root, "server-result.json", dict(status="PASS", streams=2))
        put(root, "command.json", command)
        seal_output(root)
    return source, destination, pin


def test_debug_pair_requires_explicit_pin_and_never_reports_goodput(tmp_path):
    source, destination, pin = debug_pair(tmp_path)
    with pytest.raises(ValueError, match="release build manifest"):
        analyze_pair(source, destination, source_sha=SHA)
    result = analyze_pair(source, destination, source_sha=SHA, debug_correctness_manifest_sha256=pin)
    assert result["status"] == "PASS_FINITE_PAIR_INTEGRITY_DEBUG_CORRECTNESS"
    assert result["throughput_benchmark"] == result["capacity_benchmark"] == "INELIGIBLE"
    assert "application_gbps" not in result


@pytest.mark.parametrize("fault", ["pin", "binary", "runtime-sha", "build-sha", "inventory", "commands", "profile"])
def test_debug_manifest_rejects_provenance_drift(fault):
    hashes = dict.fromkeys(peer.NAMES.values(), "d" * 64)
    build = build_manifest(hashes)
    pin = debug.manifest_digest(build)
    actual = build["source_sha256"].copy()
    if fault == "pin":
        pin = "e" * 64
    elif fault == "binary":
        hashes = hashes | {"perf_rust_source": "e" * 64}
    elif fault == "runtime-sha":
        build["runtime_source_sha"] = "e" * 40
    elif fault == "build-sha":
        build["source_sha"] = True
    elif fault == "inventory":
        actual["crates/nbsr-transport/Cargo.lock"] = "e" * 64
    elif fault == "commands":
        build["build_commands"] = []
    elif fault == "profile":
        build["build_profile"] = "release"
    if fault in ("runtime-sha", "build-sha", "commands", "profile"):
        pin = debug.manifest_digest(build)  # Exercise semantic validation even with a matching digest.
    with pytest.raises(ValueError):
        debug.validate_build(build, SHA, hashes, pin, actual_source=actual)


@pytest.mark.parametrize("fault", ["throughput", "claim", "mixed", "cleanup", "binary", "manifest"])
def test_debug_pair_rejects_resealed_invalid_evidence(tmp_path, fault):
    source, destination, pin = debug_pair(tmp_path)
    if fault in ("throughput", "claim", "mixed"):
        result = json.loads((source / "result.json").read_text())
        if fault == "throughput":
            result["application_gbps"] = 1
        elif fault == "claim":
            result["throughput_benchmark"] = "PASS"
        else:
            result.pop(debug.FIELD)
        put(source, "result.json", result)
    elif fault == "cleanup":
        row = json.loads((source / "cleanup.json").read_text())
        row["ownership"]["quic_connections_current_live"] = 1
        put(source, "cleanup.json", row)
    elif fault == "binary":
        (source / "executed-binary").write_bytes(b"wrong binary")
    else:
        build = json.loads((source / "build-manifest.json").read_text())
        build["build_commands"] = ["changed command"]
        put(source, "build-manifest.json", build)
    seal_output(source)
    with pytest.raises(ValueError):
        analyze_pair(source, destination, source_sha=SHA, debug_correctness_manifest_sha256=pin)


def test_config_and_both_endpoint_commands_require_explicit_bounded_mode():
    from scripts.performance.linux_native_finite_run import validate_config, endpoint_arguments
    from tests.performance.test_linux_native_finite_run import config

    value = config() | dict(path="nbsr", streams=2, post_close_reports=True, debug_correctness_manifest_sha256="a" * 64)
    validate_config(value)
    for role in ("source", "destination"):
        argv = endpoint_arguments(value, role)
        assert argv[argv.index("--debug-correctness-manifest-sha256") + 1] == "a" * 64
    for key, wrong in [
        ("streams", 3),
        ("depth", 2),
        ("path", "direct"),
        ("post_close_reports", False),
        (debug.FIELD, None),
        (debug.FIELD, True),
    ]:
        with pytest.raises(ValueError):
            validate_config(value | {key: wrong})


def test_debug_manifest_accepts_exact_source_and_rejects_inventory_omissions():
    hashes = dict.fromkeys(peer.NAMES.values(), "d" * 64)
    build = build_manifest(hashes)
    actual = build["source_sha256"].copy()
    pin = debug.manifest_digest(build)
    debug.validate_build(build, SHA, hashes, pin, actual_source=actual)
    actual["crates/nbsr-transport/src/additional.rs"] = "f" * 64
    with pytest.raises(ValueError, match="current source inventory"):
        debug.validate_build(build, SHA, hashes, pin, actual_source=actual)


def test_debug_long_diagnostic_and_invalid_manifest_inventory_rejected():
    cell = dict(path="nbsr", streams=2, outstanding=1, cores=1, diagnostic_seconds=60)
    with pytest.raises(ValueError, match="short two-stream"):
        debug.validate_workload(cell, True, "a" * 64)
    hashes = dict.fromkeys(peer.NAMES.values(), "d" * 64)
    for name in ("../secret", "crates/nbsr-transport/../secret"):
        build = build_manifest(hashes)
        build["source_sha256"][name] = "c" * 64
        with pytest.raises(ValueError, match="source inventory"):
            debug.validate_build(build, SHA, hashes, debug.manifest_digest(build))


def test_debug_sequence_preserves_distinct_success_and_interruption_cleanup():
    from tests.performance.test_local_container_sequence import setup

    mod, cells, engine, sequence = setup()
    for cell in cells:
        cell.config[debug.FIELD] = "a" * 64

    def runner(plan):
        if plan.interrupt:
            return mod.Outcome("INVALID_PARTIAL", plan.owners)
        return mod.Outcome(debug.status("PASS_CONTROLLED_FINITE_PAIR", "a" * 64))

    results = sequence.run(cells, runner, original_disk_free_bytes=10 * 2**30)
    assert [r.status for r in results] == [
        "PASS_CONTROLLED_FINITE_PAIR_DEBUG_CORRECTNESS",
        "INVALID_PARTIAL",
        "PASS_CONTROLLED_FINITE_PAIR_DEBUG_CORRECTNESS",
    ]
    assert all(r.accepted and r.cleanup_confirmed for r in results)
    assert not engine.live and not sequence.controller.owned


def test_windows_bound_adapter_rejects_release_success_for_debug_request(tmp_path, monkeypatch):
    from dataclasses import replace
    from tests.performance.test_windows_native_management import bound_plan
    from scripts.performance import windows_native_management as management

    plan = bound_plan(False)
    config = json.loads(plan.config_json)
    config[debug.FIELD] = "a" * 64
    plan = replace(plan, config_json=json.dumps(config).encode())
    monkeypatch.setattr(management.finite, "execute", lambda *a, **k: {"status": "PASS_CONTROLLED_FINITE_PAIR"})
    with pytest.raises(management.Unconfirmed, match="unexpected coordinator"):
        management.execute_bound(plan, tmp_path / "unused", check_cancelled=lambda: None)
    monkeypatch.setattr(management.finite, "execute", lambda *a, **k: {"status": "PASS_CONTROLLED_FINITE_PAIR_DEBUG_CORRECTNESS"})
    result = management.execute_bound(plan, tmp_path / "unused", check_cancelled=lambda: None)
    assert result.status == "PASS_CONTROLLED_FINITE_PAIR_DEBUG_CORRECTNESS"
