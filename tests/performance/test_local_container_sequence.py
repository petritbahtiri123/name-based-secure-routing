"""Three-cell management flow with deterministic engine and workload adapters."""
from copy import deepcopy
import importlib
import json
from pathlib import Path

import pytest

from scripts.performance.local_container_disposal import Container, Observation, Unconfirmed


class Engine:
    def __init__(self):
        self.live = {}
        self.count = 0
        self.fail_id = None

    def create(self, request):
        self.count += 1
        owner = Container(request.run, request.role, f'{self.count:064x}', True)
        self.live[owner.container_id] = owner
        return owner

    def remove(self, container_id):
        if container_id == self.fail_id:
            raise OSError('injected removal failure')
        self.live.pop(container_id)

    def observe(self, probe):
        return Observation(probe, self.live.get(probe.container.container_id))


def setup():
    name = 'scripts.performance.local_container_sequence'
    assert importlib.util.find_spec(name) is not None, 'sequence contract not implemented'
    mod = importlib.import_module(name)
    config = json.loads(Path('docs/benchmarks/sphere-offline-20261012/'
                             'finite-two-stream.synthetic.json').read_text())
    cells = []
    for run in ('normal', 'interrupted', 'fresh'):
        value = deepcopy(config)
        for role in ('source', 'destination'):
            value[role]['output'] = f'/evidence/{run}/{role}'
        cells.append(mod.Cell(run, value, f'/configs/{run}.json', f'/controller/{run}'))
    engine = Engine()
    return mod, cells, engine, mod.Sequence(engine)


def test_normal_interrupted_invalid_partial_then_fresh():
    mod, cells, engine, sequence = setup()
    seen = []

    def runner(plan):
        assert len(engine.live) == 2
        assert {o.run for o in engine.live.values()} == {plan.run}
        assert all(o in engine.live.values() for o in plan.owners)
        assert 'scripts.performance.linux_native_watchdog' in plan.watchdog_command
        assert '--original-disk-free-bytes' in plan.watchdog_command
        assert 'scripts.performance.linux_native_finite_run' in plan.worker_command
        output = plan.watchdog_command[plan.watchdog_command.index('--output') + 1]
        assert plan.worker_command[-1] == output + '/worker'
        assert json.loads(plan.config_json)['streams'] == 2
        seen.append(plan)
        return mod.Outcome('INVALID_PARTIAL', plan.owners) if plan.interrupt else mod.Outcome(
            'PASS_CONTROLLED_FINITE_PAIR')

    results = sequence.run(cells, runner, original_disk_free_bytes=10 * 2**30)
    assert [row.status for row in results] == [
        'PASS_CONTROLLED_FINITE_PAIR', 'INVALID_PARTIAL', 'PASS_CONTROLLED_FINITE_PAIR']
    assert [plan.interrupt for plan in seen] == [False, True, False]
    assert len({owner.container_id for plan in seen for owner in plan.owners}) == 6
    assert not engine.live
    assert not sequence.controller.owned
    assert len([event for event in sequence.controller.events if event[0] == 'released']) == 3
    with pytest.raises(Unconfirmed):
        sequence.run(cells, runner, original_disk_free_bytes=10 * 2**30)


def test_cleanup_failure_blocks_fresh_but_attempts_other_role():
    mod, cells, engine, sequence = setup()
    seen = []

    def runner(plan):
        seen.append(plan.run)
        if plan.interrupt:
            engine.fail_id = plan.owners[0].container_id
        return mod.Outcome('INVALID_PARTIAL', plan.owners) if plan.interrupt else mod.Outcome(
            'PASS_CONTROLLED_FINITE_PAIR')

    with pytest.raises(Unconfirmed):
        sequence.run(cells, runner, original_disk_free_bytes=10 * 2**30)
    assert seen == ['normal', 'interrupted']
    assert len(engine.live) == 1
    assert len(sequence.controller.owned) == 2
    assert sequence.results[-1].status == 'INVALID_PARTIAL'
    assert sequence.results[-1].cleanup_confirmed is False


