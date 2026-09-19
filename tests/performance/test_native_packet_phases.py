import pytest

from tests.performance.test_native_packet_markers import PROBE, analyze, marker
from tests.performance.test_linux_native_packet_accounting import CLIENT, SERVER, frame


NAMES = ('setup-complete', 'measurement-start', 'measurement-stop')
PHASE_PROBE = PROBE | {'phase_tokens': dict(zip(NAMES, ('11' * 32, '22' * 32, '33' * 32)))}


def phase(name):
    return frame((CLIENT[0], 43000), (SERVER[0], 44000), bytes.fromhex(PHASE_PROBE['phase_tokens'][name]))


def packets():
    return [marker(), frame(), phase(NAMES[0]), frame(), phase(NAMES[1]),
            frame(), frame(SERVER, CLIENT), phase(NAMES[2]), frame(SERVER, CLIENT), marker(True)]


def test_phase_windows_reconcile_without_claiming_pure_measurement():
    result = analyze(packets(), PHASE_PROBE)
    assert [v['packet_count'] for v in result['phase_windows'].values()] == [1, 1, 2, 1]
    for field in ('packet_count', 'ip_bytes', 'udp_bytes', 'udp_payload_bytes', 'captured_frame_bytes'):
        assert sum(v[field] for v in result['phase_windows'].values()) == result[field]
    assert result['pure_measured_operations_only'] == 'NOT_PROVEN'
    assert result['setup_vs_established'] == 'MEASURED_MARKER_WINDOWS'
    assert result['probe_packet_count'] == 5


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'reordered', 'before-start', 'after-end', 'token-collision'])
def test_incomplete_or_ambiguous_phases_reject(fault):
    rows, probe = packets(), PHASE_PROBE
    if fault == 'missing':
        del rows[4]
    elif fault == 'duplicate':
        rows.insert(3, phase(NAMES[0]))
    elif fault == 'reordered':
        rows[2], rows[4] = rows[4], rows[2]
    elif fault == 'before-start':
        rows.insert(0, rows.pop(2))
    elif fault == 'after-end':
        rows.append(rows.pop(7))
    else:
        probe = PROBE | {'phase_tokens': PHASE_PROBE['phase_tokens'] | {NAMES[0]: PROBE['token_hex']}}
    with pytest.raises(ValueError):
        analyze(rows, probe)
