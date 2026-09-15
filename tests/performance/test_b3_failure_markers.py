import os

from scripts.performance.b3_failure_markers import snapshot_markers


def test_preserves_only_marker_metadata_without_reading_contents(tmp_path):
    marker = tmp_path / 'connection-7.connected'
    marker.write_text('must not enter evidence')
    os.utime(marker, ns=(123000000000, 124000000000))
    (tmp_path / 'private-key.pem').write_text('excluded')
    (tmp_path / 'connection-8.active').mkdir()
    result = snapshot_markers(tmp_path)
    assert result['markers'] == [{'name': marker.name, 'mtime_ns': 124000000000, 'size_bytes': 23}]
    assert result['status'] == 'CAPTURED'
    assert 'must not enter evidence' not in str(result)


def test_missing_directory_is_diagnostic_unavailable(tmp_path):
    result = snapshot_markers(tmp_path / 'missing')
    assert result['status'] == 'UNAVAILABLE'
    assert result['error_type'] == 'FileNotFoundError'


def test_known_phases_and_deterministic_order(tmp_path):
    names = ['destination-2.active', 'connection-2.ack', 'connection-2.start',
             'connection-2.connected', 'connection-2.active', 'connection-2.release']
    for name in names:
        (tmp_path / name).touch()
    assert [m['name'] for m in snapshot_markers(tmp_path)['markers']] == sorted(names)
