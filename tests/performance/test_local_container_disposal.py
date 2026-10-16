"""Offline engine fixtures; never execute containers or a workload."""
from dataclasses import replace
import importlib

import pytest


def api():
    # Missing implementation is an assertion failure during the initial RED run.
    name = 'scripts.performance.local_container_disposal'
    assert importlib.util.find_spec(name) is not None, 'disposal contract not implemented'
    return importlib.import_module(name)


class Engine:
    def __init__(self, mod):
        self.mod = mod
        self.live = {}
        self.count = 0
        self.fail_remove = False
        self.stale = None
        self.on_observe = None

    def create(self, request):
        self.count += 1
        value = self.mod.Container(request.run, request.role, f'{self.count:064x}', True)
        self.live[value.container_id] = value
        return value

    def remove(self, container_id):
        if self.fail_remove:
            raise OSError('engine unavailable')
        self.live.pop(container_id, None)

    def observe(self, request):
        if self.on_observe:
            self.on_observe()
        return self.stale or self.mod.Observation(
            request, self.live.get(request.container.container_id))


def setup():
    mod = api()
    engine = Engine(mod)
    return mod, engine, mod.Controller(engine)


def test_requires_both_disposals_and_consumes_exact_receipts_once():
    mod, engine, controller = setup()
    owners = controller.start('normal')
    assert {owner.role for owner in owners} == {'source', 'destination'}
    first = controller.dispose(owners[0])
    with pytest.raises(mod.Unconfirmed):
        controller.release((first,))
    with pytest.raises(mod.Unconfirmed):
        controller.start('fresh')
    second = controller.dispose(owners[1])
    controller.release((first, second))
    assert not engine.live
    with pytest.raises(mod.Unconfirmed):
        controller.release((first, second))
    with pytest.raises(mod.Unconfirmed):
        controller.start('normal')
    assert controller.start('fresh')


@pytest.mark.parametrize('mutation', ['copy', 'wrong_run', 'wrong_role', 'wrong_id'])
def test_rejects_copied_or_changed_ownership(mutation):
    mod, _, controller = setup()
    owners = controller.start('one')
    changes = {'copy': {}, 'wrong_run': {'run': 'old'},
               'wrong_role': {'role': 'destination'}, 'wrong_id': {'container_id': 'f' * 64}}
    with pytest.raises(mod.Unconfirmed):
        controller.dispose(replace(owners[0], **changes[mutation]))
    assert controller.owned == owners


def test_failed_cleanup_retains_owner_and_requires_explicit_retry():
    mod, engine, controller = setup()
    owners = controller.start('one')
    engine.fail_remove = True
    with pytest.raises(mod.Unconfirmed):
        controller.dispose(owners[0])
    assert controller.owned == owners
    with pytest.raises(mod.Unconfirmed):
        controller.start('two')
    engine.fail_remove = False
    controller.release(tuple(controller.dispose(owner) for owner in owners))
    assert controller.start('two')


def test_stale_absence_cannot_authorize_current_disposal():
    mod, engine, controller = setup()
    owners = controller.start('one')
    engine.stale = mod.Observation(mod.Probe(owners[0]), None)
    with pytest.raises(mod.Unconfirmed):
        controller.dispose(owners[0])
    assert controller.owned == owners


@pytest.mark.parametrize('fault', ['present', 'missing', 'error', 'boolean'])
def test_incomplete_observation_retains_owner(fault):
    mod, engine, controller = setup()
    owners = controller.start('one')

    def observe(probe):
        if fault == 'error':
            raise OSError('lost observer')
        return {'present': mod.Observation(probe, owners[0]),
                'missing': None, 'boolean': True}.get(fault)

    engine.observe = observe
    with pytest.raises(mod.Unconfirmed):
        controller.dispose(owners[0])
    assert controller.owned == owners


def test_receipt_forgery_and_other_controller_receipts_fail():
    mod, _, controller = setup()
    owners = controller.start('one')
    receipts = tuple(controller.dispose(owner) for owner in owners)
    for supplied in ((True, True), (replace(receipts[0]), receipts[1])):
        with pytest.raises(mod.Unconfirmed):
            controller.release(supplied)
    other = mod.Controller(Engine(mod))
    other_owners = other.start('one')
    other_receipts = tuple(other.dispose(owner) for owner in other_owners)
    with pytest.raises(mod.Unconfirmed):
        controller.release(other_receipts)
    controller.release(receipts)


@pytest.mark.parametrize('fault', ['unknown_create', 'shared_namespace', 'wrong_label', 'reused_id'])
def test_creation_uncertainty_blocks_replacement(fault):
    mod, engine, controller = setup()
    original = engine.create

    def create(request):
        if fault == 'unknown_create':
            raise OSError('creation outcome unknown')
        value = original(request)
        if fault == 'shared_namespace':
            return replace(value, isolated=False)
        if fault == 'wrong_label':
            return replace(value, run='other')
        return replace(value, container_id='a' * 64)

    engine.create = create
    with pytest.raises(mod.Unconfirmed):
        controller.start('one')
    with pytest.raises(mod.Unconfirmed):
        controller.start('two')


def test_observer_callback_cannot_reenter_controller():
    mod, engine, controller = setup()
    owners = controller.start('one')
    engine.on_observe = lambda: controller.dispose(owners[1])
    with pytest.raises(mod.Unconfirmed):
        controller.dispose(owners[0])
    assert controller.owned == owners
