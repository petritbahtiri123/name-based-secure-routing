"""Isolated test support; no authenticated producer, disk writer or runtime trust.

The caller supplies an independently verified restore identity and serializes
freshness/denial decisions through set_eligible. A true value is a simulated
authority decision, never derived from stored bytes. Tokens cannot be serialized
or transferred to another barrier instance. This is not a hostile-process boundary.
"""

import threading
from contextlib import contextmanager
from dataclasses import dataclass


class Unavailable(RuntimeError):
    pass


class StaleToken(ValueError):
    pass


@dataclass(frozen=True)
class RestoreIdentity:
    context: bytes
    dependencies: bytes
    snapshot: bytes
    generation: int

    def __post_init__(self):
        for value in (self.context, self.dependencies, self.snapshot):
            if type(value) is not bytes or len(value) != 32:
                raise ValueError('identity digest must be exactly 32 bytes')
        if type(self.generation) is not int or not 0 < self.generation < 2**64 - 1:
            raise ValueError('invalid generation')


class CurrentnessBarrier:
    """One owning fixture instance, one identity, one constant-space token.

    Caller acquires registration ownership before hold(); all currentness
    invalidations use this barrier. No callbacks are invoked here. The hold body
    is restricted to bounded local owner mutation: no I/O, callbacks or reentry.
    Owner mutation is not rolled back if its body raises. Expiry/time evaluation
    remains the caller's existing serialized fixture responsibility.
    """

    def __init__(self, independently_verified: RestoreIdentity | None):
        if independently_verified is not None and type(independently_verified) is not RestoreIdentity:
            raise ValueError('invalid external restore identity')
        self._expected = independently_verified
        self._lock = threading.RLock()
        self._held = False
        self._latched = False
        self._restored = False
        self._eligible = False
        self._token = object()

    def _available(self):
        if self._held:
            raise Unavailable('reentrant barrier operation')
        if self._latched:
            raise Unavailable('unreconciled storage; fresh instance required')

    def _ready(self):
        self._available()
        if not self._restored or not self._eligible:
            raise Unavailable('current authority unavailable')

    def restore(self, candidate: RestoreIdentity | None):
        """Consume identity from a completed existing repository restore.

        This function does not decode snapshots or verify signed evidence. The
        upstream repository must have validated full bytes and released storage
        ownership successfully before calling it. Unknown provenance latches off.
        """
        with self._lock:
            self._available()
            self._token = object()
            self._eligible = False
            self._restored = False
            if (self._expected is None or type(candidate) is not RestoreIdentity
                    or candidate != self._expected):
                self._latched = True
                raise Unavailable('missing or mismatched independent provenance')
            self._restored = True

    def set_eligible(self, eligible: bool):
        """Explicit simulated authority result; every change invalidates tokens."""
        with self._lock:
            self._available()
            if type(eligible) is not bool:
                raise ValueError('eligibility must be an explicit boolean')
            if not self._restored:
                raise Unavailable('restore required')
            self._eligible = eligible
            self._token = object()

    def uncertain(self):
        with self._lock:
            self._available()
            self._latched = True
            self._eligible = False
            self._token = object()

    def capture(self):
        with self._lock:
            self._ready()
            return self._token

    def retire(self):
        """End an owned lifetime, including already unavailable instances.

        Waits for another thread's held guard. Reentrant lifetime termination
        latches off before rejecting; it cannot leave an escaped token usable.
        """
        with self._lock:
            self._latched = True
            self._eligible = False
            self._token = object()
            if self._held:
                raise Unavailable('cannot retire inside final owner mutation')

    @contextmanager
    def hold(self, token):
        with self._lock:
            self._ready()
            if token is not self._token:
                raise StaleToken('foreign, restarted or invalidated token')
            self._held = True
            try:
                yield
            finally:
                self._held = False
