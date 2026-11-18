"""Execution-inert API sketch; no native ownership or publication integration."""
from dataclasses import dataclass
import math
import threading


@dataclass(frozen=True)
class Observation:
    identity: tuple
    sequence: int
    generation: int
    observed_at: float


class ObservationSlot:
    def __init__(self, identity, *, anchor, deadline):
        if (type(identity) is not tuple or len(identity) != 3
                or any(type(v) is not str or not v or len(v) > 256 for v in identity)):
            raise ValueError('fixed trusted run/request/readiness identity')
        if any(type(t) not in (int, float) or not math.isfinite(t) for t in (anchor, deadline)):
            raise ValueError('finite original window')
        if anchor < 0 or deadline != anchor + 115:
            raise ValueError('unchanged viewer observation window')
        self._identity = identity
        self._previous, self._deadline = anchor, deadline
        self._lock = threading.Lock()
        self._generation = self._sequence = 0
        self._failed = self._pending = False
        self._reply = None

    def _fail(self, message):
        self._failed = True
        self._generation += 1
        self._reply = None
        raise ValueError(message)

    def _check(self, now):
        if self._failed:
            raise ValueError('observation attempt revoked')
        if type(now) not in (int, float) or not math.isfinite(now) or not self._previous <= now < self._deadline:
            self._fail('original deadline/clock')
        self._previous = now

    def request(self, *, now):
        with self._lock:
            self._check(now)
            if self._pending:
                self._fail('one bounded pending observation only')
            self._sequence += 1
            self._pending = True
            self._reply = None
            return self._sequence

    def pending(self, *, now):
        with self._lock:
            self._check(now)
            return self._sequence if self._pending and self._reply is None else None

    def answer(self, sequence, *, owned, now):
        """Only the original monitor may answer, after its actual observation.

        This sketch cannot enforce caller identity; no process handle is accepted
        or inferred from files. Runtime binding remains a separate reviewed gate.
        """
        with self._lock:
            self._check(now)
            if (not self._pending or self._reply is not None or type(sequence) is not int
                    or sequence != self._sequence or owned is not True):
                self._fail('stale/reused/unowned observation')
            self._reply = Observation(self._identity, sequence, self._generation, now)

    def take(self, sequence, *, now):
        with self._lock:
            self._check(now)
            if not self._pending or self._reply is None or type(sequence) is not int or sequence != self._sequence:
                self._fail('missing/stale/consumed observation')
            self._pending = False
            return self._reply

    def revalidate(self, reply, *, now):
        """Check immediately before I/O, without claiming atomic child liveness."""
        with self._lock:
            self._check(now)
            if self._pending or reply is not self._reply or reply is None or reply.generation != self._generation:
                self._fail('revoked or superseded observation')

    def revoke(self):
        with self._lock:
            self._failed = True
            self._generation += 1
            self._reply = None
