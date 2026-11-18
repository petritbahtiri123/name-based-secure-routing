"""Owner request/readiness binding only; no sockets or active viewer writes."""
from pathlib import Path
import json

import pytest

from scripts.performance.reader_viewer_binding import attachment_arguments


def values(tmp_path):
    root = tmp_path / 'successor'
    output = root / 'live-lab' / 'receiver-command'
    request = dict(argv=['python', '-B', str(root / 'finite_receiver.py'),
                         'worker', str(output / 'request.json')],
                   output=str(output), started=11., work_deadline=180.,
                   cleanup_deadline=185., trial_anchor=10.)
    ready = dict(run='new-run', deadline=185., port=8766)
    return root, request, ready


def test_binds_existing_publisher_without_renewing_anchor(tmp_path):
    root, request, ready = values(tmp_path)
    result = attachment_arguments(root, 'new-run', request, ready, now=20., python='python')
    assert result == ('new-run', 10., root / 'live-lab/viewer-qualification.json')


@pytest.mark.parametrize('field,value', [('trial_anchor', True), ('trial_anchor', float('nan')),
    ('output', 'other'), ('argv', ['other']), ('parent_end', 186.)])
def test_bad_request_rejected(tmp_path, field, value):
    root, request, ready = values(tmp_path)
    request[field] = value
    with pytest.raises(ValueError):
        attachment_arguments(root, 'new-run', request, ready, now=20., python='python')


@pytest.mark.parametrize('field,value', [('run', 'old-run'), ('port', 8765), ('deadline', 186.)])
def test_wrong_ready_rejected(tmp_path, field, value):
    root, request, ready = values(tmp_path)
    ready[field] = value
    with pytest.raises(ValueError):
        attachment_arguments(root, 'new-run', request, ready, now=20., python='python')


@pytest.mark.parametrize('now', [9., 125., float('inf'), True])
def test_stale_viewer_window_not_extended_to_receiver_window(tmp_path, now):
    root, request, ready = values(tmp_path)
    with pytest.raises(ValueError):
        attachment_arguments(root, 'new-run', request, ready, now=now, python='python')


def test_relative_root_rejected(tmp_path):
    _, request, ready = values(tmp_path)
    with pytest.raises(ValueError):
        attachment_arguments(Path('relative'), 'new-run', request, ready, now=20., python='python')


def test_actual_existing_publisher_consumes_bound_arguments(tmp_path):
    root, request, ready = values(tmp_path)
    args = attachment_arguments(root, 'new-run', request, ready, now=20., python='python')
    source = Path(__file__).with_name('fixtures') / 'viewer_owner_attachment.py.snapshot'
    ns = {'__name__': 'offline_publisher'}
    exec(compile(source.read_bytes(), str(source), 'exec'), ns)
    published = ns['publish'](tmp_path, *args, now=20.)
    assert published['published']
    value = json.loads((tmp_path / 'active-attachment.json').read_bytes())
    assert value == dict(run='new-run', trial_anchor=10., deadline=125.,
                        qualification_path=str(root / 'live-lab/viewer-qualification.json'))
    assert set(p.name for p in tmp_path.iterdir()) == {'active-attachment.json'}


def test_ci_selects_binding():
    from scripts.ci.check import command_groups
    assert any('tests/performance/test_reader_viewer_binding.py' in c.argv
               for c in command_groups('python-core'))
