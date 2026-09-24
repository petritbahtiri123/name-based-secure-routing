import json
from types import SimpleNamespace

import pytest


def wire(role, event, **extra):
    return (json.dumps(dict(schema="nbsr-native-finite-control-v1", role=role, event=event, timestamp_ns=1, **extra)) + "\n").encode()


def test_finite_ledger_rejects_early_complete_and_early_eof():
    from scripts.performance.linux_native_finite_control import FiniteLedger

    ledger = FiniteLedger()
    with pytest.raises(ValueError):
        ledger.accept("source", wire("source", "complete"))
    ledger.accept("source", wire("source", "owned"))
    with pytest.raises(InterruptedError):
        ledger.eof("source")
    ledger.accept("source", wire("source", "readiness_transferred"))
    ledger.accept("source", wire("source", "complete"))
    ledger.eof("source")
    with pytest.raises(ValueError):
        ledger.accept("source", wire("source", "complete"))


@pytest.mark.parametrize("change", [dict(role="destination"), dict(timestamp_ns=True), dict(extra=1), dict(schema="wrong")])
def test_event_fields_are_strict(change):
    from scripts.performance.linux_native_finite_control import FiniteLedger

    event = json.loads(wire("source", "owned"))
    event.update(change)
    with pytest.raises(ValueError):
        FiniteLedger().accept("source", json.dumps(event).encode())


def test_ack_follows_source_validation_and_zero_relay_exit():
    from scripts.performance.linux_native_finite_control import drive

    actions = []
    ready = dict(value=dict(endpoint="192.0.2.2:4567", alpn="nbsr-quic-1"))

    def wait(role, event):
        actions.append(("wait", role, event))
        return ready

    drive(
        lambda role: actions.append(("start", role)),
        wait,
        lambda role, value: actions.append(("send", role, value["op"])),
        lambda role: actions.append(("finish", role)),
    )
    assert actions.index(("finish", "source")) < actions.index(("send", "destination", "ack"))
    assert actions.index(("wait", "source", "owned")) < actions.index(("start", "destination"))


def test_manager_accepts_explicit_bounded_event_ledger(tmp_path):
    from scripts.performance.linux_native_lifecycle_coordinator import Manager

    ledger = SimpleNamespace(received={}, positions={})
    manager = Manager(None, tmp_path, ledger=ledger)
    try:
        assert manager.ledger is ledger
    finally:
        manager.close()


def test_finite_parser_can_be_shared_without_changing_defaults():
    from scripts.performance.linux_native_peer import argument_parser

    args = argument_parser().parse_args(
        [
            "--role",
            "source",
            "--path",
            "direct",
            "--binaries",
            "/bin",
            "--build-manifest",
            "/build.json",
            "--authority",
            "/tls",
            "--output",
            "/out",
            "--bind",
            "192.0.2.1:0",
        ]
    )
    assert args.cores == 1 and args.streams == 64 and args.depth == 1


def test_destination_ack_is_exclusive_and_only_after_ready(tmp_path):
    from scripts.performance.linux_native_finite_control import FiniteControl

    args = SimpleNamespace(role="destination", output=tmp_path, bind="192.0.2.2:0")
    control = FiniteControl(args)
    with pytest.raises(ValueError):
        control.request(dict(op="ack"))
    (tmp_path / "ready.json").write_text(json.dumps(dict(endpoint="192.0.2.2:1234", alpn="nbsr-quic-1")))
    assert control.poll()[0]["event"] == "ready"
    assert control.request(dict(op="ack")) == [dict(event="acked")]
    with pytest.raises(ValueError):
        control.request(dict(op="ack"))
    assert (tmp_path / "completion.ack").exists()


def test_source_readiness_rejects_wrong_address_and_overwrite(tmp_path):
    from scripts.performance.linux_native_finite_control import FiniteControl

    args = SimpleNamespace(role="source", output=tmp_path, ready_input=tmp_path / "input.json", destination_address="192.0.2.2")
    control = FiniteControl(args)
    with pytest.raises(ValueError):
        control.request(dict(op="readiness", value=dict(endpoint="192.0.2.3:42", alpn="nbsr-quic-1")))
    args.ready_input.write_text("stale")
    with pytest.raises(FileExistsError):
        control.request(dict(op="readiness", value=dict(endpoint="192.0.2.2:42", alpn="nbsr-quic-1")))
    assert args.ready_input.read_text() == "stale"


def test_source_relay_failure_never_authorizes_destination_ack():
    from scripts.performance.linux_native_finite_control import drive
    sent = []
    def finish(role):
        assert role == 'source'
        raise RuntimeError('nonzero source relay')
    with pytest.raises(RuntimeError, match='nonzero'):
        drive(lambda role: None, lambda *args: dict(value={}),
              lambda role, value: sent.append((role, value)), finish)
    assert sent == [('source', dict(op='readiness', value={}))]
