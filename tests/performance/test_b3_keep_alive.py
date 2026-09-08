import pytest

from scripts import run_b3_session_lifecycle as b3
from scripts import run_b3_v2 as v2


def test_keep_alive_bundles_are_a_distinct_workload():
    idle = v2.spec_for('bundles', 1024, 1)
    live = v2.spec_for('live-bundles', 1024, 1)
    assert idle.get('keep_alive_seconds', 0) == 0
    assert live['keep_alive_seconds'] == 1
    assert live['name'] != idle['name']
    assert live['kind'] == idle['kind'] == 'sessions'
    assert live['sessions'] == idle['sessions'] == 1024
    assert 'keepalive' in live['resource_scope']


@pytest.mark.parametrize('path,kind,interval', [
    ('go-rust', 'sessions', 1),
    ('rust-rust', 'streams', 1),
    ('rust-rust', 'sessions', 2),
    ('rust-rust', 'sessions', True),
])
def test_invalid_keep_alive_spec_fails_before_artifacts(tmp_path, path, kind, interval):
    spec = {**v2.spec_for('bundles', 16, 1), 'kind': kind, 'keep_alive_seconds': interval}
    with pytest.raises(ValueError, match='keepalive'):
        b3.run_cell(path, spec, {}, tmp_path, idle_seconds=2, active_seconds=2,
                    cooldown_seconds=2, cadence=.5)
    assert not list(tmp_path.iterdir())
