import json
from types import SimpleNamespace

import pytest

from scripts.performance import linux_native_lifecycle as native
from scripts.performance import linux_native_lifecycle_endpoint as endpoint_module
from scripts.performance.linux_native_lifecycle_endpoint import EndpointControl


def endpoint(tmp_path, role='source'):
    root = tmp_path / 'out'
    root.mkdir()
    peer = root / 'peer'
    peer.mkdir()
    lifecycle = tmp_path / 'lifecycle'
    lifecycle.mkdir()
    args = SimpleNamespace(role=role, count=16, lifecycle=lifecycle, output=peer,
        ready_input=root / 'transferred-readiness.json' if role == 'source' else None,
        destination_address='192.0.2.2' if role == 'source' else None,
        bind='192.0.2.1:0' if role == 'source' else '192.0.2.2:0')
    control = EndpointControl(args, root, capture=lambda: None)
    return control, args, root


def test_source_requires_preparation_and_valid_fresh_readiness(tmp_path):
    control, args, root = endpoint(tmp_path)
    message = dict(op='readiness', value=dict(endpoint='192.0.2.2:1234', alpn='nbsr-quic-1'))
    with pytest.raises(ValueError, match='prepared'):
        control.request(message)
    (args.output / 'source-prepared.json').write_text('{')
    assert control.poll() == []
    (args.output / 'source-prepared.json').write_text(json.dumps(dict(status='PREPARED_NOT_CONNECTED')))
    assert control.poll() == [dict(event='prepared')]
    with pytest.raises(ValueError, match='address/ALPN'):
        control.request(dict(op='readiness', value=dict(endpoint='192.0.2.3:1234', alpn='nbsr-quic-1')))
    assert not args.ready_input.exists()
    assert control.request(message) == [dict(event='readiness_transferred')]
    assert json.loads(args.ready_input.read_text()) == message['value']
    with pytest.raises(ValueError, match='once'):
        control.request(message)
    assert control.poll() == []


def test_readiness_transfer_does_not_overwrite_stale_input(tmp_path):
    control, args, _ = endpoint(tmp_path)
    (args.output / 'source-prepared.json').write_text(json.dumps(dict(status='PREPARED_NOT_CONNECTED')))
    control.poll()
    args.ready_input.write_text('stale')
    with pytest.raises(ValueError, match='fresh'):
        control.request(dict(op='readiness', value=dict(endpoint='192.0.2.2:1234', alpn='nbsr-quic-1')))
    assert args.ready_input.read_text() == 'stale'


def test_destination_emits_validated_readiness_once(tmp_path):
    control, args, _ = endpoint(tmp_path, 'destination')
    ready = dict(endpoint='192.0.2.2:4321', alpn='nbsr-quic-1')
    (args.output / 'ready.json').write_text(json.dumps(ready))
    assert control.poll() == [dict(event='ready', value=ready)]
    assert control.poll() == []
    with pytest.raises(ValueError, match='source only'):
        control.request(dict(op='readiness', value=ready))


def test_cancel_command_interrupts_delegate(tmp_path):
    control, _, _ = endpoint(tmp_path)
    with pytest.raises(InterruptedError, match='control cancellation'):
        control.request(dict(op='cancel'))


@pytest.mark.parametrize('wrong_pid', [True, False], ids=['wrong-pid', 'duplicate-socket'])
def test_socket_snapshot_requires_matching_sample_and_unique_inodes(tmp_path, monkeypatch, wrong_pid):
    control, args, _ = endpoint(tmp_path)
    (args.output / 'pid.json').write_text(json.dumps(dict(pid=123)))
    (args.output / 'resources.ndjson').write_text(json.dumps(dict(pid=456 if wrong_pid else 123, start_ticks=4)) + '\n')
    (args.output / 'command.json').write_text(json.dumps(dict(argv=['taskset', '--cpu-list', '0', '/bin/source'])))
    monkeypatch.setattr(endpoint_module, 'snapshot', lambda *a: dict(status='MEASURED_LIVE_SOCKET_SNAPSHOT',
        sockets=[dict(inode=7, local=['192.0.2.1', 1234])] * 16))
    monkeypatch.setattr(endpoint_module, 'validate_binding', lambda *a, **kw: None)
    with pytest.raises(ValueError, match='identity|unique'):
        control.capture()


def test_existing_native_parser_is_shared_without_changing_cli_contract():
    args = native.argument_parser().parse_args(['--role', 'source', '--binaries', '/bins',
        '--build-manifest', '/build.json', '--authority', '/private/tls', '--lifecycle', '/private/lifecycle',
        '--output', '/out', '--bind', '192.0.2.1:0', '--prepare-before-readiness'])
    assert args.role == 'source' and args.prepare_before_readiness and args.count == 16


def test_input_reader_preserves_frames_and_reports_eof():
    import io
    import queue

    messages = queue.Queue(maxsize=8)
    endpoint_module.read_commands(io.BytesIO(b'{"op":"release"}\n{"op":"cancel"}\n'), messages)
    assert messages.get_nowait() == b'{"op":"release"}\n'
    assert messages.get_nowait() == b'{"op":"cancel"}\n'
    assert messages.get_nowait() is None


@pytest.mark.parametrize('wire', [None, b'{"op":"cancel"}\n', b'{"op":"release"}', b'x' * 65537],
                         ids=['eof', 'cancel', 'unterminated', 'oversized'])
def test_control_reader_errors_interrupt_the_delegate(tmp_path, wire):
    import queue
    import threading

    control, _, _ = endpoint(tmp_path)
    messages, errors, emitted = queue.Queue(maxsize=8), [], []
    messages.put(wire)
    endpoint_module.watch_control(control, messages, emitted.append, threading.Event(), errors)
    assert len(errors) == 1 and isinstance(errors[0], (ValueError, InterruptedError))
    assert not emitted


def test_control_eof_uses_existing_delegate_cancellation_and_preserves_failure(tmp_path, monkeypatch):
    import io
    import time

    authority, lifecycle = tmp_path / 'authority', tmp_path / 'lifecycle'
    authority.mkdir()
    lifecycle.mkdir()
    (lifecycle / '00').mkdir()
    args = SimpleNamespace(role='source', count=16, output=tmp_path / 'public', lifecycle=lifecycle,
        authority=authority, ready_input=None, destination_address='192.0.2.2',
        bind='192.0.2.1:0', prepare_before_readiness=False)
    cleaned = []

    def delegate(args, *, check_cancelled):
        try:
            for _ in range(100):
                check_cancelled()
                time.sleep(.002)
            pytest.fail('EOF did not cancel delegate')
        finally:
            cleaned.append(True)

    monkeypatch.setattr(endpoint_module.platform, 'system', lambda: 'Linux')
    with pytest.raises(InterruptedError, match='EOF'):
        endpoint_module.execute_endpoint(args, input_stream=io.BytesIO(), output_stream=io.StringIO(), delegate=delegate)
    assert cleaned == [True]
    assert (args.output / 'failure.json').is_file() and (args.output / 'checksums.sha256').is_file()
    assert not (args.output / 'result.json').exists()
