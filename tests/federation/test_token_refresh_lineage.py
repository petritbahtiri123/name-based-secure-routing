"""Actual memory-pipeline lineage tests; all evidence remains explicitly fake."""
import pytest

from .freshness_support.fixture_setup import setup, allow
from .freshness_support.pipeline_repository_fixture import FixtureEvidence
from .freshness_support.owned_memory_pipeline import ExclusivePipelineRepository
from .freshness_support.currentness_seam import StaleToken, Unavailable
from scripts import inclusion_persistence as store


@pytest.mark.parametrize('intermediate_denial', [False, True])
def test_same_snapshot_refresh_issues_new_lineage_without_reviving_old_token(intermediate_denial):
    backend, owner, snapshot, _, identity = setup()
    owner.reload(allow, 100)
    old = owner.manager.capture(100)
    with owner.manager.hold(old, 100):
        pass
    before = backend.snapshot_for_test()
    if intermediate_denial:
        with pytest.raises(Unavailable):
            owner.reload(lambda _: FixtureEvidence(False, 200), 101)
        with pytest.raises(Unavailable):
            owner.manager.capture(101)
    callbacks = []
    def refreshed(current):
        callbacks.append(current.digest)
        with pytest.raises(Unavailable):
            with owner.manager.hold(old, 102):
                pytest.fail('old lineage survived refresh entry')
        with pytest.raises(store.StorageUnavailable):
            ExclusivePipelineRepository(backend, identity)
        return allow(current)
    assert owner.reload(refreshed, 102) == snapshot
    new = owner.manager.capture(102)
    assert callbacks == [snapshot.digest]
    with owner.manager.hold(new, 102):
        pass
    with pytest.raises(StaleToken):
        with owner.manager.hold(old, 102):
            pytest.fail('same snapshot revived prior token')
    assert backend.snapshot_for_test() == before
    owner.close()
    with pytest.raises(Unavailable):
        with owner.manager.hold(new, 103):
            pytest.fail('close retained refreshed token eligibility')


def test_provider_exception_requires_new_manager_and_cannot_retry_in_place():
    backend, owner, _, _, identity = setup()
    owner.reload(allow, 100)
    old = owner.manager.capture(100)
    def fail(_):
        raise LookupError('fixture provider failure')
    with pytest.raises(LookupError):
        owner.reload(fail, 101)
    calls = []
    with pytest.raises(Unavailable):
        owner.reload(lambda snapshot: calls.append(snapshot), 102)
    assert calls == []
    with pytest.raises(Unavailable):
        with owner.manager.hold(old, 102):
            pytest.fail('failed manager revived token')
    with pytest.raises(store.StorageUnavailable):
        ExclusivePipelineRepository(backend, identity)
    owner.close()
