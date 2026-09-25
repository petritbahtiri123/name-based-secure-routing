"""A successful role inside a failed pair still requires raw peer validation."""
import ast
import json
from pathlib import Path

import pytest

from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.linux_native_lifecycle_pair import check_peer
from tests.performance.test_linux_native_lifecycle_pair import peers, SHA, write


def individual_verifier():
    path = Path('evidence/performance/v2/native-live2048-mib-8945c77a/analyze.py')
    tree = ast.parse(path.read_text(encoding='utf-8'))
    functions = ast.Module(body=[v for v in tree.body if isinstance(v, ast.FunctionDef)], type_ignores=[])
    namespace = dict(check_peer=check_peer)
    exec(compile(functions, str(path), 'exec'), namespace)
    return namespace['verified_individual_peer']


@pytest.mark.parametrize('tamper', [False, True])
def test_individual_role_replays_payload_and_ownership(tmp_path, tamper):
    source, _ = peers(tmp_path)
    env = json.loads((source / 'environment.json').read_bytes())
    env['bundle_mode'] = 'live-bundles'
    write(source, 'environment.json', env)
    command = json.loads((source / 'command.json').read_bytes())
    command['argv'] += ['--b3-keep-alive-seconds', '1']
    write(source, 'command.json', command)
    if tamper:
        result = json.loads((source / 'result.json').read_bytes())
        result['ownership']['transport_sessions_current_live'] = 1
        write(source, 'result.json', result)
    seal_output(source)
    verify = individual_verifier()
    if tamper:
        with pytest.raises(ValueError):
            verify(source, 'source', SHA, 16)
    else:
        assert verify(source, 'source', SHA, 16)
