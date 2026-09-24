import pytest

from scripts.performance import linux_native_lifecycle_control as control


def make(tmp_path, role='source', cycles=2):
    root, output = tmp_path / 'private', tmp_path / 'public'
    root.mkdir()
    output.mkdir()
    now = [0]
    state = control.CycleBarrier(role=role, cycles=cycles, root=root, output=output,
        capture=lambda: dict(status='MEASURED_LIVE_SOCKET_SNAPSHOT', sockets=[{}]),
        clock=lambda: now[0])
    return state, root, output, now


def active(state, root, now, cycle, role='source'):
    state.request('start', cycle)
    prefix = 'connection' if role == 'source' else 'destination'
    (root / f'{prefix}-{cycle}.active').write_text('active')
    assert state.poll() == [dict(event='active', cycle=cycle)]
    now[0] += 2_000_000_000
    assert state.request('release', cycle) == [dict(event='released', cycle=cycle)]


def test_two_source_cycles_keep_markers_and_require_cooldown(tmp_path):
    state, root, output, now = make(tmp_path)
    active(state, root, now, 0)
    (root / 'connection-0.ack').write_text('ack')
    assert state.poll() == [dict(event='acked', cycle=0)]
    with pytest.raises(ValueError, match='cooldown'):
        state.request('start', 1)
    now[0] += 2_000_000_000
    active(state, root, now, 1)
    assert (root / 'connection-0.active').exists()
    assert (output / 'socket-binding-0.json').exists()
    assert (output / 'socket-binding-1.json').exists()
    (root / 'connection-1.ack').write_text('ack')
    assert state.poll() == [dict(event='acked', cycle=1)]
    with pytest.raises(ValueError, match='cooldown'):
        state.request('final_release', 1)
    now[0] += 2_000_000_000
    assert state.request('final_release', 1) == [dict(event='final_released', cycle=1)]
    assert (root / 'source.final-release').read_text() == 'release\n'


def test_destination_final_report_requires_final_cycle_and_cooldown(tmp_path):
    state, root, _, now = make(tmp_path, 'destination', 1)
    active(state, root, now, 0, 'destination')
    (root / 'destination.report-ready').write_text('ready')
    assert state.poll() == [dict(event='report_ready', cycle=0)]
    with pytest.raises(ValueError, match='cooldown'):
        state.request('final_release', 0)
    now[0] += 2_000_000_000
    assert state.request('final_release', 0) == [dict(event='final_released', cycle=0)]
    assert (root / 'destination.report-release').is_file()


@pytest.mark.parametrize('cycle', [True, -1, 1, 2, '0'])
def test_invalid_or_skipped_start_rejects(tmp_path, cycle):
    state, root, _, _ = make(tmp_path)
    with pytest.raises(ValueError):
        state.request('start', cycle)
    assert not list(root.iterdir())


def test_early_release_duplicate_start_and_early_ack_reject(tmp_path):
    state, root, _, now = make(tmp_path)
    state.request('start', 0)
    with pytest.raises(ValueError):
        state.request('start', 0)
    with pytest.raises(ValueError):
        state.request('release', 0)
    (root / 'connection-0.active').write_text('active')
    state.poll()
    with pytest.raises(ValueError, match='hold'):
        state.request('release', 0)
    (root / 'connection-0.ack').write_text('ack')
    with pytest.raises(ValueError, match='ACK before release'):
        state.poll()
    assert now[0] == 0


@pytest.mark.parametrize('name', ['connection-1.active', 'connection-0.failed', 'destination-0.active'])
def test_unexpected_markers_fail_closed(tmp_path, name):
    state, root, _, _ = make(tmp_path)
    state.request('start', 0)
    (root / name).write_text('unexpected')
    with pytest.raises(ValueError):
        state.poll()


def test_destination_cannot_start_next_without_cooldown(tmp_path):
    state, root, _, now = make(tmp_path, 'destination')
    active(state, root, now, 0, 'destination')
    with pytest.raises(ValueError, match='cooldown'):
        state.request('start', 1)
    now[0] += 2_000_000_000
    assert state.request('start', 1) == [dict(event='started', cycle=1)]


def test_missing_previous_marker_cannot_be_hidden_by_advancing(tmp_path):
    state, root, _, now = make(tmp_path)
    active(state, root, now, 0)
    (root / 'connection-0.ack').write_text('ack')
    state.poll()
    now[0] += 2_000_000_000
    (root / 'connection-0.active').unlink()
    with pytest.raises(ValueError, match='retained'):
        state.request('start', 1)


@pytest.mark.parametrize('role,marker', [('source', 'connection-0.ack'), ('destination', 'destination.report-ready')])
def test_premature_completion_between_poll_and_release_rejects(tmp_path, role, marker):
    state, root, _, now = make(tmp_path, role, 1)
    state.request('start', 0)
    prefix = 'connection' if role == 'source' else 'destination'
    (root / f'{prefix}-0.active').write_text('active')
    state.poll()
    now[0] += 2_000_000_000
    (root / marker).write_text('premature')
    with pytest.raises(ValueError):
        state.request('release', 0)
    assert not (root / 'connection-0.release').exists()
