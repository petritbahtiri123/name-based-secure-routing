"""Actual inclusion Repository through one admitted route; memory-fixture use only.

No disk backend, process lease, provenance producer or runtime authorization.
The caller must exclusively own the underlying backend and route all operations
through this adapter. Direct references to that backend bypass this premise.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from threading import get_ident
from scripts import inclusion_persistence as persistence
from .currentness_seam import RestoreIdentity, Unavailable
from .authority_lifetime_fixture import FixtureAuthorityLifetime, PreparedFixture


@dataclass(frozen=True)
class FixtureEvidence:
    allowed: bool
    expires: int


class _AttemptStorage:
    """Same-thread, single-transaction access; revoked when the attempt returns."""
    def __init__(self, backend):
        self._backend = backend
        self._thread = get_ident()
        self._live = True
        self._active = False
        self._entered = False
        self.released = False

    def _check(self):
        if not self._live or get_ident() != self._thread:
            raise persistence.StorageUnavailable('outside owned storage attempt')

    @contextmanager
    def exclusive(self):
        self._check()
        if self._entered or self._active:
            raise persistence.StorageUnavailable('duplicate/nested transaction')
        self._entered = True
        with self._backend.exclusive():
            self._active = True
            try:
                yield
            finally:
                self._active = False
        self.released = True  # ONLY after actual backend __exit__ succeeds.

    def read(self, name):
        self._check()
        if not self._active:
            raise persistence.StorageUnavailable('read outside transaction')
        return self._backend.read(name)

    def replace(self, name, data):
        self._check()
        if not self._active:
            raise persistence.StorageUnavailable('write outside transaction')
        return self._backend.replace(name, data)

    def retire(self):
        self._live = False


class PipelineRepository:
    """One manager plus the unchanged Repository.load/repair mechanism.

    Synchronous only: no child tasks are launched. Authority callback executes
    after transaction release, outside manager/currentness/backend locks. It is
    explicitly a fixture oracle, not an authenticated verifier implementation.
    """
    def __init__(self, backend, independently_accepted: RestoreIdentity):
        self.manager = FixtureAuthorityLifetime(independently_accepted)
        self._backend = backend
        self._expected = independently_accepted

    def reload(self, authority_fixture, now):
        ticket = self.manager.begin_update()
        scoped = None
        with self.manager.write_attempt(ticket):
            scoped = _AttemptStorage(self._backend)
            try:
                repository = persistence.Repository(scoped, context_binding=self._expected.context)
                snapshot = repository.load(self._expected.snapshot)
            finally:
                scoped.retire()
            # Independent binding is checked before any publication. Repository
            # owns canonical bytes, exact digest, retained facts and repair order.
            record = persistence.parse_record(snapshot.state.record)
            if (snapshot.context_binding != self._expected.context
                    or snapshot.digest != self._expected.snapshot
                    or record[4] != self._expected.generation):
                raise Unavailable('independent restore identity mismatch')
            evidence = authority_fixture(snapshot)
            if type(evidence) is not FixtureEvidence:
                raise Unavailable('explicit fixture evidence required')
            prepared = PreparedFixture(self._expected, evidence.expires, True,
                                       scoped.released, evidence.allowed)
        # No publication until actual transaction exit AND synchronous work return.
        self.manager.publish(ticket, prepared, now)
        return snapshot