@pytest.mark.parametrize('fault', ['raises', 'wrong_status', 'self_report'])
def test_workload_failure_is_retained_and_cleanup_still_runs(fault):
    _, cells, engine, sequence = setup()

    def runner(plan):
        if fault == 'raises':
            raise OSError('lost coordinator')
        if fault == 'self_report':
            return {'status': 'PASS_CONTROLLED_FINITE_PAIR', 'disposed': True}
        return 'PASS'

    with pytest.raises(Unconfirmed):
        sequence.run(cells, runner, original_disk_free_bytes=10 * 2**30)
    assert not engine.live
    assert len(sequence.results) == 1
    assert sequence.results[0].accepted is False
    assert sequence.results[0].cleanup_confirmed is True


@pytest.mark.parametrize('fault', ['reused_output', 'reused_run', 'changed_workload',
                                  'bad_config', 'bad_baseline', 'missing_cell', 'long_profile'])
def test_invalid_plan_has_no_creation_side_effect(fault):
    mod, cells, engine, sequence = setup()
    baseline = 10 * 2**30
    if fault == 'reused_output':
        cells[2].config['source']['output'] = cells[0].config['source']['output']
    elif fault == 'reused_run':
        cells[2] = mod.Cell(cells[0].run, cells[2].config, cells[2].config_path, cells[2].output)
    elif fault == 'changed_workload':
        cells[2].config['streams'] = 3
    elif fault == 'bad_config':
        cells[1].config['unexpected'] = True
    elif fault == 'bad_baseline':
        baseline = True
    elif fault == 'long_profile':
        for cell in cells:
            cell.config['diagnostic_rate'] = [1, 1]
            cell.config['diagnostic_seconds'] = 60
    else:
        cells.pop()
    with pytest.raises((ValueError, Unconfirmed)):
        sequence.run(cells, lambda plan: pytest.fail('runner called'),
                     original_disk_free_bytes=baseline)
    assert engine.count == 0


def test_runner_reentry_is_blocked_without_new_container():
    _, cells, engine, sequence = setup()

    def runner(plan):
        sequence.run(cells, runner, original_disk_free_bytes=10 * 2**30)

    with pytest.raises(Unconfirmed):
        sequence.run(cells, runner, original_disk_free_bytes=10 * 2**30)
    assert engine.count == 2
    assert not engine.live


@pytest.mark.parametrize('fault', ['before_readiness', 'wrong_owner', 'unexpected_pass'])
def test_interrupted_cell_requires_exact_ready_owner_binding(fault):
    mod, cells, engine, sequence = setup()
    seen = []

    def runner(plan):
        seen.append(plan.run)
        if not plan.interrupt or fault == 'unexpected_pass':
            return mod.Outcome('PASS_CONTROLLED_FINITE_PAIR')
        owners = () if fault == 'before_readiness' else tuple(reversed(plan.owners))
        return mod.Outcome('INVALID_PARTIAL', owners)

    assert hasattr(mod, 'Outcome'), 'typed readiness-bound workload outcome missing'
    with pytest.raises(Unconfirmed):
        sequence.run(cells, runner, original_disk_free_bytes=10 * 2**30)
    assert seen == ['normal', 'interrupted']
    assert not engine.live
    assert sequence.results[-1].accepted is False


@pytest.mark.parametrize('output_cell', [0, 2])
def test_config_path_cannot_overlap_any_cells_fresh_output(output_cell):
    mod, cells, engine, sequence = setup()
    cells[0] = mod.Cell(cells[0].run, cells[0].config,
                        cells[output_cell].output + '/config.json', cells[0].output)
    with pytest.raises(Unconfirmed):
        sequence.run(cells, lambda plan: mod.Outcome('PASS_CONTROLLED_FINITE_PAIR'),
                     original_disk_free_bytes=10 * 2**30)
    assert engine.count == 0
