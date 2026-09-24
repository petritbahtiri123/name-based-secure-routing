import io
import json
from types import SimpleNamespace

import pytest

from scripts.performance import linux_native_finite_endpoint as endpoint
from scripts.performance.linux_native_pair import verify_index


def args(tmp_path, role):
    return SimpleNamespace(
        role=role,
        output=tmp_path / "out",
        authority=tmp_path / "private",
        ready_input=None,
        phase_control=None,
        destination_address="192.0.2.2" if role == "source" else None,
        bind="192.0.2.1:0" if role == "source" else "192.0.2.2:0",
    )


def test_source_eof_seals_failure_without_starting_child(tmp_path, monkeypatch):
    monkeypatch.setattr(endpoint.platform, "system", lambda: "Linux")
    monkeypatch.setattr(endpoint, "read_commands", lambda stream, messages, stop: messages.put(None))
    item = args(tmp_path, "source")
    with pytest.raises(InterruptedError, match="EOF"):
        endpoint.execute_endpoint(
            item, input_stream=io.BytesIO(), output_stream=io.StringIO(), delegate=lambda *a, **k: pytest.fail("child after EOF")
        )
    assert (item.output / "failure.json").exists()
    assert not (item.output / "result.json").exists()
    verify_index(item.output)


def test_preexisting_root_is_never_published_or_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(endpoint.platform, "system", lambda: "Linux")
    item = args(tmp_path, "source")
    item.output.mkdir()
    secret = item.output / "untouched"
    secret.write_text("preserve")
    output = io.StringIO()
    with pytest.raises(FileExistsError):
        endpoint.execute_endpoint(item, input_stream=io.BytesIO(), output_stream=output)
    assert output.getvalue() == "" and secret.read_text() == "preserve"
    assert {p.name for p in item.output.iterdir()} == {"untouched"}


def test_destination_ack_precedes_success_and_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(endpoint.platform, "system", lambda: "Linux")

    def reader(stream, messages, stop):
        messages.put(b'{"op":"ack"}\n')

    monkeypatch.setattr(endpoint, "read_commands", reader)

    def delegate(item, check_cancelled):
        item.output.mkdir()
        (item.output / "ready.json").write_text(json.dumps(dict(endpoint="192.0.2.2:4444", alpn="nbsr-quic-1")))
        check_cancelled()
        assert (item.output / "completion.ack").exists()
        return dict(exit_code=0)

    output = io.StringIO()
    item = args(tmp_path, "destination")
    endpoint.execute_endpoint(item, input_stream=io.BytesIO(), output_stream=output, delegate=delegate)
    assert [json.loads(line)["event"] for line in output.getvalue().splitlines()] == ["owned", "ready", "acked", "complete"]
    verify_index(item.output)


def test_cancellation_propagates_into_owned_delegate(tmp_path, monkeypatch):
    monkeypatch.setattr(endpoint.platform, "system", lambda: "Linux")
    monkeypatch.setattr(endpoint, "read_commands", lambda stream, messages, stop: messages.put(b'{"op":"cancel"}\n'))

    def delegate(item, check_cancelled):
        try:
            check_cancelled()
        finally:
            (item.output.parent / "delegated-cleanup").write_text("owned cleanup reached")

    item = args(tmp_path, "destination")
    with pytest.raises(InterruptedError):
        endpoint.execute_endpoint(item, input_stream=io.BytesIO(), output_stream=io.StringIO(), delegate=delegate)
    assert (item.output / "delegated-cleanup").exists()
    assert not (item.output / "result.json").exists()
    verify_index(item.output)
