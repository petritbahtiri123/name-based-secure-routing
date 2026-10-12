"""CRP-1 deterministic OFFLINE conformance model; never a runtime trust API.

No socket, TLS session, authority discovery, registry allocation or credential
creation. Callers supply synthetic verifier receipts and exporter callbacks.
Python object identity is test correlation, NOT an adversarial trust boundary.
Control bodies have candidate field keys; envelope message/action/ALPN tokens
remain UNALLOCATED. No application work is created or timed by this module.
"""

from dataclasses import dataclass, field
from hashlib import sha256
from hmac import compare_digest

from nbsr.federation.registry import ObjectType
from nbsr.protocol.cbor import CborLimits, decode_deterministic, encode_deterministic
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.fields import TEXT_ID_PATTERN
from nbsr.protocol.registry import ErrorCode
from nbsr.protocol.schemas import decode_error

EXPORTER_LABEL = b"EXPORTER-NBSR-Connector-Registration-v1"
CONTEXT_DOMAIN = "NBSR-CONNECTOR-REGISTRATION-CONTEXT-v1"
ACCEPT_DOMAIN = "NBSR-CONNECTOR-ACCEPT-DIGEST-v1"
ACTION = "UNALLOCATED_CONNECTOR_REGISTER_ACTION"
PROFILE = "UNALLOCATED_CONNECTOR_PROFILE"
OFFLINE_PROFILE_VERSION = "connector-registration-v1-draft2"
MAX_COUNTER = 2**64 - 1
MAX_TIME = 253402300799
LIMITS = CborLimits(65536, 8, 64, 32, 128, 16384)
REQUEST_LIMITS = CborLimits(16384, 8, 64, 16, 64, 64)


def reject(name):
    raise ProtocolViolation(getattr(ErrorCode, "NBSR_E_" + name), "CRP-1 offline rejection: " + name)


def uint(value, low=0, high=2**64 - 1):
    return type(value) is int and low <= value <= high


def bstr(value, size, nonzero=False):
    return type(value) is bytes and len(value) == size and (not nonzero or any(value))


def text_id(value):
    return type(value) is str and 1 <= len(value) <= 64 and TEXT_ID_PATTERN.fullmatch(value) is not None


def canonical(value):
    return encode_deterministic(value, LIMITS)


def digest(value):
    return sha256(canonical(value)).digest()


def operation_counter(session_id, request_id):
    """Profile-specific correlation, not an authority or Core ID reinterpretation."""
    if not bstr(session_id, 16, True) or not bstr(request_id, 16, True):
        reject("REPLAY")
    counter = int.from_bytes(request_id[8:], "big")
    if request_id[:8] != session_id[:8] or counter == 0:
        reject("REPLAY")
    return counter


def decode_body(kind, raw):
    sizes = {"REQUEST": 16, "CHALLENGE": 4, "PROOF": 4, "ACCEPT": 10, "WITHDRAW": 5, "REJECT": 3}
    if kind not in sizes:
        reject("PROFILE_UNSUPPORTED")
    body = decode_deterministic(raw, REQUEST_LIMITS if kind == "REQUEST" else LIMITS)
    if (
        type(body) is not dict
        or any(type(k) is not int for k in body)
        or set(body) != set(range(sizes[kind]))
        or type(body[0]) is not int
        or body[0] != 1
    ):
        reject("PROFILE_UNSUPPORTED")
    valid = True
    if kind == "REQUEST":
        refs = body[10]
        valid = (
            type(body[1]) is str
            and body[1] in ("register", "renew")
            and text_id(body[2])
            and text_id(body[6])
            and all(bstr(body[k], 32) for k in (3, 4, 5, 8, 9, 11, 12))
            and type(body[7]) is bytes
            and 1 <= len(body[7]) <= 64
            and uint(body[13], 1, 60)
            and uint(body[14], 0, MAX_TIME)
            and (body[15] is None if body[1] == "register" else bstr(body[15], 32))
            and type(refs) is list
            and 1 <= len(refs) <= 64
        )
        if valid:
            valid = all(
                type(r) is list and len(r) == 2 and uint(r[0]) and r[0] in {int(x) for x in ObjectType} and bstr(r[1], 32) for r in refs
            )
        if valid:
            encoded = [canonical(r) for r in refs]
            valid = encoded == sorted(set(encoded)) and body[11] == digest(refs)
    elif kind == "CHALLENGE":
        valid = bstr(body[1], 32) and bstr(body[2], 32, True) and uint(body[3], 0, MAX_TIME)
    elif kind == "PROOF":
        valid = bstr(body[1], 32) and bstr(body[2], 32, True) and bstr(body[3], 32)
    elif kind == "ACCEPT":
        valid = (
            all(bstr(body[k], 32) for k in (1, 8, 9))
            and all(bstr(body[k], 16, True) for k in (2, 3))
            and uint(body[4], 1)
            and all(uint(body[k], 0, MAX_TIME) for k in (5, 6, 7))
            and 0 < body[6] - body[5] <= 60
            and body[7] == body[5] + (body[6] - body[5]) // 2
        )
    elif kind == "WITHDRAW":
        valid = bstr(body[1], 16, True) and bstr(body[2], 16, True) and uint(body[3], 1) and bstr(body[4], 32)
    elif kind == "REJECT":
        valid = bstr(body[1], 32)
        decode_error(canonical(body[2]))
    if not valid:
        reject("PROFILE_UNSUPPORTED")
    return body


