"""Issued fixture-token invalidation through actual isolated memory reload."""
import pytest

from .freshness_support.fixture_setup import setup, allow
from .freshness_support.pipeline_repository_fixture import FixtureEvidence
from .freshness_support.owned_memory_pipeline import ExclusivePipelineRepository
from .freshness_support.currentness_seam import Unavailable
from scripts import inclusion_persistence as store


@pytest.mark.parametrize('failure', ['denied', 'provider_error', 'release_uncertain'])
def test_issued_token_cannot_survive_failed_reload(failure):
    backend, owner, _, _, identity = setup()
    owner.reload(allow, 100)  # Explicit simulated authority, not real provenance.
    token = owner.manager.capture(100)
    with owner.manager.hold(token, 100):
        pass  # Establish this exact token was usable before the failure.
    before = backend.snapshot_for_test()
    callbacks = []
    def next_evidence(snapshot):
        callbacks.append(snapshot.digest)
        # begin_update must retire the old token before calling external evidence.
        with pytest.raises(Unavailable):
            with owner.manager.hold(token, 101):
                pytest.fail('old token remained usable during evidence refresh')
        if failure == 'provider_error':
            raise LookupError('fixture evidence unavailable')
        return FixtureEvidence(False, 200)
    if failure == 'release_uncertain':
        backend.fail_release = True
    expected_error = (OSError if failure == 'release_uncertain'
                      else LookupError if failure == 'provider_error' else Unavailable)
    with pytest.raises(expected_error):
        owner.reload(next_evidence, 101)
    assert callbacks == ([] if failure == 'release_uncertain' else [identity.snapshot])
    with pytest.raises(Unavailable):
        with owner.manager.hold(token, 101):
            pytest.fail('failed reload revived issued token')
    with pytest.raises(Unavailable):
        owner.manager.capture(101)
    assert backend.snapshot_for_test() == before
    with pytest.raises(store.StorageUnavailable):
        ExclusivePipelineRepository(backend, identity)
    owner.close()
    if failure == 'release_uncertain':
        backend.fail_release = False
        with pytest.raises(store.StorageUnavailable):
            ExclusivePipelineRepository(backend, identity)
    with pytest.raises(Unavailable):
        with owner.manager.hold(token, 102):
            pytest.fail('close revived old token')
