"""Owned in-memory backend: access control at Storage boundary, not a disk lock.

Proof backend only. It implements no filesystem, process lease or trust anchor.
Raw Storage methods reject; exactly one private owner facade can transact.
"""
from contextlib import contextmanager
from threading import RLock, get_ident
from scripts import inclusion_persistence as persistence
from .pipeline_repository_fixture import PipelineRepository
from .authority_lifetime_fixture import FixtureAuthorityLifetime


class OwnedMemoryBackend:
    def __init__(self, initial):
        if type(initial) is not dict or any(type(k) is not str or type(v) is not bytes for k, v in initial.items()):
            raise ValueError('explicit immutable fixture bytes required')
        self.__files = dict(initial)
        self.__lock = RLock()
        self.__capability = None
        self.__active = False
        self.__closed = False
        self.fail = None  # Test-only deterministic I/O fault selector.
        self.fail_release = False
        self.fail_owner_release = False
        self.__owner_release_failed = False

    def snapshot_for_test(self):
        with self.__lock:
            return dict(self.__files)

    def _claim(self):
        with self.__lock:
            if self.__capability is not None or self.__closed:
                raise persistence.StorageUnavailable('backend already owned or closed')
            self.__capability = object()
            return self.__capability

    def _release_claim(self, capability):
        with self.__lock:
            if capability is None or capability is not self.__capability:
                raise persistence.StorageUnavailable('not this backend owner')
            if self.__active:
                raise persistence.StorageUnavailable('active transaction retains claim')
            if self.__owner_release_failed:
                raise persistence.StorageUnavailable('unreconciled owner release failure')
            if self.fail_owner_release:
                # Injected ambiguous release: keep the exact claim visible and
                # quarantine this backend. No retry/reset can transfer ownership.
                self.__owner_release_failed = True
                self.__closed = True
                raise persistence.StorageUnavailable('owner release failed; claim retained')
            self.__capability = None
            # __closed deliberately stays set after transaction uncertainty.

    @contextmanager
    def exclusive(self):
        raise persistence.StorageUnavailable('raw repository route forbidden')
        yield  # Storage protocol context-manager shape, never reached.

    def read(self, name):
        raise persistence.StorageUnavailable('raw storage read forbidden')

    def replace(self, name, data):
        raise persistence.StorageUnavailable('raw storage write forbidden')

    @contextmanager
    def _owned_transaction(self, capability):
        with self.__lock:
            if capability is not self.__capability or capability is None or self.__closed or self.__active:
                raise persistence.StorageUnavailable('invalid or nested backend ownership')
            self.__active = True
            transaction = _Transaction(self.__files, self.fail)
            body_failed = False
            try:
                yield transaction
            except BaseException:
                body_failed = True
                # Sticky on the backend, not merely its current manager. Once
                # replacement may have started, any failed transaction prevents
                # later claim transfer on this same backend instance.
                if transaction.mutation_started:
                    self.__closed = True
                raise
            finally:
                if transaction.write_uncertain or (transaction.write_failed and transaction.mutation_started):
                    self.__closed = True
                transaction.retire()
                self.__active = False
                if self.fail_release:
                    self.__closed = True
                    raise OSError('owned transaction release failed')
                if transaction.write_failed and not body_failed:
                    # A proven no-mutation failure still is NOT a completed
                    # repair. Reject publication without inventing uncertainty.
                    raise persistence.StorageUnavailable('suppressed write failure; repair not confirmed')


class _Transaction:
    def __init__(self, files, fault):
        self.__files = files
        self.__fault = fault
        self.__thread = get_ident()
        self.__live = True
        self.mutation_started = False
        self.write_uncertain = False
        self.write_failed = False

    def _check(self):
        if not self.__live or get_ident() != self.__thread:
            raise persistence.StorageUnavailable('escaped or cross-thread transaction')

    def read(self, name):
        self._check()
        return self.__files.get(name)

    def replace(self, name, data):
        self._check()
        try:
            if self.__fault == (name, 'before'):
                raise OSError('before replacement')
            self.mutation_started = True
            self.__files[name] = data
            if self.__fault == (name, 'after'):
                raise OSError('after replacement')
        except BaseException:
            self.write_failed = True
            if self.mutation_started:
                self.write_uncertain = True
            raise

    def retire(self):
        self.__live = False


class _OwnerStorage:
    def __init__(self, backend):
        self.__backend = backend
        self.__transaction = None
        self.__released = False
        self.__capability = backend._claim()

    def release(self):
        if self.__released:
            return
        self.__backend._release_claim(self.__capability)
        self.__released = True

    @contextmanager
    def exclusive(self):
        with self.__backend._owned_transaction(self.__capability) as transaction:
            self.__transaction = transaction
            try:
                yield
            finally:
                self.__transaction = None

    def read(self, name):
        if self.__transaction is None:
            raise persistence.StorageUnavailable('no owner transaction')
        return self.__transaction.read(name)

    def replace(self, name, data):
        if self.__transaction is None:
            raise persistence.StorageUnavailable('no owner transaction')
        self.__transaction.replace(name, data)
        # Memory-backend completion proof under the SAME transaction lock.
        # A wrapper returning without replacing is not a successful repair.
        if self.__transaction.read(name) != data:
            raise persistence.StorageUnavailable('repair not confirmed by transaction bytes')


class ExclusivePipelineRepository(PipelineRepository):
    def __init__(self, backend, independently_accepted):
        if type(backend) is not OwnedMemoryBackend:
            raise ValueError('explicit owned fixture backend required')
        # Complete all authority/lifecycle construction before claiming storage.
        # No externally supplied callback or second authority constructor follows
        # successful claim acquisition.
        self.manager = FixtureAuthorityLifetime(independently_accepted)
        self._expected = independently_accepted
        self.__close_lock = RLock()
        self.__closed = False
        self._backend = _OwnerStorage(backend)  # Last construction step.

    def close(self):
        """Retire authority, verify local quiescence, release this exact claim.

        Pending work returns an error and retains ownership; caller may retry
        close only after actual synchronous work returns. A release failure is
        quarantined, not an implicit successful close or a generic reset.
        """
        # Retire first, before acquiring the close mutex. A prohibited reentrant
        # call from a final guard fails immediately instead of waiting behind a
        # different closer that is itself waiting for that guard.
        self.manager.shutdown()
        with self.__close_lock:
            if self.__closed:
                return
            if not self.manager.process_lease_releasable():
                raise persistence.StorageUnavailable('pending work retains backend claim')
            self._backend.release()
            self.__closed = True