def exporter_context(session_id, request_id, raw, challenge):
    if not bstr(session_id, 16, True) or not bstr(request_id, 16, True):
        reject("PROFILE_UNSUPPORTED")
    operation_counter(session_id, request_id)
    body = decode_body("REQUEST", raw)
    challenge = decode_body("CHALLENGE", canonical(challenge))
    if challenge[1] != sha256(raw).digest():
        reject("PROOF_INVALID")
    return canonical([CONTEXT_DOMAIN, 1, session_id, request_id, challenge[1], challenge[2], body[4], body[5], body[6], body[8], body[12]])


def accept_digest(session_id, request_id, body):
    if not bstr(session_id, 16, True) or not bstr(request_id, 16, True):
        reject("PROFILE_UNSUPPORTED")
    operation_counter(session_id, request_id)
    decode_body("ACCEPT", canonical(body))
    return digest([ACCEPT_DOMAIN, 1, session_id, request_id, body])


def validate_accept(body, raw, *, now, skew):
    body = decode_body("ACCEPT", canonical(body))
    req = decode_body("REQUEST", raw)
    if not uint(now, 0, MAX_TIME) or not uint(skew, 0, MAX_TIME):
        reject("PROFILE_UNSUPPORTED")
    if (
        body[1] != sha256(raw).digest()
        or body[8] != req[11]
        or body[9] != req[12]
        or body[6] - body[5] > req[13]
        or body[5] > now + skew
        or now >= body[6]
    ):
        reject("RECORD_STALE")
    return body


def frame(raw):
    if type(raw) is not bytes or not 1 <= len(raw) <= 65536:
        reject("OVER_CAPACITY")
    n = len(raw)
    width, flag = (1, 0) if n < 64 else (2, 0x4000) if n < 16384 else (4, 0x80000000)
    return (n | flag).to_bytes(width, "big") + raw


def unframe(raw):
    if type(raw) is not bytes or not raw:
        reject("PROFILE_UNSUPPORTED")
    width = 1 << (raw[0] >> 6)
    if len(raw) < width:
        reject("PROFILE_UNSUPPORTED")
    length = int.from_bytes(raw[:width], "big") & ((1 << (width * 8 - 2)) - 1)
    if length < 1 or length > 65536:
        reject("OVER_CAPACITY")
    if len(raw) != width + length or frame(raw[width:]) != raw:
        reject("PROFILE_UNSUPPORTED")
    return raw[width:]


def validate_carrier(*, stream_id, early_data, datagram, control_count):
    if (
        type(stream_id) is not int
        or stream_id != 0
        or early_data is not False
        or datagram is not False
        or type(control_count) is not int
        or control_count != 1
    ):
        reject("PROFILE_UNSUPPORTED")


@dataclass(frozen=True)
class ServiceConfig:
    """Immutable restrictive fixture pin. It never grants authority."""

    pinned: tuple

    @classmethod
    def from_request(cls, body):
        body = decode_body("REQUEST", canonical(body))
        return cls(tuple(body[k] for k in (2, 3, 4, 5, 6, 7, 8, 12)))

    @property
    def key(self):
        return self.pinned[1], self.pinned[4]


@dataclass(frozen=True)
class OfflineDecision:
    """SYNTHETIC receipt. No constructor call establishes authenticated trust."""

    request_digest: bytes
    connection: object
    session_id: bytes
    expires_at: int
    governing_profile: str
    verified_record_refs: tuple[bytes, ...]
    revision: int


@dataclass(frozen=True)
class OwnerHandle:
    connection: object
    session_id: bytes
    registration_id: bytes
    epoch: bytes
    generation: int


