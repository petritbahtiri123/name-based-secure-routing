"""Offline local-container ownership contract; no live engine or CLI adapter.

The injected management engine is trusted to create isolated endpoint containers,
return immutable IDs, remove exactly one ID, and answer each fresh Probe from its
own engine observations. Workload outputs are never engine observations. This is
instance-local accidental-misuse protection, not hostile-process authentication,
durable recovery, bare-host disposal evidence, or protocol authority.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import re


class Unconfirmed(RuntimeError):
    """Ownership must remain retained; replacement is not authorized."""


@dataclass(frozen=True)
class Creation:
    run: str
    role: str


@dataclass(frozen=True)
class Container:
    run: str
    role: str
    container_id: str
    isolated: bool


@dataclass(frozen=True, eq=False)
class Probe:
    container: Container


@dataclass(frozen=True)
class Observation:
    probe: Probe
    present: Container | None


@dataclass(frozen=True, eq=False)
class Receipt:
    container: Container
    probe: Probe


class Controller:
    """One surviving, serialized controller; creation uncertainty is terminal.

An exception from create may hide a newly created resource, so it permanently
blocks this controller. Known failed removals can be explicitly retried with the
same owner. All owners remain retained until both exact receipts are consumed.
The engine must forbid host/shared namespaces and external descendants; an
isolated flag is an adapter assertion, not a measured guarantee in these tests.
"""

    def __init__(self, engine):
        self._engine = engine
        self._owners = []
        self._receipts = {}
        self._runs = set()
        self._ids = set()
        self._busy = False
        self._uncertain = False
        self._events = []

    @property
    def owned(self):
        return tuple(self._owners)

    @property
    def events(self):
        return tuple(self._events)

    @contextmanager
    def _operation(self):
        if self._busy:
            raise Unconfirmed('reentrant operation')
        self._busy = True
        try:
            yield
        finally:
            self._busy = False

    def _observe(self, owner, absent):
        probe = Probe(owner)
        observation = self._engine.observe(probe)
        if (type(observation) is not Observation or observation.probe is not probe
                or (observation.present is not None if absent else
                    type(observation.present) is not Container or observation.present != owner)):
            raise Unconfirmed('missing, stale, or mismatched engine observation')
        return probe

    def start(self, run):
        with self._operation():
            if (self._uncertain or self._owners or type(run) is not str
                    or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', run) or run in self._runs):
                raise Unconfirmed('unreleased ownership or invalid/replayed run')
            self._runs.add(run)
            try:
                for role in ('source', 'destination'):
                    owner = self._engine.create(Creation(run, role))
                    if (type(owner) is not Container or owner.run != run or owner.role != role
                            or type(owner.container_id) is not str
                            or not re.fullmatch(r'[0-9a-f]{64}', owner.container_id)
                            or owner.container_id in self._ids or owner.isolated is not True):
                        raise Unconfirmed('unresolved creation identity or containment')
                    self._owners.append(owner)
                    self._ids.add(owner.container_id)
                    self._observe(owner, absent=False)
                    self._events.append(('created', owner))
            except BaseException as exc:
                self._uncertain = True
                self._events.append(('creation_unconfirmed', run, type(exc).__name__))
                raise Unconfirmed('creation uncertain; replacement disabled') from exc
            return self.owned

    def dispose(self, owner):
        with self._operation():
            if not any(owner is current for current in self._owners):
                raise Unconfirmed('not the exact current owner')
            if owner.container_id in self._receipts:
                raise Unconfirmed('disposal already confirmed')
            try:
                self._engine.remove(owner.container_id)
                probe = self._observe(owner, absent=True)
            except BaseException as exc:
                self._events.append(('disposal_unconfirmed', owner, type(exc).__name__))
                raise Unconfirmed('disposal uncertain; ownership retained') from exc
            receipt = Receipt(owner, probe)
            self._receipts[owner.container_id] = receipt
            self._events.append(('disposed', owner))
            return receipt

    def release(self, receipts):
        with self._operation():
            if (self._uncertain or len(self._owners) != 2 or type(receipts) is not tuple
                    or len(receipts) != 2 or len(self._receipts) != 2
                    or any(supplied is not self._receipts.get(owner.container_id)
                           for supplied, owner in zip(receipts, self._owners))):
                raise Unconfirmed('both fresh exact disposal receipts required')
            self._events.append(('released', self._owners[0].run))
            self._owners.clear()
            self._receipts.clear()
