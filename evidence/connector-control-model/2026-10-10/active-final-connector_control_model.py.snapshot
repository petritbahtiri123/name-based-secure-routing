"""Experimental mock-only connector ownership model. NOT a protocol/runtime API.

Single-threaded, synchronous event ordering; no I/O, signing, persistence, timers
or production verifier. Call poll explicitly to model time/invalidation events.
Attempt phases deliberately do not alter the frozen ConnectorState transitions.
Dependencies must be non-reentrant deterministic fakes; Python objects are not
an adversarial security boundary. No runtime imports this model.
"""

from dataclasses import dataclass
from typing import Callable, Protocol

from nbsr.federation.registry import EnforcementMode


@dataclass(frozen=True)
class Binding:
    connector: str
    service: str
    gateway: str
    operator: str
    issuer: str
    generation: int
    role: str


@dataclass(frozen=True)
class Permission:
    binding: Binding
    expires: int


class Transport(Protocol):
    session: object
    closed: bool

    def close(self) -> None: ...


@dataclass(eq=False)
class Attempt:
    transport: Transport
    binding: Binding
    session: object
    phase: str = "connecting"


@dataclass(frozen=True, eq=False)
class Acceptance:
    owner: Attempt
    session: object
    expires: int


@dataclass(eq=False)
class ActiveWork:
    """One simulated request, never an actual stream or resource reservation."""

    owner: Attempt
    deadline: int
    cancelled: bool = False
    completed: bool = False