@dataclass
class Operation:
    raw: bytes
    challenge: bytes
    decision: OfflineDecision
    result: bytes | None = None
    proof: bytes | None = None


@dataclass
class Connection:
    transport: object
    session: bytes
    sequence: int = 0
    response_sequence: int = 0
    operation_high_water: int = 0
    operations: dict = field(default_factory=dict)
    pending: bytes | None = None
    owner: OwnerHandle | None = None
    current: bytes | None = None
    current_digest: bytes | None = None
    key: tuple | None = None
    denied: bool = False
    terminal: bool = False
    expires: int = 0
    dependencies: frozenset = frozenset()


class Coordinator:
    """Serialized pure coordinator, finite fixture connection set, no I/O loop.

    Four retained outcomes plus one pending operation; a separate monotonic
    operation high-water mark rejects evicted identities without tombstone growth.
    All counters belong to this full connection/session, never durable authority.
    """

    def __init__(
        self,
        configs,
        verifier,
        clock,
        *,
        epoch,
        nonce,
        registration_id,
        clock_skew_seconds,
        revision_source,
        offline_isolation_fixture=False,
    ):
        if (
            not configs
            or (len(configs) != 1 and not offline_isolation_fixture)
            or len(configs) > 2
            or any(type(c) is not ServiceConfig for c in configs)
            or len({c.key for c in configs}) != len(configs)
            or not bstr(epoch, 16, True)
            or not uint(clock_skew_seconds, 0, MAX_TIME)
        ):
            raise ValueError("explicit bounded offline configuration required")
        self.configs = {c.key: c for c in configs}
        self.verifier, self.clock = verifier, clock
        self.epoch, self.nonce, self.registration_id = epoch, nonce, registration_id
        self.skew = clock_skew_seconds
        self.revision_source = revision_source
        self.connections = {}
        self.owners = {}
        self.generation = 0
        self.last_time = None

    def _now(self):
        now = self.clock()
        if not uint(now, 0, MAX_TIME) or (self.last_time is not None and now < self.last_time):
            reject("INTERNAL")
        self.last_time = now
        return now

    def _connection(self, transport, sequence, *, create=False):
        if not uint(sequence, 1) or not bstr(transport.session, 16, True):
            reject("PROFILE_UNSUPPORTED")
        if transport.closed:
            reject("RECORD_STALE")
        state = self.connections.get(id(transport))
        if state is None:
            if not create:
                reject("REPLAY")
            # Only one unowned candidate plus the bounded configured owners.
            if len(self.connections) >= len(self.configs) + 1:
                reject("OVER_CAPACITY")
            state = Connection(transport, transport.session)
            self.connections[id(transport)] = state
        if state.transport is not transport or state.session != transport.session:
            reject("REPLAY")
        if transport.closed or state.terminal:
            reject("RECORD_STALE")
        if state.response_sequence == MAX_COUNTER:
            reject("OVER_CAPACITY")
        if sequence <= state.sequence:
            reject("REPLAY")
        state.sequence = sequence
        return state

    def _verify(self, state, raw, now):
        body = decode_body("REQUEST", raw)
        config = ServiceConfig.from_request(body)
        if self.configs.get(config.key) != config:
            reject("ROUTE_DENIED")
        result = self.verifier(raw, state.transport, now)
        if (
            type(result) is not OfflineDecision
            or result.connection is not state.transport
            or result.session_id != state.session
            or result.request_digest != sha256(raw).digest()
            or not uint(result.expires_at, 0, MAX_TIME)
            or result.expires_at <= now
            or not isinstance(result.governing_profile, str)
            or not result.governing_profile
            or type(result.verified_record_refs) is not tuple
            or result.verified_record_refs != tuple(r[1] for r in body[10])
            or not uint(result.revision, 1)
        ):
            reject("RECORD_UNTRUSTED")
        return result

    def request(self, transport, request_id, sequence, raw):
        now = self._now()
        counter = operation_counter(transport.session, request_id)
        body = decode_body("REQUEST", raw)
        state = self._connection(transport, sequence, create=True)
        if state.denied:
            reject("RECORD_REVOKED")
        old = state.operations.get(request_id)
        if old:
            if old.raw != raw:
                reject("REPLAY")
            if old.result is not None:
                return self._cached(state, request_id, old, now)
            challenge = decode_body("CHALLENGE", old.challenge)
            if state.pending != request_id or now >= challenge[3]:
                if state.pending == request_id:
                    self._clear_pending(state)
                reject("RECORD_STALE")
            return self._response(state, challenge)
        if counter != state.operation_high_water + 1:
            reject("REPLAY")
        if state.pending is not None:
            reject("OVER_CAPACITY")
        # Consume a structurally valid new operation before authority checks.
        # Failed/evicted identities cannot be re-executed with a fresh sequence.
        state.operation_high_water = counter
        # sent_at describes the REQUEST, not the later proof commit time.
        if abs(body[14] - now) > self.skew:
            reject("RECORD_STALE")
        key = (body[3], body[6])
        if body[1] == "register":
            if key in self.owners or state.owner is not None:
                reject("OVER_CAPACITY")
        elif state.owner is None or state.key != key or not self.eligible(transport) or body[15] != self._accept_hash(state):
            reject("RECORD_STALE")
        decision = self._verify(state, raw, now)
        nonce = self.nonce()
        if not bstr(nonce, 32, True):
            reject("INTERNAL")
        challenge = {0: 1, 1: sha256(raw).digest(), 2: nonce, 3: min(now + 5, decision.expires_at, MAX_TIME)}
        state.operations[request_id] = Operation(raw, canonical(challenge), decision)
        state.pending = request_id
        self._trim(state)
        return self._response(state, challenge)

    @staticmethod
    def _trim(state):
        completed = [key for key in state.operations if key != state.pending]
        for key in completed[:-4]:
            del state.operations[key]

    @classmethod
    def _clear_pending(cls, state):
        state.pending = None
        cls._trim(state)

    @staticmethod
    def _response(state, body):
        # Metadata for the unallocated carrier: never inserted into body CBOR.
        state.response_sequence += 1
        return body

    def _cached(self, state, request_id, operation, now):
        if state.denied:
            reject("RECORD_REVOKED")
        if state.current != request_id:
            reject("REPLAY")
        if not self.eligible(state.transport):
            reject("RECORD_STALE")
        return self._response(state, decode_body("ACCEPT", operation.result))

    def prove(self, transport, request_id, sequence, raw):
        now = self._now()
        operation_counter(transport.session, request_id)
        proof = decode_body("PROOF", raw)
        state = self._connection(transport, sequence)
        if state.denied:
            reject("RECORD_REVOKED")
        operation = state.operations.get(request_id)
        if operation is None:
            reject("REPLAY")
        if operation.result is not None:
            if operation.proof != raw:
                reject("REPLAY")
            return self._cached(state, request_id, operation, now)
        challenge = decode_body("CHALLENGE", operation.challenge)
        if state.pending != request_id or now >= challenge[3]:
            if state.pending == request_id:
                self._clear_pending(state)
            reject("RECORD_STALE")
        # A proof attempt consumes the pending challenge, including failures.
        self._clear_pending(state)
        if proof[1] != challenge[1] or proof[2] != challenge[2]:
            reject("PROOF_INVALID")
        context = exporter_context(state.session, request_id, operation.raw, challenge)
        try:
            expected = transport.export(EXPORTER_LABEL, context)
        except Exception:
            reject("PROFILE_UNSUPPORTED")
        if not bstr(expected, 32) or not compare_digest(expected, proof[3]):
            reject("PROOF_INVALID")
        decision = self._verify(state, operation.raw, now)
        if decision.revision != operation.decision.revision:
            reject("RECORD_STALE")
        body = decode_body("REQUEST", operation.raw)
        key = (body[3], body[6])
        registration_id = self.registration_id() if body[1] == "register" else None
        if body[1] == "register" and not bstr(registration_id, 16, True):
            reject("INTERNAL")
        # Sample after all potentially time-consuming fixture work. The revision
        # source is a read-only, non-reentrant snapshot under this serialized
        # fixture boundary. No callback runs between this check and installation.
        committed_at = self._now()
        if transport.closed or transport.session != state.session or state.denied or committed_at >= min(challenge[3], decision.expires_at):
            reject("RECORD_STALE")
        current_revision = self.revision_source()
        if not uint(current_revision, 1) or decision.revision != current_revision:
            reject("RECORD_STALE")
        if body[1] == "renew":
            if not self._eligible_at(state, committed_at) or state.key != key or body[15] != self._accept_hash(state):
                reject("RECORD_STALE")
        else:
            if key in self.owners:
                reject("OVER_CAPACITY")
            if self.generation == 2**64 - 1:
                reject("OVER_CAPACITY")
            self.generation += 1
            state.owner = OwnerHandle(transport, state.session, registration_id, self.epoch, self.generation)
            state.key = key
            self.owners[key] = state
        expires = min(committed_at + body[13], decision.expires_at, MAX_TIME)
        if expires <= committed_at:
            reject("RECORD_STALE")
        result = {
            0: 1,
            1: proof[1],
            2: state.owner.registration_id,
            3: self.epoch,
            4: state.owner.generation,
            5: committed_at,
            6: expires,
            7: committed_at + (expires - committed_at) // 2,
            8: body[11],
            9: body[12],
        }
        operation.result, operation.proof = canonical(result), raw
        state.current, state.expires = request_id, expires
        state.current_digest = accept_digest(state.session, request_id, result)
        state.dependencies = frozenset(decision.verified_record_refs)
        return self._response(state, result)

    def _accept_hash(self, state):
        return state.current_digest

    def eligible(self, transport):
        now = self._now()
        state = self.connections.get(id(transport))
        return bool(state and state.transport is transport and self._eligible_at(state, now))

    @staticmethod
    def _eligible_at(state, now):
        return bool(
            state
            and state.owner
            and not state.denied
            and not state.terminal
            and not state.transport.closed
            and state.transport.session == state.session
            and now < state.expires
        )

    def handle(self, transport):
        state = self.connections.get(id(transport))
        return state.owner if state and state.transport is transport else None

    def close_owner(self, handle):
        if type(handle) is not OwnerHandle:
            return False
        state = self.connections.get(id(handle.connection))
        if state is None or state.owner != handle or state.owner is None:
            return False
        state.terminal = True
        self._clear_pending(state)
        try:
            handle.connection.close()
        except Exception:
            return False
        if not handle.connection.closed:
            return False
        self.owners.pop(state.key, None)
        state.owner = None
        self.connections.pop(id(handle.connection), None)
        return True

    def poll(self):
        """Explicit offline timer tick; no scheduler or automatic background I/O."""
        now = self._now()
        for state in list(self.connections.values()):
            if state.pending is not None:
                challenge = decode_body("CHALLENGE", state.operations[state.pending].challenge)
                if now >= challenge[3]:
                    self._clear_pending(state)
            if state.owner is not None:
                if state.transport.closed or now >= state.expires:
                    self.close_owner(state.owner)
            elif state.pending is None or state.transport.closed:
                self.close_attempt(state.transport)

    def close_attempt(self, transport):
        """Cleanup an exact unowned fixture attempt; failed close retains quota."""
        state = self.connections.get(id(transport))
        if state is None or state.transport is not transport or state.owner is not None:
            return False
        state.terminal = True
        self._clear_pending(state)
        try:
            transport.close()
        except Exception:
            return False
        if not transport.closed:
            return False
        del self.connections[id(transport)]
        return True

    def withdraw(self, transport, sequence, raw):
        body = decode_body("WITHDRAW", raw)
        state = self._connection(transport, sequence)
        handle = state.owner
        if handle is None or (body[1], body[2], body[3], body[4]) != (
            handle.registration_id,
            handle.epoch,
            handle.generation,
            self._accept_hash(state),
        ):
            reject("REPLAY")
        return self.close_owner(handle)

    def invalidate_dependencies(self, dependencies):
        """Explicit semantic fixture only. No unauthenticated runtime event API."""
        for state in self.connections.values():
            pending_refs = () if state.pending is None else state.operations[state.pending].decision.verified_record_refs
            if (state.dependencies | frozenset(pending_refs)).intersection(dependencies):
                state.denied = True
                self._clear_pending(state)

    def counts(self):
        return {
            "owned": len(self.owners),
            "eligible": sum(self.eligible(s.transport) for s in self.owners.values()),
            "pending": sum(s.pending is not None for s in self.connections.values()),
            "completed": sum(op.result is not None for s in self.connections.values() for op in s.operations.values()),
        }


class ConnectBudget:
    """Pure scheduling fixture, no connection attempts or sleeps are executed."""

    def __init__(self):
        self.attempts = 0
        self.next_at = 0
        self.halted = False
        self.in_flight = False

    def start(self, now):
        if not uint(now, 0, MAX_TIME) or self.halted or self.in_flight or self.attempts >= 3 or now < self.next_at:
            return False
        self.attempts += 1
        self.in_flight = True
        return True

    def failed(self, now, *, transient):
        if not self.in_flight or not uint(now, 0, MAX_TIME) or type(transient) is not bool:
            raise ValueError("exact pending attempt required")
        self.in_flight = False
        self.halted = not transient or self.attempts == 3
        self.next_at = now + self.attempts
