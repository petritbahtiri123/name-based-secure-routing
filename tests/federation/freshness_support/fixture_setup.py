"""Portable copy of the existing setup recipe; explicit fixture trust only."""
from ..test_inclusion_persistence import initialized, store
from .currentness_seam import RestoreIdentity
from .pipeline_repository_fixture import FixtureEvidence
from .owned_memory_pipeline import OwnedMemoryBackend, ExclusivePipelineRepository


def setup(missing=False):
    memory, _, raw, _, snapshot = initialized()
    initial = dict(memory.files)
    if missing:
        del initial[store.PRIMARY]
    backend = OwnedMemoryBackend(initial)
    identity = RestoreIdentity(snapshot.context_binding, b'D'*32, snapshot.digest,
                               store.parse_record(snapshot.state.record)[4])
    owner = ExclusivePipelineRepository(backend, identity)
    return backend, owner, snapshot, raw, identity


def allow(_):
    return FixtureEvidence(True, 200)