class Model:
    """One slot, no queue; explicit test-input limits, never protocol defaults."""

    def __init__(
        self,
        binding: Binding,
        verifier: Callable[[Binding, object, int], Permission | None],
        clock: Callable[[], int],
        *,
        lease: int,
        attempts: int,
        retry_delay: int,
    ):
        if any(type(x) is not int or x <= 0 for x in (lease, attempts)):
            raise ValueError("positive integer model limits required")
        if type(retry_delay) is not int or retry_delay < 0:
            raise ValueError("nonnegative integer model delay required")
        self.binding = binding
        self.verifier = verifier
        self.clock = clock
        self.lease = lease
        self.remaining = attempts
        self.retry_delay = retry_delay
        self._last_time: int | None = None
        self._retry_at: int | None = None
        self._halted = False
        self._current: Attempt | None = None
        self._acceptance: Acceptance | None = None
        self._work: ActiveWork | None = None

    def _time(self) -> int | None:
        try:
            now = self.clock()
        except Exception:
            now = None
        if type(now) is not int or (self._last_time is not None and now < self._last_time):
            self._halted = True
            if self._current is not None:
                self._cleanup(self._current)
            return None
        self._last_time = now
        return now

    def _permission(self, attempt: Attempt, now: int) -> Permission | None:
        if attempt.binding != self.binding or attempt.transport.session is not attempt.session:
            return None
        try:
            permission = self.verifier(attempt.binding, attempt.session, now)
        except Exception:
            return None
        if (
            not isinstance(permission, Permission)
            or permission.binding != self.binding
            or type(permission.expires) is not int
            or permission.expires <= now
        ):
            return None
        return permission

    def begin(self, transport: Transport, binding: Binding) -> Attempt | None:
        self.poll()
        now = self._time()
        if self._current is not None and transport is self._current.transport:
            return None
        if (
            now is None
            or self._halted
            or self._current is not None
            or self.remaining == 0
            or transport.closed
            or (self._retry_at is not None and now < self._retry_at)
        ):
            transport.close()
            return None
        self.remaining -= 1
        self._current = Attempt(transport, binding, transport.session)
        return self._current

    def authenticate(self, attempt: Attempt) -> bool:
        self.poll()
        if attempt is not self._current or attempt.phase != "connecting":
            return False
        attempt.phase = "authenticated"
        return True

    def register(self, attempt: Attempt) -> Acceptance | None:
        self.poll()
        if attempt is not self._current or attempt.phase != "authenticated":
            return None
        now = self._time()
        if now is None:
            return None
        permission = self._permission(attempt, now)
        if permission is None:
            self._halted = True
            self.stop(attempt)
            return None
        ticket = Acceptance(attempt, attempt.session, min(now + self.lease, permission.expires))
        self._acceptance = ticket
        attempt.phase = "registered"
        return ticket

    def confirm(self, attempt: Attempt, ticket: Acceptance) -> bool:
        self.poll()
        if attempt is not self._current or ticket is not self._acceptance or ticket.owner is not attempt:
            return False
        attempt.phase = "ready"
        return True

    def renew(self, attempt: Attempt, ticket: Acceptance) -> Acceptance | None:
        self.poll()
        if attempt is not self._current or ticket is not self._acceptance or attempt.phase != "ready":
            return None
        now = self._time()
        if now is None:
            return None
        if now >= ticket.expires:
            self._expire_registration(attempt, now)
            return None
        permission = self._permission(attempt, now)
        if permission is None:
            self._halted = True
            self.stop(attempt)
            return None
        renewed = Acceptance(attempt, attempt.session, min(now + self.lease, permission.expires))
        self._acceptance = renewed
        return renewed

    def poll(self) -> None:
        now = self._time()
        attempt = self._current
        if attempt is None or now is None or attempt.phase == "terminal":
            return
        if attempt.transport.closed:
            self.stop(attempt)
            return
        if self._permission(attempt, now) is None:
            self._halted = True
            self.stop(attempt)
            return
        if self._work is not None and now >= self._work.deadline:
            self._work.cancelled = True
            self._work = None
        ticket = self._acceptance
        if ticket is not None and now >= ticket.expires:
            self._expire_registration(attempt, now)
        if attempt.phase == "draining" and self._work is None:
            self.stop(attempt)

    def _expire_registration(self, attempt: Attempt, now: int) -> None:
        self._acceptance = None
        attempt.phase = "draining"
        if self._work is not None and now >= self._work.deadline:
            self._work.cancelled = True
            self._work = None
        if self._work is None:
            self.stop(attempt)

    def admit_work(self, attempt: Attempt, *, deadline: int, lease_bounds_active: bool) -> ActiveWork | None:
        """Explicit fixture policy: caller chooses whether lease also caps work.

        Both choices remain bounded by admission-time permission and caller
        deadline. Renewal never extends an already admitted request's deadline.
        """
        if type(deadline) is not int or type(lease_bounds_active) is not bool:
            raise ValueError("explicit integer deadline and boolean fixture policy required")
        self.poll()
        if attempt is not self._current or attempt.phase != "ready" or self._work is not None:
            return None
        now = self._time()
        ticket = self._acceptance
        if now is None or ticket is None:
            return None
        if now >= ticket.expires:
            self.stop(attempt)
            return None
        permission = self._permission(attempt, now)
        if permission is None:
            self._halted = True
            self.stop(attempt)
            return None
        bounded = min(deadline, permission.expires, ticket.expires if lease_bounds_active else permission.expires)
        if bounded <= now:
            return None
        self._work = ActiveWork(attempt, bounded)
        return self._work

    def finish_work(self, work: ActiveWork) -> None:
        self.poll()
        if work is not self._work:
            return
        work.completed = True
        self._work = None
        if self._current is not None and self._current.phase == "draining":
            self.stop(self._current)

    def enforce(self, attempt: Attempt, mode: EnforcementMode) -> None:
        """Apply an already-verified fake event; no parsing or trust is provided.

        Exact enum type is required: Core mode 2 must not become federation
        REAUTHENTICATE through an IntEnum cast. Only the two approved modes exist
        in this slice. Revocation latches this model instance against reconnect.
        """
        if type(mode) is not EnforcementMode or mode not in (EnforcementMode.DENY_NEW_USE, EnforcementMode.TERMINATE_ACTIVE_USE):
            raise ValueError("unsupported semantic enforcement mode")
        if attempt is not self._current:
            return
        # Match before polling: expiry/disconnect cleanup must not swallow a
        # revocation addressed to the current owner at this event boundary.
        self._halted = True
        self.poll()
        if attempt is not self._current:
            return
        self._acceptance = None
        if mode is EnforcementMode.TERMINATE_ACTIVE_USE or attempt.phase == "terminal":
            self.stop(attempt)
            return
        attempt.phase = "draining"
        if self._work is None:
            self.stop(attempt)

    def select(self) -> Attempt | None:
        self.poll()
        if self._current is not None and self._current.phase == "ready":
            return self._current
        return None

    def stop(self, attempt: Attempt) -> None:
        if attempt is not self._current:
            return
        self._time()
        self._cleanup(attempt)

    def _cleanup(self, attempt: Attempt) -> None:
        if attempt is not self._current:
            return
        # Withdraw eligibility first, but never report released ownership until
        # close is confirmed. Failed cleanup requires explicit owner retry.
        self._acceptance = None
        attempt.phase = "terminal"
        if self._work is not None:
            self._work.cancelled = True
            self._work = None
        try:
            attempt.transport.close()
        except Exception:
            self._halted = True
            return
        if not attempt.transport.closed:
            self._halted = True
            return
        self._current = None
        if self._last_time is not None:
            self._retry_at = self._last_time + self.retry_delay

    def health(self) -> dict[str, bool | int]:
        return {"ready": self.select() is not None, "owned": int(self._current is not None)}
