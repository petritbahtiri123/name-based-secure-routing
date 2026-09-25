from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import run_b3_session_lifecycle as runner


def test_linux_go_waits_for_existing_runtime_file():
    paths, clients = [Path('runtime.ndjson')], [object()]
    with patch.object(runner, 'wait_paths') as wait:
        runner.wait_source_initialization('go-rust', True, paths, clients)
    wait.assert_called_once_with(paths, clients, 30)


@pytest.mark.parametrize(('path', 'linux'), [('rust-rust', True), ('go-rust', False)])
def test_other_paths_do_not_add_gate(path, linux):
    with patch.object(runner, 'wait_paths') as wait:
        runner.wait_source_initialization(path, linux, [], [])
    wait.assert_not_called()


def test_initialization_failure_is_not_suppressed():
    with patch.object(runner, 'wait_paths', side_effect=TimeoutError('startup')):
        with pytest.raises(TimeoutError, match='startup'):
            runner.wait_source_initialization('go-rust', True, [Path('runtime')], [object()])
