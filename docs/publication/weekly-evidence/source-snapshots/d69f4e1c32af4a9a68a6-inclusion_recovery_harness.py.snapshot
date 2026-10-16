"""Test-only, synchronous recovery composition with a surviving controller.

No process, filesystem, transport, signing, registration or authority provider.
Caller-supplied accepted context/digest and disposal outcomes are explicit test
trust. Object identity models exact ownership, not hostile-process authentication.
The controller itself must survive; its reconstruction is outside this model.
"""

from dataclasses import dataclass

from scripts.inclusion_persistence import Repository, Snapshot


class RecoveryBlocked(RuntimeError):
    pass


@dataclass(frozen=True, eq=False)
class RecoveredWorker:
    snapshot: Snapshot
    registration: None = None


@dataclass(eq=False)
class _Disposal:
    owner: object
    result: bool | None = None


class Controller:
    """One fake worker slot; recovery never grants registration or readiness."""

    def __init__(self, storage, *, context_binding, expected, owner):
        if owner is None:
            raise ValueError("explicit initial fake owner required")
        self._storage = storage
        self._context = context_binding
        self._expected = expected
        self._owner = owner
        self._disposal = None
        self._restoring = False

    @property
    def owner(self):
        return self._owner

    def begin_disposal(self, owner):
        if owner is None or owner is not self._owner:
            raise RecoveryBlocked("wrong owner")
        if self._disposal is None:
            self._disposal = _Disposal(owner)
        return self._disposal

    def confirm_disposal(self, ticket, *, success):
        if type(success) is not bool:
            raise ValueError("exact fake boolean outcome required")
        if ticket is not self._disposal or ticket is None or ticket.owner is not self._owner or ticket.result is not None:
            return False
        ticket.result = success
        if success:
            self._owner = None
            self._disposal = None
        return success

    def retry_disposal(self, ticket):
        if ticket is None or ticket is not self._disposal or ticket.owner is not self._owner or ticket.result is not False:
            raise RecoveryBlocked("no exact failed disposal")
        self._disposal = _Disposal(self._owner)
        return self._disposal

    def restore(self):
        if self._restoring:
            raise RecoveryBlocked("reentrant restore")
        if self._owner is not None or self._disposal is not None:
            raise RecoveryBlocked("old ownership unresolved")
        if type(self._expected) is not bytes or len(self._expected) != 32:
            raise RecoveryBlocked("independent expected snapshot required")
        # Each retry is an explicit reopen with the SAME controller expectation.
        # Never learn an expected digest from storage or clear a repository latch.
        self._restoring = True
        try:
            repository = Repository(self._storage, context_binding=self._context)
            snapshot = repository.load(self._expected)
            worker = RecoveredWorker(snapshot)
            self._owner = worker
            return worker
        finally:
            self._restoring = False
