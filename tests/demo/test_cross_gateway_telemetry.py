import asyncio
import importlib.util
import json
import os
import ssl
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/demo/cross_gateway_telemetry.py"
spec = importlib.util.spec_from_file_location("cross_gateway_telemetry", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
run_scenario = module.run_scenario


@pytest.mark.parametrize("scenario,count,terminal", [
    ("allowed", 1, ("client", "response_received")),
    ("policy_denied_b", 0, ("gateway_b", "policy_denied")),
    ("gateway_b_unavailable", 0, ("gateway_a", "connect_failed")),
])
def test_live_two_gateways(scenario, count, terminal, capsys, caplog, monkeypatch):
    private_values = []
    wire_writes = []
    processes = []
    original_start = module.GatewayProcess.start

    async def observed_start(gateway, *args, **kwargs):
        ready = await original_start(gateway, *args, **kwargs)
        processes.append(gateway.process)
        return ready

    monkeypatch.setattr(module.GatewayProcess, "start", observed_start)
    original = module.handshake
    original_write = asyncio.StreamWriter.write

    def record_write(writer, data):
        wire_writes.append(bytes(data))
        return original_write(writer, data)

    monkeypatch.setattr(asyncio.StreamWriter, "write", record_write)

    def record_handshake(*args):
        value = original(*args)
        private_values.extend(value[field] for field in ("binding", "proof", "nonce", "route_id", "hostname"))
        return value

    monkeypatch.setattr(module, "handshake", record_handshake)
    result = asyncio.run(run_scenario(scenario))
    assert len(processes) == 2
    assert len({os.getpid(), *(process.pid for process in processes)}) == 3
    assert all(process.returncode == 0 for process in processes)
    assert result["status"] == "PASS"
    assert result["service_requests"] == count
    assert result["service_connections"] == count
    assert result["response_verified"] is (count == 1)
    assert result["cleanup"] == {"listeners": 0, "tasks": 0, "connections": 0, "processes": 0}
    assert result["processes"] == {"gateways_started": 2, "distinct": True, "gateways_exited": 2}
    assert result["trace_id_leaks"] == 0
    events = result["trace"]
    assert result["correlation"] == "HARNESS_ONLY"
    identities = {}
    for event in events:
        identities.setdefault(event["component"], set()).add(event["local_trace_id"])
        assert "request_id" not in event
    assert all(len(values) == 1 for values in identities.values())
    assert len(set.union(*identities.values())) == len(identities)
    wire_bytes = b"".join(wire_writes)
    assert not any(local_id.encode() in wire_bytes for local_id in set.union(*identities.values()))
    for component in identities:
        local_events = [event for event in events if event["component"] == component]
        assert [event["sequence"] for event in local_events] == list(range(1, len(local_events) + 1))
    stages = [(event["component"], event["stage"]) for event in events]
    assert terminal in stages
    assert ("gateway_a", "admission_allowed") in stages
    if count:
        assert stages.index(("gateway_b", "admission_allowed")) < stages.index(("gateway_b", "connected"))
        assert ("service", "request_received") in stages
        assert result["tls"] == ["gateway_a", "gateway_b"]
    else:
        assert ("service", "request_received") not in stages
        assert ("client", "response_received") not in stages
    if scenario == "policy_denied_b":
        assert ("gateway_b", "connect_started") not in stages
    if scenario == "gateway_b_unavailable":
        assert not any(component == "gateway_b" for component, _ in stages)
        assert result["tls"] == ["gateway_a"]
    captured = capsys.readouterr()
    rendered = json.dumps(result) + captured.out + captured.err + caplog.text
    for private_value in private_values:
        assert private_value not in rendered
    for forbidden in ("127.0.0.", "localhost", ".test", "PRIVATE KEY", "eyJ", "nonce", "binding", "proof"):
        assert forbidden not in rendered


def test_cli_is_repeatable_and_emits_only_public_json():
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=root, capture_output=True, text=True, timeout=55,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    report = json.loads(completed.stdout)
    assert report["scope"] == "LIVE_LOOPBACK_PYTHON_RELAY_FIXTURE"
    assert len(report["results"]) == 3
    per_case = [{event["local_trace_id"] for event in item["trace"]} for item in report["results"]]
    assert sum(map(len, per_case)) == len(set.union(*per_case))
    assert all(item["status"] == "PASS" for item in report["results"])


def test_trace_rejects_unstructured_events():
    trace = module.Trace("gateway_a", [])
    with pytest.raises(ValueError, match="diagnostic event"):
        trace.emit("secret-or-private-destination")
    assert trace.events == []


def test_gateway_does_not_correlate_a_different_handshake():
    settings = module.route_settings("gateway_a", "gateway-b.test")
    expected = module.handshake(settings, "gateway-b.test")
    trace = module.Trace("gateway_a", [])
    relay = module.ObservedRelay(trace=trace, expected=expected, settings=settings)
    changed = {**expected, "nonce": "unrelated"}
    with pytest.raises(module.RelayRejected, match="diagnostic handshake"):
        relay._verify_admission(changed)
    assert trace.events == []
    # Exact diagnostic matching does not authorize an invalid signed proof.
    invalid = {**expected, "proof": "invalid"}
    relay.expected = invalid
    from nbsr.security import SecurityError
    with pytest.raises(SecurityError):
        relay._verify_admission(invalid)
    assert trace.events == []


def test_tls_identity_is_checked_and_temporary_keys_are_removed(tmp_path):
    async def check():
        server_context, trusted, _ = module.tls_contexts(tmp_path, "gateway-b.test")
        _, unrelated, _ = module.tls_contexts(tmp_path, "unrelated.test")
        assert list(tmp_path.iterdir()) == []
        assert trusted.check_hostname and trusted.verify_mode == ssl.CERT_REQUIRED
        assert trusted.minimum_version == trusted.maximum_version == ssl.TLSVersion.TLSv1_3
        server = await asyncio.start_server(lambda _r, w: w.close(), "127.0.0.1", 0, ssl=server_context)
        try:
            port = server.sockets[0].getsockname()[1]
            for context, hostname in ((trusted, "wrong.test"), (unrelated, "gateway-b.test")):
                with pytest.raises(ssl.SSLCertVerificationError):
                    await asyncio.wait_for(asyncio.open_connection(
                        "127.0.0.1", port, ssl=context, server_hostname=hostname), timeout=2)
        finally:
            server.close()
            await server.wait_closed()
    asyncio.run(check())


def test_cancellation_cleans_owned_connections(monkeypatch):
    async def check():
        initial = asyncio.all_tasks()
        entered = asyncio.Event()
        processes = []
        original_start = module.GatewayProcess.start

        async def blocked_start(self, *args, **kwargs):
            await original_start(self, *args, **kwargs)
            processes.append(self.process)
            entered.set()
            await asyncio.Future()

        monkeypatch.setattr(module.GatewayProcess, "start", blocked_start)
        trial = asyncio.create_task(run_scenario("allowed"))
        await asyncio.wait_for(entered.wait(), timeout=3)
        trial.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(trial, timeout=10)
        assert processes and all(process.returncode == 0 for process in processes)
        assert asyncio.all_tasks() == initial
    asyncio.run(check())


def test_supervisor_failure_does_not_print_private_exception(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    async def timeout():
        raise TimeoutError("secret-token private-origin")

    monkeypatch.setattr(module, "run_all", timeout)
    assert module.main() == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {"status": "FAIL", "stage": "trial_or_cleanup", "cleanup": "UNCONFIRMED"}


def test_supervisor_cancels_stalled_work(monkeypatch):
    cancelled = []

    async def stalled():
        try:
            await asyncio.Future()
        finally:
            cancelled.append(True)

    monkeypatch.setattr(module, "SUPERVISOR_SECONDS", 0.01)
    monkeypatch.setattr(module, "run_all", stalled)
    with pytest.raises(TimeoutError):
        asyncio.run(module.supervised_run())
    assert cancelled == [True]


def test_unexpected_gateway_death_fails_and_reaps_both(monkeypatch):
    processes = []
    original_start = module.GatewayProcess.start

    async def killing_start(self, *args, **kwargs):
        ready = await original_start(self, *args, **kwargs)
        processes.append(self.process)
        if self.component == "gateway_a":
            processes[0].kill()
            await processes[0].wait()
        return ready

    monkeypatch.setattr(module.GatewayProcess, "start", killing_start)
    with pytest.raises(module.TrialFailure):
        asyncio.run(run_scenario("allowed"))
    assert len(processes) == 2
    assert all(process.returncode is not None for process in processes)


def test_unresponsive_owned_worker_is_killed_and_reaped():
    async def check():
        worker = module.GatewayProcess("gateway_b")
        worker.process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "import time; time.sleep(30)",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        with pytest.raises(TimeoutError):
            await worker.close()
        assert worker.process.returncode is not None
        assert worker.receipt is None
    asyncio.run(check())


@pytest.mark.parametrize("failure", ["cancel", "timeout"])
def test_failed_client_close_still_reaps_gateways(monkeypatch, failure):
    async def check():
        entered = asyncio.Event()
        processes = []
        original_start = module.GatewayProcess.start
        original_close = module.NameRelay._close_writer

        async def observed_start(self, *args, **kwargs):
            ready = await original_start(self, *args, **kwargs)
            processes.append(self.process)
            return ready

        async def stalled_close(writer):
            if writer.get_extra_info("ssl_object") is not None and not entered.is_set():
                writer.close()
                entered.set()
                await asyncio.Future()
            await original_close(writer)

        monkeypatch.setattr(module.GatewayProcess, "start", observed_start)
        monkeypatch.setattr(module.NameRelay, "_close_writer", stalled_close)
        trial = asyncio.create_task(run_scenario("allowed"))
        try:
            await asyncio.wait_for(entered.wait(), timeout=10)
            if failure == "cancel":
                trial.cancel()
            expected = asyncio.CancelledError if failure == "cancel" else TimeoutError
            # Aborting TLS may also make a gateway report unconfirmed cleanup;
            # either way this must fail, and both processes must be reaped.
            with pytest.raises((expected, module.TrialFailure)):
                await asyncio.wait_for(trial, timeout=10)
            assert len(processes) == 2
            assert all(process.returncode is not None for process in processes)
        finally:
            # The RED run must not leave the reproduced orphan processes behind.
            if not trial.done():
                trial.cancel()
                await asyncio.gather(trial, return_exceptions=True)
            for process in processes:
                if process.returncode is None:
                    process.kill()
                await process.wait()
    asyncio.run(check())


@pytest.mark.parametrize("index,visible", [
    (0, "[Service OK]"), (1, "[B DENIED]"), (2, "[B UNREACHABLE]"),
])
def test_terminal_view_distinguishes_expected_block_from_test_failure(index, visible):
    report = json.loads((ROOT / "docs/demo/p1-cross-gateway-telemetry-example.json").read_text())
    result = report["results"][index]
    result["private_debug"] = "secret-token private-origin.test"
    rendered = module.render_terminal_case(result, color=True)
    assert visible in rendered
    assert "\x1b[32m[PASS]" in rendered
    assert ("\x1b[31m" in rendered) is (index != 0)
    assert "secret-token" not in rendered and "private-origin" not in rendered
    plain = module.render_terminal_case(result, color=False)
    assert "\x1b[" not in plain
    assert "[PASS]" in plain


def test_terminal_color_auto_respects_redirection_and_no_color(monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    assert module.terminal_color_enabled("auto") is False
    assert module.terminal_color_enabled("always") is True
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("NO_COLOR", "")
    assert module.terminal_color_enabled("auto") is False
    assert module.terminal_color_enabled("never") is False


def test_terminal_failure_is_red_without_private_details(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--format", "terminal", "--color", "always"])

    async def failure(*args, **kwargs):
        raise RuntimeError("secret-token private-origin.test")

    monkeypatch.setattr(module, "supervised_run", failure)
    assert module.main() == 1
    output = capsys.readouterr().out
    assert "\x1b[31m[FAIL]" in output
    assert "[PASS]" not in output
    assert "UNCONFIRMED" in output
    assert "secret-token" not in output and "private-origin" not in output


def test_terminal_cli_runs_all_three_live_cases():
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--format", "terminal", "--color", "never"],
        cwd=ROOT, capture_output=True, text=True, timeout=55,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert completed.stdout.count("[PASS]") == 3
    assert "[B DENIED]" in completed.stdout and "[B UNREACHABLE]" in completed.stdout
    assert "\x1b[" not in completed.stdout
    assert "127.0.0." not in completed.stdout


def test_explicit_json_remains_raw_even_with_color_always(monkeypatch, capsys):
    report = json.loads((ROOT / "docs/demo/p1-cross-gateway-telemetry-example.json").read_text())

    async def completed():
        return report

    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--format", "json", "--color", "always"])
    monkeypatch.setattr(module, "supervised_run", completed)
    assert module.main() == 0
    output = capsys.readouterr().out
    assert "\x1b[" not in output
    assert json.loads(output) == report


@pytest.mark.parametrize("interactive", [True, False])
def test_default_view_follows_console_and_preserves_redirected_json(monkeypatch, capsys, interactive):
    report = json.loads((ROOT / "docs/demo/p1-cross-gateway-telemetry-example.json").read_text())
    async def completed(on_result=None):
        if on_result:
            for result in report["results"]:
                on_result(result)
        return report
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    monkeypatch.setattr(sys.stdout, "isatty", lambda: interactive)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(module, "supervised_run", completed)
    assert module.main() == 0
    output = capsys.readouterr().out
    if interactive:
        assert output.count("+----------------------------+") == 24
        assert output.count("[PASS]") == 3
    else:
        assert json.loads(output) == report


def test_box_diagram_fits_narrow_console_and_marks_unattempted_link():
    report = json.loads((ROOT / "docs/demo/p1-cross-gateway-telemetry-example.json").read_text())
    output = module.render_terminal_case(report["results"][2], color=False)
    assert "              X\n              v" in output
    assert "              :\n              v" in output
    assert max(map(len, output.splitlines())) <= 80


@pytest.mark.skipif(os.name != "nt", reason="Windows console API")
def test_windows_vt_is_enabled_and_original_mode_restored(monkeypatch):
    import ctypes
    from unittest.mock import Mock
    from ctypes import wintypes

    kernel = Mock()
    kernel.GetStdHandle.return_value = 123
    def get_mode(handle, pointer):
        ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD)).contents.value = 1
        return 1
    kernel.GetConsoleMode.side_effect = get_mode
    kernel.SetConsoleMode.return_value = 1
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: kernel)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    restore = module.enable_windows_ansi()
    kernel.SetConsoleMode.assert_called_once_with(123, 5)
    restore()
    assert kernel.SetConsoleMode.call_args.args == (123, 1)
