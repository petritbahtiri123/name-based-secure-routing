"""Ongoing authority lifetime proof, fixture inputs only; no runtime trust.

Separate from owned_restore: NEVER accepts, revives or extends its tokens.
The backend lease and completion facts below are explicitly simulated. A real
producer still needs authenticated provenance and a process-owned backend.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock
from .currentness_seam import CurrentnessBarrier, RestoreIdentity, Unavailable


@dataclass(frozen=True)
class PreparedFixture:
    identity: RestoreIdentity
    evidence_expires: int
    storage_completed: bool
    transaction_release_completed: bool
    authority_verified: bool


class _OwnedAttempt:
    __slots__ = ('issuer', 'phase', 'dispatched')

    def __init__(self, issuer):
        self.issuer, self.phase, self.dispatched = issuer, 'issued', False


class FixtureAuthorityLifetime:
    """One manager, invalidation-before-work, publication-after-work.

    Lock order: registration owner (external) -> manager -> currentness guard.
    Storage/provider work runs BETWEEN begin_update and publish, outside all
    these locks. No storage callback is accepted by this class. All participating
    writers must use begin_update/write_attempt before writing; a simulated process-owned backend
    excludes uncoordinated writers. That precondition is not implemented here.
    """
    def __init__(self, independently_accepted: RestoreIdentity):
        if type(independently_accepted) is not RestoreIdentity:
            raise Unavailable('independent fixture identity required')
        self._expected = independently_accepted
        self._lock = RLock()
        self._pending = None
        self._issuer = object()
        self._process_lease_lost = False
        self._barrier = None
        self._expires = None
        self._unavailable = False
        self._held = False
        self._time_floor = None

    def _entry(self):
        if self._held:
            raise Unavailable('reentrant manager operation')
        if self._unavailable:
            raise Unavailable('manager unavailable; new reconciled instance required')

    def _retire(self):
        if self._barrier is not None:
            self._barrier.retire()
        self._barrier = None
        self._expires = None

    def _time(self, now):
        if (type(now) is not int or not 0 <= now <= 253402300799
                or (self._time_floor is not None and now < self._time_floor)):
            self._latch()
            raise Unavailable('invalid or rolled-back fixture time')
        self._time_floor = now

    def _known(self, ticket):
        return type(ticket) is _OwnedAttempt and ticket.issuer is self._issuer

    def _latch(self):
        self._unavailable = True
        self._retire()
        # Never discard ownership of a dispatched write that may still run.
        if self._pending is not None and self._pending.phase != 'writing':
            self._pending.phase = 'completed'
            self._pending = None

    def begin_update(self):
        with self._lock:
            self._entry()
            if self._pending is not None:
                raise Unavailable('single update pipeline busy')
            self._retire()
            self._pending = _OwnedAttempt(self._issuer)
            return self._pending

    @contextmanager
    def write_attempt(self, ticket):
        """Only admitted writer route; no manager lock spans external work.

        One dispatch, then transaction completion, then publication. The caller
        must finish ALL child write work before returning. A process-wide lease
        is distinct from the bounded transaction released by this work.
        """
        with self._lock:
            self._entry()
            if not self._known(ticket) or ticket is not self._pending or ticket.phase != 'issued':
                raise Unavailable('foreign, duplicate or completed write dispatch')
            ticket.phase = 'writing'
            ticket.dispatched = True
        try:
            yield
        except BaseException:
            with self._lock:
                self._latch()
            raise
        finally:
            with self._lock:
                ticket.phase = 'returned'
                if self._unavailable:
                    ticket.phase = 'completed'
                    if self._pending is ticket:
                        self._pending = None

    def report_write_uncertainty(self, ticket):
        """Trusted backend notification; owned history is separate from publication.

        Even a late report from a previously completed owned write poisons the
        current publication. A foreign object cannot poison this manager.
        """
        with self._lock:
            if self._held:
                raise Unavailable('reentrant uncertainty notification')
            if not self._known(ticket) or not ticket.dispatched:
                raise Unavailable('no owned dispatched write')
            self._latch()

    def publish(self, ticket, prepared: PreparedFixture, now):
        with self._lock:
            if self._held:
                raise Unavailable('reentrant publication')
            # Process known write uncertainty BEFORE active-publication checks.
            # Completed attempts retain instance identity in caller-owned tickets;
            # the manager keeps only its single pending attempt, not an unbounded log.
            if (self._known(ticket) and ticket.dispatched
                    and (type(prepared) is not PreparedFixture
                         or prepared.storage_completed is not True
                         or prepared.transaction_release_completed is not True)):
                self._latch()
                raise Unavailable('owned write/release uncertain; reconciliation required')
            self._entry()
            if not self._known(ticket) or ticket is not self._pending or ticket.phase != 'returned':
                raise Unavailable('foreign, incomplete or already published completion')
            self._time(now)
            ticket.phase = 'completed'
            self._pending = None
            if (type(prepared) is not PreparedFixture
                    or prepared.identity != self._expected
                    or prepared.authority_verified is not True
                    or type(prepared.evidence_expires) is not int
                    or not now < prepared.evidence_expires <= 253402300799):
                raise Unavailable('incomplete or invalid fixture evidence')
            barrier = CurrentnessBarrier(self._expected)
            barrier.restore(prepared.identity)
            barrier.set_eligible(True)
            self._barrier = barrier
            self._expires = prepared.evidence_expires

    def uncertain(self):
        with self._lock:
            self._entry()
            self._latch()

    def lose_process_writer_lease(self):
        with self._lock:
            if self._held:
                raise Unavailable('reentrant lease loss')
            self._process_lease_lost = True
            self._latch()

    def shutdown(self):
        with self._lock:
            if self._held:
                raise Unavailable('reentrant shutdown')
            self._latch()

    def process_lease_releasable(self):
        with self._lock:
            return self._unavailable and self._pending is None

    def capture(self, now):
        with self._lock:
            self._entry()
            self._time(now)
            if self._barrier is None or now >= self._expires:
                self._retire()
                raise Unavailable('fresh authority required')
            return self._barrier.capture()

    @contextmanager
    def hold(self, token, now):
        with self._lock:
            self._entry()
            self._time(now)
            if self._barrier is None or now >= self._expires:
                self._retire()
                raise Unavailable('fresh authority required')
            with self._barrier.hold(token):
                self._held = True
                try:
                    yield  # Bounded trusted local mutation only; no callbacks/I/O.
                finally:
                    self._held = False
