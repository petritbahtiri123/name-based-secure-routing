from pathlib import Path

import pytest

from scripts.performance.linux_loopback import sample_process


@pytest.mark.parametrize('tid', [123, 124])
@pytest.mark.parametrize('filename', ['status', 'children'])
@pytest.mark.parametrize('error', [ProcessLookupError, PermissionError])
def test_thread_exit_does_not_hide_leader_or_permission_failure(tmp_path, monkeypatch, tid, filename, error):
    process = tmp_path / '123'
    for thread in (123, 124):
        task = process / 'task' / str(thread)
        task.mkdir(parents=True)
        (task / 'status').write_text('Cpus_allowed_list:\t0\n')
        (task / 'children').write_text('')
    (process / 'fd').mkdir()
    (process / 'stat').write_text('123 (peer) S ' + '0 ' * 49)
    original = Path.read_text

    def read(path, *args, **kwargs):
        if path == process / 'task' / str(tid) / filename:
            raise error('injected disappearing thread')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', read)
    if tid == 123 or error is PermissionError:
        with pytest.raises(error):
            sample_process(123, [0], tmp_path, 100, 4096)
    else:
        assert sample_process(123, [0], tmp_path, 100, 4096)['thread_ids'] == [123]
