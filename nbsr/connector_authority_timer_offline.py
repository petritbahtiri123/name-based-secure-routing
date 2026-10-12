"""Explicitly polled fixture scheduler; NOT a runtime authority/event receiver.

Call poll before each simulated operation after changing the injected clock.
Attaching this adapter replaces the model clock with its last sampled time;
each poll samples the original injected clock exactly once. Model operations
between polls intentionally see that snapshot, including after owner cleanup.
No background thread, wakeup, signed receipt, real clock, event transport or
new lifetime policy. All events and dependency/revision bindings are test inputs.
The bounded lifetime inventory never evicts event IDs or clears a denial latch.
Dependencies and clock must be serialized, deterministic and non-reentrant.
"""

from dataclasses import dataclass

from nbsr.connector_control_model import Model
from nbsr.connector_registration_offline import MAX_TIME, bstr, uint
from nbsr.federation.registry import EnforcementMode
from nbsr.federation.revocation import DependencyIndex


@dataclass(frozen=True)
class SimulatedAuthorityEvent:
    event_id: bytes
    context_digest: bytes
    dependencies: frozenset[bytes]
    revision: int
    effective_at: int
    mode: EnforcementMode


class OfflineAuthorityTimer:
    """One exact existing owner; replacement/rebinding requires another fixture."""

    def __init__(self, model, owner, *, context_digest, dependencies, revision, max_events):
        if (
            type(model) is not Model
            or isinstance(getattr(model.clock, "__self__", None), OfflineAuthorityTimer)
            or owner is None
            or owner is not model._current
            or owner.transport.session is not owner.session
            or not bstr(context_digest, 32)
            or not self._dependencies(dependencies)
            or not uint(revision, 1)
            or not uint(max_events, 1, 64)
        ):
            raise ValueError("explicit bounded owner/dependency fixture required")
        self.model, self.owner = model, owner
        self.context_digest, self.dependencies = context_digest, dependencies
        self.revision, self.max_events = revision, max_events
        self._last_time = model._last_time
        self._failed_clock = False
        self._events = {}
        self._pending = set()
        self._source_clock = model.clock
        self._sample = model._last_time
        model.clock = self._sample_time

    def _sample_time(self):
        return self._sample

    @staticmethod
    def _dependencies(value):
        return type(value) is frozenset and 1 <= len(value) <= 64 and all(bstr(v, 32) for v in value)

    def _matches(self):
        return self.owner is self.model._current and self.owner.transport.session is self.owner.session

    def _affects(self, event):
        index = DependencyIndex()
        index.add(self.context_digest, set(self.dependencies))
        return self.context_digest in index.invalidate(set(event.dependencies))

    def advance_revision(self, revision):
        """Test-input revision only. Does not validate or restore authority."""
        if not uint(revision, self.revision + 1):
            raise ValueError("revision must increase")
        self.revision = revision

    def schedule(self, event):
        if (
            type(event) is not SimulatedAuthorityEvent
            or not bstr(event.event_id, 32)
            or not bstr(event.context_digest, 32)
            or not self._dependencies(event.dependencies)
            or not uint(event.revision, 1)
            or not uint(event.effective_at, 0, MAX_TIME)
            or type(event.mode) is not EnforcementMode
            or event.mode not in (EnforcementMode.DENY_NEW_USE, EnforcementMode.TERMINATE_ACTIVE_USE)
        ):
            raise ValueError("exact simulated event required")
        previous = self._events.get(event.event_id)
        if previous is not None:
            if previous != event:
                raise ValueError("conflicting event identity")
            return False
        if self._failed_clock or not self._matches() or event.context_digest != self.context_digest or event.revision != self.revision:
            return False
        if not self._affects(event):
            return False
        if len(self._events) >= self.max_events:
            raise ValueError("fixture event inventory bound")
        self._events[event.event_id] = event
        self._pending.add(event.event_id)
        return True

    def poll(self):
        try:
            now = self._source_clock()
        except Exception:
            now = None
        floor = max(t for t in (self._last_time, self.model._last_time, 0) if t is not None)
        if self._failed_clock or not uint(now, floor, MAX_TIME):
            self._failed_clock = True
            self._sample = None
            if self._matches():
                self.model.enforce(self.owner, EnforcementMode.TERMINATE_ACTIVE_USE)
            raise ValueError("invalid or rolled-back fixture clock")
        self._last_time = now
        self._sample = now
        dispatched = 0
        for event in sorted((self._events[key] for key in self._pending), key=lambda e: (e.effective_at, e.event_id)):
            if event.effective_at > now:
                break
            if not self._matches() or event.revision != self.revision or not self._affects(event):
                self._pending.remove(event.event_id)
                continue
            self.model.enforce(self.owner, event.mode, effective_at=event.effective_at)
            self._pending.remove(event.event_id)
            dispatched += 1
        if self._matches():
            self.model.poll()
        return dispatched
