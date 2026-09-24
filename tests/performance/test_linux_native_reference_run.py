import copy
import json

import pytest

from tests.performance.test_linux_native_reference import reference
from tests.performance.test_linux_native_pair import SHA
from tests.performance.test_linux_native_finite_run import config


def inputs(tmp_path, effect=1):
    root = tmp_path / 'reference'
    root.mkdir()
    manifest = reference(root, effect=effect)
    value = config()
    value.update(source_sha=SHA, path='nbsr', streams=64)
    value['source']['bind'] = '192.0.2.10:0'
    value['destination']['bind'] = '192.0.2.11:0'
    return value, manifest


def test_cli_defers_signal_and_passes_cancellation_into_owned_runner(tmp_path, monkeypatch):
    import signal
    import sys
    from scripts.performance import linux_native_reference_run as run
    config_path = tmp_path / 'config.json'
    config_path.write_text('{}')
    monkeypatch.setattr(sys, 'argv', ['runner', '--config', str(config_path), '--reference', 'reference.json',
        '--percent', '75', '--seconds', '60', '--output', str(tmp_path / 'out')])
    def execute(*args, **kwargs):
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler), 'CLI must own deferred cancellation'
        handler(signal.SIGTERM, None)
        kwargs['check_cancelled']()
        pytest.fail('cancellation not delivered')
    monkeypatch.setattr(run, 'execute', execute)
    with pytest.raises(InterruptedError, match='SIGTERM'):
        run.main()


def test_rate_uses_one_verified_snapshot_before_launch(tmp_path, monkeypatch):
    from scripts.performance import linux_native_reference_run as run
    from scripts.performance import linux_native_reference as reference_module
    value, manifest = inputs(tmp_path)
    original = reference_module.analyze_reference
    calls = []
    def analyze(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(run, 'analyze_reference', analyze)
    monkeypatch.setattr(reference_module, 'analyze_reference', analyze)
    def runner(*args, **kwargs):
        assert len(calls) == 1, 'rate and retained analysis must use one verified snapshot'
        raise RuntimeError('stop after preflight')
    with pytest.raises(RuntimeError, match='stop after preflight'):
        run.execute(value, manifest, percent=75, seconds=60, output=tmp_path / 'out', runner=runner)


def test_unqualified_reference_prevents_launch_and_output_creation(tmp_path):
    from scripts.performance.linux_native_reference_run import execute
    value, manifest = inputs(tmp_path, effect=.8)
    output = tmp_path / 'out'
    with pytest.raises(ValueError):
        execute(value, manifest, percent=75, seconds=3600, output=output,
                runner=lambda *a, **k: pytest.fail('launched from rejected reference'))
    assert not output.exists()


@pytest.mark.parametrize('fault', ['rate', 'source', 'shape', 'bind', 'percent', 'duration'])
def test_reference_contract_mismatch_prevents_launch(tmp_path, fault):
    from scripts.performance.linux_native_reference_run import execute
    value, manifest = inputs(tmp_path)
    percent, seconds = 75, 3600
    if fault == 'rate':
        value['diagnostic_rate'] = [1, 1]
    elif fault == 'source':
        value['source_sha'] = 'b' * 40
    elif fault == 'shape':
        value['streams'] = 8
    elif fault == 'bind':
        value['source']['bind'] = '192.0.2.20:0'
    elif fault == 'percent':
        percent = 81
    else:
        seconds = 61
    with pytest.raises(ValueError):
        execute(value, manifest, percent=percent, seconds=seconds, output=tmp_path / 'out',
                runner=lambda *a, **k: pytest.fail('launched invalid contract'))


@pytest.mark.parametrize('fault', [None, 'placement', 'run-failure', 'reference-change'])
def test_derived_rate_and_actual_placement_are_bound_without_stable_claim(tmp_path, fault):
    from scripts.performance.linux_native_reference_run import execute
    from scripts.performance.linux_native_pair import verify_index
    value, manifest = inputs(tmp_path)
    original = copy.deepcopy(value)
    def runner(config, output, **kwargs):
        from scripts.performance.linux_b5_placement import seal_output
        assert config['diagnostic_rate'] == [15, 4]
        assert config['diagnostic_seconds'] == 60
        assert config['source_live_guard'] and config['paired_live_guards'] and config['post_close_reports']
        output.mkdir()
        if fault == 'run-failure':
            (output / 'partial.txt').write_text('preserved')
            raise RuntimeError('measured failure')
        for role in ('source', 'destination'):
            root = output / role / 'peer'
            root.mkdir(parents=True)
            env = json.loads((manifest.parent / 'observer' / 'on-1' / role / 'environment.json').read_bytes())
            if fault == 'placement' and role == 'source':
                env['linux_environment']['selected_cpus'] = [1]
            (root / 'environment.json').write_text(json.dumps(env))
        seal_output(output)
        if fault == 'reference-change':
            manifest.write_bytes(manifest.read_bytes() + b'\n')
        return dict(status='PASS_CONTROLLED_FINITE_PAIR', sustained_capacity='NOT_ESTABLISHED')
    output = tmp_path / 'out'
    if fault:
        with pytest.raises((ValueError, RuntimeError)):
            execute(value, manifest, percent=75, seconds=60, output=output, runner=runner)
        assert (output / 'failure.json').exists() and not (output / 'result.json').exists()
    else:
        result = execute(value, manifest, percent=75, seconds=60, output=output, runner=runner)
        assert result['classification'] == 'REFERENCE_BOUND_DIAGNOSTIC'
        assert result['sustained_capacity'] == 'NOT_ESTABLISHED'
        assert result['live_observer_qualification'] == 'NOT_ESTABLISHED'
    assert value == original
    verify_index(output)
