import json

import pytest

from scripts.performance.linux_native_lifecycle_control import LifecycleBarrier, decode_control


def barrier(tmp_path, role='source'):
    root, output = tmp_path / 'markers', tmp_path / 'output'
    root.mkdir()
    output.mkdir()
    now = [0]
    captures = []

    def capture():
        captures.append(True)
        return dict(status='MEASURED_LIVE_SOCKET_SNAPSHOT', sockets=[{}] * (16 if role == 'source' else 1))

    value = LifecycleBarrier(role=role, count=16, root=root, output=output,
                             capture=capture, clock=lambda: now[0])
    return value, root, now, captures


def mark_active(root, role='source', count=16):
    prefix = 'connection' if role == 'source' else 'destination'
    for i in range(count):
        (root / f'{prefix}-{i}.active').write_text('active')


def test_complete_named_set_and_full_hold_are_required_before_release(tmp_path):
    state, root, now, captures = barrier(tmp_path)
    mark_active(root, count=15)
    assert state.poll() == [] and not captures
    with pytest.raises(ValueError, match='all active'):
        state.request('release')
    (root / 'connection-15.active').write_text('active')
    assert state.poll() == [dict(event='active', count=16)]
    assert captures == [True]
    now[0] = 1_999_999_999
    with pytest.raises(ValueError, match='hold'):
        state.request('release')
    assert not list(root.glob('*.release'))
    now[0] = 2_000_000_000
    assert state.request('release') == [dict(event='released', count=16)]
    assert len(list(root.glob('*.release'))) == 16
    assert state.request('release') == []
    assert state.poll() == [] and captures == [True]


def test_source_ack_requires_release_and_all_named_acks(tmp_path):
    state, root, now, _ = barrier(tmp_path)
    mark_active(root)
    state.poll()
    (root / 'connection-0.ack').write_text('ack')
    with pytest.raises(ValueError, match='ACK before release'):
        state.poll()
    (root / 'connection-0.ack').unlink()
    now[0] = 2_000_000_000
    state.request('release')
    for i in range(15):
        (root / f'connection-{i}.ack').write_text('ack')
    assert state.poll() == []
    (root / 'connection-15.ack').write_text('ack')
    assert state.poll() == [dict(event='acked', count=16)]


def test_destination_cooldown_and_wrong_role_operations(tmp_path):
    state, root, now, _ = barrier(tmp_path, 'destination')
    mark_active(root, 'destination')
    state.poll()
    with pytest.raises(ValueError, match='report ready'):
        state.request('report_release')
    now[0] = 2_000_000_000
    state.request('release')
    (root / 'destination.report-ready').write_text('ready')
    assert state.poll() == [dict(event='report_ready')]
    now[0] += 1_999_999_999
    with pytest.raises(ValueError, match='cooldown'):
        state.request('report_release')
    now[0] += 1
    assert state.request('report_release') == [dict(event='report_released')]
    assert (root / 'destination.report-release').read_text() == 'release\n'
    assert state.request('report_release') == []


@pytest.mark.parametrize('name', ['connection-0.failed', 'destination-0.failed'])
def test_failure_markers_prevent_progress(tmp_path, name):
    state, root, _, _ = barrier(tmp_path)
    mark_active(root)
    (root / name).write_text('failure')
    with pytest.raises(ValueError, match='failed marker'):
        state.poll()


def test_extra_active_marker_and_stale_release_reject(tmp_path):
    state, root, now, _ = barrier(tmp_path)
    mark_active(root)
    (root / 'connection-16.active').write_text('unexpected')
    with pytest.raises(ValueError, match='unexpected active'):
        state.poll()
    (root / 'connection-16.active').unlink()
    state.poll()
    now[0] = 2_000_000_000
    (root / 'connection-0.release').write_text('stale')
    with pytest.raises(FileExistsError):
        state.request('release')
    assert (root / 'connection-0.release').read_text() == 'stale'


def test_source_cannot_release_destination_report(tmp_path):
    state, _, _, _ = barrier(tmp_path)
    with pytest.raises(ValueError, match='destination only'):
        state.request('report_release')


@pytest.mark.parametrize('value', [dict(op='release'), dict(op='report_release'), dict(op='cancel'),
    dict(op='readiness', value=dict(endpoint='192.0.2.2:1234', alpn='nbsr-quic-1'))])
def test_control_messages(value):
    assert decode_control(json.dumps(value).encode()) == value


@pytest.mark.parametrize('wire', [b'', b'[]', b'null', b'{', b'{"op":"unknown"}',
    b'{"op":"release","extra":1}', b'{"op":"readiness"}',
    b'{"op":"readiness","value":[]}', b'{"op":"release","op":"cancel"}',
    b'{"op":"readiness","value":{"x":NaN}}', b'x' * 65537],
    ids=['empty', 'array', 'null', 'partial', 'unknown', 'extra', 'missing-value',
         'wrong-value', 'duplicate', 'nonfinite', 'oversized'])
def test_invalid_control_messages_reject(wire):
    with pytest.raises(ValueError):
        decode_control(wire)
