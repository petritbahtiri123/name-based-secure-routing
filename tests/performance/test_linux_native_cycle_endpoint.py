import importlib
import io
import json
import time
from types import SimpleNamespace

import pytest

from scripts.performance import linux_native_lifecycle as native
from scripts.performance import linux_native_lifecycle_endpoint as endpoint


def test_cycle_parser_has_no_offered_rate_or_fanout_contract():
    module = importlib.import_module('scripts.performance.linux_native_cycle_endpoint')
    parser = module.argument_parser()
    argv = ['--role', 'source', '--binaries', '/bin', '--build-manifest', '/build',
        '--authority', '/private/auth', '--lifecycle', '/private/cycles', '--output', '/out',
        '--bind', '192.0.2.1:0', '--cycles', '4']
    args = parser.parse_args(argv)
    assert args.cycles == 4 and args.count is None and args.rate is None and args.shards is None
    with pytest.raises(SystemExit):
        parser.parse_args(argv + ['--rate', '100'])


def test_cycle_control_starts_only_when_requested_after_readiness(tmp_path):
    module = importlib.import_module('scripts.performance.linux_native_cycle_endpoint')
    root, peer, output = (tmp_path / n for n in ('private', 'peer', 'output'))
    for path in (root, peer, output):
        path.mkdir()
    args = SimpleNamespace(role='source', cycles=2, lifecycle=root, output=peer,
        bind='192.0.2.1:0', ready_input=tmp_path / 'ready.json', destination_address='192.0.2.2')
    state = module.CycleEndpointControl(args, output, capture=lambda: {})
    with pytest.raises(ValueError, match='readiness'):
        state.request(dict(op='start', cycle=0))
    assert not list(root.iterdir())
    (peer / 'source-prepared.json').write_text(json.dumps(dict(status='PREPARED_NOT_CONNECTED')))
    assert state.poll() == [dict(event='prepared')]
    state.request(dict(op='readiness', value=dict(endpoint='192.0.2.2:4000', alpn='nbsr-quic-1')))
    assert state.request(dict(op='start', cycle=0)) == [dict(event='started', cycle=0)]
    assert {p.name for p in root.iterdir()} == {'connection-0.start'}


def test_cycle_eof_cancels_owned_delegate_without_prestarting_cycles(tmp_path, monkeypatch):
    module = importlib.import_module('scripts.performance.linux_native_cycle_endpoint')
    authority, lifecycle = tmp_path / 'authority', tmp_path / 'lifecycle'
    authority.mkdir()
    lifecycle.mkdir()
    (lifecycle / '00').mkdir()
    args = SimpleNamespace(role='source', cycles=2, count=None, output=tmp_path / 'public',
        lifecycle=lifecycle, authority=authority, ready_input=None,
        destination_address='192.0.2.2', bind='192.0.2.1:0', prepare_before_readiness=False)
    cleaned = []
    def delegate(args, *, check_cancelled):
        assert args.count == 2 and not list(lifecycle.glob('*.start'))
        try:
            for _ in range(100):
                check_cancelled()
                time.sleep(.002)
            pytest.fail('EOF did not cancel cycle delegate')
        finally:
            cleaned.append(True)
    monkeypatch.setattr(endpoint.platform, 'system', lambda: 'Linux')
    with pytest.raises(InterruptedError, match='EOF'):
        module.execute_endpoint(args, input_stream=io.BytesIO(), output_stream=io.StringIO(), delegate=delegate)
    assert cleaned == [True]
    assert (args.output / 'failure.json').is_file()
    assert (args.output / 'checksums.sha256').is_file()
    assert not (args.output / 'result.json').exists()


def test_cycle_workload_dispatch_retains_explicit_mode(tmp_path):
    args = SimpleNamespace(role='source', cycles=2, count=2, shards=None, rate=None)
    argv, env = native.workload_command(args, binaries=tmp_path, authority=tmp_path,
        lifecycle=tmp_path, output=tmp_path, bind='192.0.2.1:0', endpoint='192.0.2.2:4000')
    assert argv[argv.index('--connections') + 1] == '2'
    assert '--lifecycle-clients' not in argv and not env


@pytest.mark.parametrize('wire', [b'{"op":"start","cycle":true}', b'{"op":"start","cycle":16}',
    b'{"op":"release"}', b'{"op":"cancel","cycle":0}', b'{"op":"readiness","value":[]}'])
def test_cycle_control_bad_frames_reject(wire):
    module = importlib.import_module('scripts.performance.linux_native_cycle_endpoint')
    with pytest.raises(ValueError):
        module.decode_cycle_control(wire)
