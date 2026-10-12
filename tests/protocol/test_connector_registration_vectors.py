"""CRP-1 offline vectors. Fixture decisions/exporters are NOT live trust."""

from dataclasses import replace
from hashlib import sha256
import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from nbsr.protocol.cbor import encode_deterministic as encode
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.registry import ErrorCode


def test_offline_profile_available():
    assert importlib.util.find_spec("nbsr.connector_registration_offline") is not None


@pytest.fixture
def api():
    return importlib.import_module("nbsr.connector_registration_offline")


class Clock:
    now = 100

    def __call__(self):
        return self.now


class Transport:
    """Public deterministic exporter fixture, never a TLS connection."""

    def __init__(self, seed=b"a" * 32):
        self.session = b"s" * 16
        self.closed = False
        self.seed = seed
        self.contexts = []

    def export(self, label, context):
        self.contexts.append((label, context))
        # Deliberately NOT TLS derivation. Separate exporter vectors check HKDF.
        return sha256(self.seed + label + context).digest()

    def close(self):
        self.closed = True


def rid(counter, session=b"s" * 16):
    return session[:8] + counter.to_bytes(8, "big")


def request(service=b"v" * 32):
    refs = [[2, b"k" * 32], [4, b"d" * 32]]
    return {
        0: 1,
        1: "register",
        2: "connector.fixture",
        3: service,
        4: b"o" * 32,
        5: b"g" * 32,
        6: "gateway.fixture",
        7: b"fixture-key",
        8: b"t" * 32,
        9: b"k" * 32,
        10: refs,
        11: sha256(encode(refs)).digest(),
        12: b"p" * 32,
        13: 60,
        14: 100,
        15: None,
    }


class Authority:
    """Synthetic verifier receipt producer, not a cryptographic authority API."""

    def __init__(self, api):
        self.api = api
        self.error = None
        self.expires = 1000
        self.revision = 1
        self.calls = 0

    def __call__(self, raw, transport, now):
        self.calls += 1
        if self.error:
            raise ProtocolViolation(self.error)
        return self.api.OfflineDecision(
            request_digest=sha256(raw).digest(),
            connection=transport,
            session_id=transport.session,
            expires_at=self.expires,
            governing_profile="explicit-offline-registration-fixture",
            verified_record_refs=(b"k" * 32, b"d" * 32),
            revision=self.revision,
        )


@pytest.fixture
def rig(api):
    clock, transport, body = Clock(), Transport(), request()
    authority = Authority(api)
    config = api.ServiceConfig.from_request(body)
    gateway = api.Coordinator(
        [config],
        authority,
        clock,
        epoch=b"e" * 16,
        nonce=lambda: b"n" * 32,
        registration_id=lambda: b"r" * 16,
        clock_skew_seconds=0,
        revision_source=lambda: authority.revision,
    )
    return api, gateway, authority, clock, transport, body


def start(rig, request_id=rid(1), sequence=1, body=None):
    api, gateway, _, _, transport, original = rig
    raw = encode(original if body is None else body)
    challenge = gateway.request(transport, request_id, sequence, raw)
    context = api.exporter_context(transport.session, request_id, raw, challenge)
    proof = encode({0: 1, 1: sha256(raw).digest(), 2: challenge[2], 3: transport.export(api.EXPORTER_LABEL, context)})
    return raw, challenge, proof


def accepted(rig):
    raw, challenge, proof = start(rig)
    result = rig[1].prove(rig[4], rid(1), 2, proof)
    return raw, challenge, proof, result


def error(code):
    return (
        pytest.raises(ProtocolViolation, match="CRP-1")
        if code is None
        else pytest.raises(ProtocolViolation, check=lambda e: e.code is code)
    )


def test_crp01_register(rig):
    api, gateway, authority, _, transport, _ = rig
    raw, _, _, result = accepted(rig)
    assert result == {
        0: 1,
        1: sha256(raw).digest(),
        2: b"r" * 16,
        3: b"e" * 16,
        4: 1,
        5: 100,
        6: 160,
        7: 130,
        8: request()[11],
        9: b"p" * 32,
    }
    assert gateway.counts() == {"owned": 1, "eligible": 1, "pending": 0, "completed": 1}
    assert authority.calls == 2
    assert api.validate_accept(result, raw, now=100, skew=0) == result
    assert transport.contexts[-1][0] == b"EXPORTER-NBSR-Connector-Registration-v1"


def renew(rig, previous, request_id=rid(2), sequence=3):
    api, gateway, _, clock, transport, body = rig
    old_rid = rid(1) if request_id == rid(2) else rid(2)
    body = dict(body, **{})
    body.update({1: "renew", 14: clock.now, 15: api.accept_digest(transport.session, old_rid, previous)})
    _, _, proof = start(rig, request_id, sequence, body)
    return gateway.prove(transport, request_id, sequence + 1, proof)


def test_crp02_renew_extends_lease_preserves_handle(rig):
    old = accepted(rig)[3]
    rig[3].now = 130
    result = renew(rig, old)
    assert [result[k] for k in (2, 3, 4)] == [old[k] for k in (2, 3, 4)]
    assert (result[5], result[6], result[7]) == (130, 190, 160)


def test_crp03_retry_and_superseded_rejection(rig):
    api, gateway, _, clock, transport, body = rig
    raw, challenge, proof = start(rig)
    clock.now = 101
    assert gateway.request(transport, rid(1), 2, raw) == challenge
    old = gateway.prove(transport, rid(1), 3, proof)
    assert gateway.request(transport, rid(1), 4, raw) == old
    assert gateway.prove(transport, rid(1), 5, proof) == old
    clock.now = 130
    current = renew(rig, old, sequence=6)
    with error(ErrorCode.NBSR_E_REPLAY):
        gateway.request(transport, rid(1), 8, raw)
    assert gateway.counts()["owned"] == 1 and current[6] == 190


def test_crp04_withdraw(rig):
    api, gateway, _, _, transport, _ = rig
    result = accepted(rig)[3]
    body = {0: 1, 1: result[2], 2: result[3], 3: result[4], 4: api.accept_digest(transport.session, rid(1), result)}
    assert gateway.withdraw(transport, 3, encode(body))
    assert transport.closed and gateway.counts()["owned"] == 0


@pytest.mark.parametrize("key,value", [(2, "other"), (4, b"x" * 32), (7, b"other"), (8, b"x" * 32)])
def test_crp05_wrong_principal_pin(rig, key, value):
    rig[5][key] = value
    with error(ErrorCode.NBSR_E_ROUTE_DENIED):
        start(rig)
    assert rig[1].counts()["owned"] == 0


def test_crp06_missing_registration_authority(rig):
    rig[2].error = ErrorCode.NBSR_E_RECORD_UNTRUSTED
    with error(ErrorCode.NBSR_E_RECORD_UNTRUSTED):
        start(rig)
    assert rig[1].counts()["pending"] == 0


@pytest.mark.parametrize("key,value", [(3, b"x" * 32), (5, b"x" * 32), (6, "other"), (12, b"x" * 32)])
def test_crp07_scope_and_policy(rig, key, value):
    rig[5][key] = value
    with error(ErrorCode.NBSR_E_ROUTE_DENIED):
        start(rig)


@pytest.mark.parametrize("code", [ErrorCode.NBSR_E_RECORD_STALE, ErrorCode.NBSR_E_RECORD_REVOKED])
def test_crp08_authority_rechecked_at_commit(rig, code):
    proof = start(rig)[2]
    rig[2].error = code
    with error(code):
        rig[1].prove(rig[4], rid(1), 2, proof)
    assert rig[1].counts()["owned"] == 0


def test_crp09_verifier_stale_lineage_rejects(rig):
    rig[2].error = ErrorCode.NBSR_E_RECORD_STALE
    with error(ErrorCode.NBSR_E_RECORD_STALE):
        start(rig)


def test_crp10_cross_connection(rig):
    proof = start(rig)[2]
    other = Transport(b"b" * 32)
    with error(ErrorCode.NBSR_E_REPLAY):
        rig[1].prove(other, rid(1), 1, proof)
    assert rig[1].counts()["owned"] == 0


@pytest.mark.parametrize("mutation", ["output", "nonce", "label", "context"])
def test_crp11_bad_binding(rig, mutation):
    api, gateway, _, _, transport, _ = rig
    raw, challenge, proof = start(rig)
    body = api.decode_body("PROOF", proof)
    if mutation == "nonce":
        body[2] = b"x" * 32
    elif mutation == "output":
        body[3] = b"x" * 32
    else:
        context = api.exporter_context(transport.session, rid(1), raw, challenge)
        body[3] = transport.export(
            b"wrong" if mutation == "label" else api.EXPORTER_LABEL, context + b"x" if mutation == "context" else context
        )
    with error(ErrorCode.NBSR_E_PROOF_INVALID):
        gateway.prove(transport, rid(1), 2, encode(body))


@pytest.mark.parametrize("now", [105, 106])
def test_crp12_challenge_expiry(rig, now):
    proof = start(rig)[2]
    rig[3].now = now
    with error(ErrorCode.NBSR_E_RECORD_STALE):
        rig[1].prove(rig[4], rid(1), 2, proof)
    assert rig[1].counts()["pending"] == 0


def test_crp13_conflicting_retry(rig):
    accepted(rig)
    rig[5][13] = 30
    with error(ErrorCode.NBSR_E_REPLAY):
        start(rig, sequence=3)
    assert rig[1].counts()["owned"] == 1


def test_crp14_duplicate_owner(rig):
    accepted(rig)
    second = (*rig[:4], Transport(b"b" * 32), rig[5])
    with error(ErrorCode.NBSR_E_OVER_CAPACITY):
        start(second)
    assert rig[1].counts()["owned"] == 1 and not rig[4].closed


def test_crp15_lease_expires_between_challenge_and_commit(rig):
    api, gateway, _, clock, transport, body = rig
    old = accepted(rig)[3]
    clock.now = 159
    body = body | {1: "renew", 14: 159, 15: api.accept_digest(transport.session, rid(1), old)}
    proof = start(rig, rid(2), 3, body)[2]
    clock.now = 160
    with error(ErrorCode.NBSR_E_RECORD_STALE):
        gateway.prove(transport, rid(2), 4, proof)
    assert gateway.counts()["eligible"] == 0


def test_crp16_lost_response_retry_and_disconnect(rig):
    _, gateway, _, _, transport, _ = rig
    raw, _, proof, result = accepted(rig)
    assert gateway.prove(transport, rid(1), 3, proof) == result
    handle = gateway.handle(transport)
    assert gateway.close_owner(handle)
    with error(ErrorCode.NBSR_E_RECORD_STALE):
        gateway.request(transport, rid(1), 4, raw)
    assert gateway.counts()["owned"] == 0


def test_crp17_stale_cleanup(rig):
    accepted(rig)
    gateway = rig[1]
    old = gateway.handle(rig[4])
    assert gateway.close_owner(old)
    transport = Transport(b"b" * 32)
    second = (*rig[:4], transport, rig[5])
    accepted(second)
    assert not gateway.close_owner(old)
    assert gateway.counts()["owned"] == 1 and not transport.closed


@pytest.mark.parametrize("failure", ["noop", "raise"])
def test_crp18_failed_cleanup(rig, failure):
    accepted(rig)

    def close():
        if failure == "raise":
            raise OSError("fixture")

    rig[4].close = close
    assert not rig[1].close_owner(rig[1].handle(rig[4]))
    assert rig[1].counts()["owned"] == 1 and rig[1].counts()["eligible"] == 0


def test_crp20_denial_invalidates_cached_success(rig):
    raw = accepted(rig)[0]
    rig[1].invalidate_dependencies({b"d" * 32})
    with error(ErrorCode.NBSR_E_RECORD_REVOKED):
        rig[1].request(rig[4], rid(1), 3, raw)


@pytest.mark.parametrize("mutation", ["unknown", "version", "bool", "trailing", "indefinite", "oversize", "refs"])
def test_crp23_parser(rig, mutation):
    api, _, _, _, _, body = rig
    if mutation == "unknown":
        body[16] = 0
    if mutation == "version":
        body[0] = 2
    if mutation == "bool":
        body[13] = True
    if mutation == "refs":
        body[10] = body[10] * 33
    raw = encode(body)
    if mutation == "trailing":
        raw += b"\x00"
    if mutation == "indefinite":
        raw = b"\xbf\xff"
    if mutation == "oversize":
        raw = b"\x00" * 16385
    with pytest.raises(ProtocolViolation):
        api.decode_body("REQUEST", raw)


def test_crp23_pending_capacity_and_sequence(rig):
    start(rig)
    with error(ErrorCode.NBSR_E_REPLAY):
        start(rig)
    with error(ErrorCode.NBSR_E_OVER_CAPACITY):
        start(rig, rid(2), 2)
    assert rig[1].counts()["pending"] == 1


@pytest.mark.parametrize("stream,early,datagram", [(4, False, False), (0, True, False), (0, False, True)])
def test_crp23_control_only(api, stream, early, datagram):
    with error(ErrorCode.NBSR_E_PROFILE_UNSUPPORTED):
        api.validate_carrier(stream_id=stream, early_data=early, datagram=datagram, control_count=1)


def test_crp23_connect_budget(api):
    budget = api.ConnectBudget()
    assert budget.start(100)
    budget.failed(100, transient=True)
    assert not budget.start(100) and budget.start(101)
    budget.failed(101, transient=True)
    assert not budget.start(102) and budget.start(103)
    budget.failed(103, transient=True)
    assert not budget.start(1000)
    permanent = api.ConnectBudget()
    assert permanent.start(100)
    permanent.failed(100, transient=False)
    assert not permanent.start(1000)


def test_crp24_service_isolation(rig):
    api, _, authority, clock, _, body = rig
    b = request(b"b" * 32)
    b[10] = [[2, b"k" * 32], [4, b"z" * 32]]
    b[11] = sha256(encode(b[10])).digest()
    configs = [api.ServiceConfig.from_request(body), api.ServiceConfig.from_request(b)]
    with pytest.raises(ValueError):
        api.Coordinator(
            configs,
            authority,
            clock,
            epoch=b"e" * 16,
            nonce=lambda: b"n" * 32,
            registration_id=lambda: b"r" * 16,
            clock_skew_seconds=0,
            revision_source=lambda: authority.revision,
        )
    gateway = api.Coordinator(
        configs,
        authority,
        clock,
        epoch=b"e" * 16,
        nonce=lambda: b"n" * 32,
        registration_id=lambda: b"r" * 16,
        clock_skew_seconds=0,
        revision_source=lambda: authority.revision,
        offline_isolation_fixture=True,
    )

    def verify(raw, transport, now):
        decision = authority(raw, transport, now)
        decoded = api.decode_body("REQUEST", raw)
        return replace(decision, verified_record_refs=tuple(r[1] for r in decoded[10]))

    gateway.verifier = verify
    a_rig = (api, gateway, authority, clock, Transport(), body)
    b_rig = (api, gateway, authority, clock, Transport(b"b" * 32), b)
    accepted(a_rig)
    accepted(b_rig)
    assert gateway.counts()["eligible"] == 2
    gateway.invalidate_dependencies({b"d" * 32})
    assert gateway.eligible(b_rig[4]) and not gateway.eligible(a_rig[4])
    gateway.invalidate_dependencies({b"k" * 32})
    assert gateway.counts()["eligible"] == 0


def test_closed_connections_do_not_accumulate(rig):
    for _ in range(8):
        transport = Transport()
        accepted((*rig[:4], transport, rig[5]))
        assert rig[1].close_owner(rig[1].handle(transport))
    assert len(rig[1].connections) == 0


def test_withheld_proof_expires_and_releases_candidate(rig):
    start(rig)
    rig[3].now = 105
    rig[1].poll()
    assert rig[4].closed and rig[1].counts()["pending"] == 0
    assert len(rig[1].connections) == 0


@pytest.mark.parametrize("message", ["request", "proof"])
def test_stale_operation_cannot_clear_successor_pending(rig, message):
    old = accepted(rig)[3]
    body = rig[5] | {1: "renew", 15: rig[0].accept_digest(rig[4].session, rid(1), old)}
    raw, _, proof = start(rig, rid(2), 3, body)
    bad = rig[0].decode_body("PROOF", proof) | {3: b"x" * 32}
    with error(ErrorCode.NBSR_E_PROOF_INVALID):
        rig[1].prove(rig[4], rid(2), 4, encode(bad))
    successor = start(rig, rid(3), 5, body)[2]
    with pytest.raises(ProtocolViolation):
        if message == "request":
            rig[1].request(rig[4], rid(2), 6, raw)
        else:
            rig[1].prove(rig[4], rid(2), 6, proof)
    assert rig[1].prove(rig[4], rid(3), 7, successor)[6] == 160


def test_authority_revision_changed_before_commit_rejects(rig):
    proof = start(rig)[2]
    clock = rig[3]
    calls = 0

    def changed_revision():
        nonlocal calls
        calls += 1
        if calls == 2:
            rig[2].revision += 1
        return clock.now

    rig[1].clock = changed_revision
    with error(ErrorCode.NBSR_E_RECORD_STALE):
        rig[1].prove(rig[4], rid(1), 2, proof)
    assert rig[1].counts()["owned"] == 0


@pytest.mark.parametrize("revision", [True, 1.0])
def test_current_revision_snapshot_requires_exact_integer(rig, revision):
    proof = start(rig)[2]
    rig[1].revision_source = lambda: revision
    with error(ErrorCode.NBSR_E_RECORD_STALE):
        rig[1].prove(rig[4], rid(1), 2, proof)
    assert rig[1].counts()["owned"] == 0
    assert rig[1].counts()["pending"] == 0


@pytest.mark.parametrize("operation", ["register", "renew"])
def test_challenge_revision_change_requires_fresh_exchange(rig, operation):
    api, gateway, authority, clock, transport, body = rig
    counter, sequence = 1, 1
    previous = None
    if operation == "renew":
        previous = accepted(rig)[3]
        clock.now = 130
        body = body | {1: "renew", 14: 130, 15: api.accept_digest(transport.session, rid(1), previous)}
        counter, sequence = 2, 3
    owner = gateway.handle(transport)
    proof = start(rig, rid(counter), sequence, body)[2]
    authority.revision += 1
    with error(ErrorCode.NBSR_E_RECORD_STALE):
        gateway.prove(transport, rid(counter), sequence + 1, proof)
    assert gateway.handle(transport) is owner
    assert gateway.counts()["pending"] == 0
    if previous is not None:
        assert gateway.connections[id(transport)].expires == previous[6]
        assert gateway.eligible(transport)
    # Same consumed operation cannot be retried into success; a new one can.
    with error(ErrorCode.NBSR_E_RECORD_STALE):
        gateway.prove(transport, rid(counter), sequence + 2, proof)
    successor = start(rig, rid(counter + 1), sequence + 3, body)[2]
    result = gateway.prove(transport, rid(counter + 1), sequence + 4, successor)
    assert result[6] == clock.now + 60
    assert gateway.counts()["owned"] == 1


@pytest.mark.parametrize("size", [1, 63, 64, 16383, 16384, 65536])
def test_crp23_frame_boundaries(api, size):
    raw = b"x" * size
    assert api.unframe(api.frame(raw)) == raw


@pytest.mark.parametrize("raw", [b"", b"\x00", b"\x40\x01x", b"\x02x", b"\x01xx", b"\x80\x01\x00\x01"])
def test_crp23_invalid_frames(api, raw):
    with pytest.raises(ProtocolViolation):
        api.unframe(raw)


@pytest.mark.parametrize("field,value", [(0, True), (4, True), (6, 161), (7, 131), (8, b"x" * 32), (9, b"x" * 32)])
def test_client_rejects_invalid_acceptance(rig, field, value):
    raw, _, _, body = accepted(rig)
    body[field] = value
    with pytest.raises(ProtocolViolation):
        rig[0].validate_accept(body, raw, now=100, skew=0)


def test_expired_acceptance_never_ready(rig):
    raw, _, _, body = accepted(rig)
    with error(ErrorCode.NBSR_E_RECORD_STALE):
        rig[0].validate_accept(body, raw, now=160, skew=0)


def test_receipt_is_not_bare_authority(rig):
    rig[1].verifier = lambda *args: True
    with error(ErrorCode.NBSR_E_RECORD_UNTRUSTED):
        start(rig)


def test_pending_dependency_denial_prevents_commit(rig):
    proof = start(rig)[2]
    rig[1].invalidate_dependencies({b"d" * 32})
    with error(ErrorCode.NBSR_E_RECORD_REVOKED):
        rig[1].prove(rig[4], rid(1), 2, proof)


def test_failed_candidate_cleanup_stays_bounded(rig):
    start(rig)
    rig[4].close = lambda: None
    rig[3].now = 105
    rig[1].poll()
    assert len(rig[1].connections) == 1 and not rig[4].closed
    assert rig[1].counts()["pending"] == 0
    assert not rig[1].close_attempt(rig[4])


def test_more_than_four_renewals_evict_results_without_replaying(rig):
    raw, _, _, body = accepted(rig)
    handle = rig[1].handle(rig[4])
    for i in range(2, 11):
        rig[3].now += 10
        request_body = rig[5] | {1: "renew", 14: rig[3].now, 15: rig[0].accept_digest(rig[4].session, rid(i - 1), body)}
        proof = start(rig, rid(i), 2 * i - 1, request_body)[2]
        body = rig[1].prove(rig[4], rid(i), 2 * i, proof)
        assert rig[1].handle(rig[4]) == handle
        assert rig[1].counts()["completed"] == min(i, 4)
    assert body[6] == 250 and rig[1].eligible(rig[4]) and not rig[4].closed
    before_calls = rig[2].calls
    with error(ErrorCode.NBSR_E_REPLAY):
        rig[1].request(rig[4], rid(1), 21, raw)
    assert rig[2].calls == before_calls
    assert rig[1].connections[id(rig[4])].operation_high_water == 10


def test_crp_reject_reuses_frozen_error_schema(api):
    request_id = rid(1)
    body = {0: 1, 1: b"d" * 32, 2: {0: 1, 1: 3, 2: request_id, 3: False}}
    assert api.decode_body("REJECT", encode(body)) == body
    body[2][1] = True
    with pytest.raises(ProtocolViolation):
        api.decode_body("REJECT", encode(body))


def test_retained_byte_vectors_execute_gateway(rig):
    from scripts.generate_wp4_exporter_vectors import expand_label

    root = Path(__file__).resolve().parents[2] / "vectors/connector-registration-v1-counter"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for name, entry in manifest["artifacts"].items():
        data = (root / name).read_bytes()
        assert len(data) == entry["bytes"] and sha256(data).hexdigest() == entry["sha256"]

    def export(label, context):
        master = (root / "fixture-exporter-master.bin").read_bytes()
        secret = expand_label(master, label, sha256(b"").digest(), 32)
        return expand_label(secret, b"exporter", sha256(context).digest(), 32)

    rig[4].export = export
    raw = (root / "request.cbor").read_bytes()
    challenge = rig[1].request(rig[4], rid(1), 1, raw)
    assert encode(challenge) == (root / "challenge.cbor").read_bytes()
    result = rig[1].prove(rig[4], rid(1), 2, (root / "proof.cbor").read_bytes())
    assert encode(result) == (root / "accept.cbor").read_bytes()
    assert rig[1].withdraw(rig[4], 3, (root / "withdraw.cbor").read_bytes())


@pytest.mark.parametrize(
    "name",
    [
        "invalid-bool-lease.cbor",
        "invalid-unknown-key.cbor",
        "invalid-trailing.cbor",
        "invalid-duplicate.cbor",
        "invalid-nonpreferred.cbor",
        "invalid-indefinite.cbor",
    ],
)
def test_retained_negative_bytes_reject(api, name):
    root = Path(__file__).resolve().parents[2] / "vectors/connector-registration-v1-counter"
    with pytest.raises(ProtocolViolation):
        api.decode_body("REQUEST", (root / name).read_bytes())


def test_manifest_has_24_executable_mappings():
    import ast

    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root / "vectors/connector-registration-v1-counter/manifest.json").read_text(encoding="utf-8"))
    assert [case["id"] for case in manifest["cases"]] == [f"CRP-{n:02}" for n in range(1, 25)]
    for case in manifest["cases"]:
        assert case["pytest_nodes"]
        for node in case["pytest_nodes"]:
            path, name = node.split("::")
            tree = ast.parse((root / path).read_text(encoding="utf-8"))
            assert any(isinstance(definition, ast.FunctionDef) and definition.name == name for definition in tree.body)


def test_identifier_callback_cannot_commit_after_challenge_deadline(rig):
    proof = start(rig)[2]

    def delayed_identifier():
        rig[3].now = 105
        return b"r" * 16

    rig[1].registration_id = delayed_identifier
    with error(ErrorCode.NBSR_E_RECORD_STALE):
        rig[1].prove(rig[4], rid(1), 2, proof)
    assert rig[1].counts()["owned"] == 0


@pytest.mark.parametrize("counter", [0, 2, 2**64 - 1])
def test_counter_starts_at_one_without_skipping(rig, counter):
    with error(ErrorCode.NBSR_E_REPLAY):
        start(rig, rid(counter))
    assert rig[2].calls == 0


def test_request_prefix_is_bound_to_session(rig):
    with error(ErrorCode.NBSR_E_REPLAY):
        start(rig, rid(1, b"x" * 16))
    assert rig[2].calls == 0


def test_full_session_binding_even_when_prefix_matches(rig):
    raw, _, proof = start(rig)
    other = Transport(b"a" * 32)
    other.session = b"s" * 8 + b"x" * 8
    rig[1].request(other, rid(1), 1, raw)
    with error(ErrorCode.NBSR_E_PROOF_INVALID):
        rig[1].prove(other, rid(1), 2, proof)
    assert rig[1].counts()["owned"] == 0


def test_counter_exhaustion_preserves_owner(rig):
    body = accepted(rig)[3]
    state = rig[1].connections[id(rig[4])]
    # Boundary-only state injection; not a claim that 2**64 exchanges ran.
    state.operation_high_water = 2**64 - 2
    request_body = rig[5] | {1: "renew", 15: rig[0].accept_digest(rig[4].session, rid(1), body)}
    proof = start(rig, rid(2**64 - 1), 3, request_body)[2]
    rig[1].prove(rig[4], rid(2**64 - 1), 4, proof)
    owner = rig[1].handle(rig[4])
    with error(ErrorCode.NBSR_E_REPLAY):
        start(rig, rid(0), 5, request_body)
    with error(ErrorCode.NBSR_E_REPLAY):
        start(rig, rid(1), 6, request_body)
    assert rig[1].handle(rig[4]) == owner and rig[1].eligible(rig[4])
    assert not rig[4].closed and state.operation_high_water == 2**64 - 1


def test_pending_does_not_consume_next_operation_counter(rig):
    raw, challenge, proof = start(rig)
    state = rig[1].connections[id(rig[4])]
    assert state.operation_high_water == 1
    with error(ErrorCode.NBSR_E_OVER_CAPACITY):
        start(rig, rid(2), 2)
    assert state.operation_high_water == 1
    assert rig[1].request(rig[4], rid(1), 3, raw) == challenge
    rig[1].prove(rig[4], rid(1), 4, proof)


def test_same_counter_changed_body_rejects_without_verifier(rig):
    accepted(rig)
    calls = rig[2].calls
    with error(ErrorCode.NBSR_E_REPLAY):
        start(rig, rid(1), 3, rig[5] | {13: 30})
    assert rig[2].calls == calls and rig[1].counts()["owned"] == 1


def test_new_counter_cannot_change_service(rig):
    old = accepted(rig)[3]
    calls = rig[2].calls
    body = rig[5] | {1: "renew", 3: b"x" * 32, 15: rig[0].accept_digest(rig[4].session, rid(1), old)}
    with error(ErrorCode.NBSR_E_RECORD_STALE):
        start(rig, rid(2), 3, body)
    assert rig[2].calls == calls and rig[1].eligible(rig[4])


def test_envelope_directions_have_independent_sequences(rig):
    raw, challenge, proof = start(rig, sequence=10)
    state = rig[1].connections[id(rig[4])]
    assert state.sequence == 10 and state.response_sequence == 1
    assert rig[1].request(rig[4], rid(1), 20, raw) == challenge
    assert state.sequence == 20 and state.response_sequence == 2 and state.operation_high_water == 1
    rig[1].prove(rig[4], rid(1), 30, proof)
    assert state.response_sequence == 3 and state.operation_high_water == 1


@pytest.mark.parametrize("finish", ["request_expiry", "deny", "failed_close"])
def test_pending_completion_always_trims_to_four(rig, finish):
    body = accepted(rig)[3]
    for i in range(2, 5):
        req = rig[5] | {1: "renew", 15: rig[0].accept_digest(rig[4].session, rid(i - 1), body)}
        proof = start(rig, rid(i), 2 * i - 1, req)[2]
        body = rig[1].prove(rig[4], rid(i), 2 * i, proof)
    req = rig[5] | {1: "renew", 15: rig[0].accept_digest(rig[4].session, rid(4), body)}
    raw, _, _ = start(rig, rid(5), 9, req)
    state = rig[1].connections[id(rig[4])]
    assert len(state.operations) == 5 and state.pending == rid(5)
    if finish == "request_expiry":
        rig[3].now = 105
        with error(ErrorCode.NBSR_E_RECORD_STALE):
            rig[1].request(rig[4], rid(5), 10, raw)
    elif finish == "deny":
        rig[1].invalidate_dependencies({b"d" * 32})
    else:
        rig[4].close = lambda: None
        assert not rig[1].close_owner(rig[1].handle(rig[4]))
    assert state.pending is None and len(state.operations) == 4


def test_failed_renewals_can_evict_result_without_losing_current_acceptance(rig):
    body = accepted(rig)[3]
    req = rig[5] | {1: "renew", 15: rig[0].accept_digest(rig[4].session, rid(1), body)}
    for i in range(2, 6):
        proof = start(rig, rid(i), 2 * i - 1, req)[2]
        bad = rig[0].decode_body("PROOF", proof) | {3: b"x" * 32}
        with error(ErrorCode.NBSR_E_PROOF_INVALID):
            rig[1].prove(rig[4], rid(i), 2 * i, encode(bad))
    assert rid(1) not in rig[1].connections[id(rig[4])].operations
    assert rig[1].eligible(rig[4])
    proof = start(rig, rid(6), 11, req)[2]
    assert rig[1].prove(rig[4], rid(6), 12, proof)[4] == body[4]


def test_response_sequence_exhaustion_preserves_existing_owner(rig):
    body = accepted(rig)[3]
    state = rig[1].connections[id(rig[4])]
    state.response_sequence = 2**64 - 1
    with error(ErrorCode.NBSR_E_OVER_CAPACITY):
        start(rig, rid(2), 3, rig[5] | {1: "renew", 15: rig[0].accept_digest(rig[4].session, rid(1), body)})
    assert rig[1].eligible(rig[4]) and not rig[4].closed and state.operation_high_water == 1


def test_cache_eviction_preserves_separately_admitted_work(rig):
    from nbsr.connector_control_model import Binding, CompletionGrace, Model, Permission

    binding = Binding("fixture", "service", "gateway", "operator", "issuer", 1, "fixture")
    permission = Permission(binding, 1000, 500, CompletionGrace("explicit-continuity-fixture", 30))
    model = Model(binding, lambda *args: permission, rig[3], lease=60, attempts=1, retry_delay=0)
    attempt = model.begin(rig[4], binding)
    assert model.authenticate(attempt)
    ticket = model.register(attempt)
    assert model.confirm(attempt, ticket)
    work = model.admit_work(attempt, deadline=400)
    body = accepted(rig)[3]
    for i in range(2, 8):
        rig[3].now += 10
        req = rig[5] | {1: "renew", 14: rig[3].now, 15: rig[0].accept_digest(rig[4].session, rid(i - 1), body)}
        proof = start(rig, rid(i), 2 * i - 1, req)[2]
        body = rig[1].prove(rig[4], rid(i), 2 * i, proof)
        ticket = model.renew(attempt, ticket)
        assert ticket is not None
        assert work.owner is attempt and work.deadline == 400 and not work.cancelled and not work.completed
    assert not rig[4].closed and rig[1].counts()["completed"] == 4


@pytest.mark.parametrize("trace_index", range(4))
def test_retained_counter_traces_execute_coordinator(rig, trace_index):
    root = Path(__file__).resolve().parents[2] / "vectors/connector-registration-v1-counter"
    trace = json.loads((root / "counter-traces.json").read_text(encoding="utf-8"))[trace_index]
    gateway, transport = rig[1], rig[4]
    if int(trace["seed_high_water"]):
        state = gateway._connection(transport, 1, create=True)
        state.operation_high_water = int(trace["seed_high_water"])
    requests, proofs = {}, {}
    current = None
    current_id = None
    for sequence, step in enumerate(trace["steps"], 100):
        request_id = bytes.fromhex(step["request_id_hex"])
        if step["kind"] == "request":
            if request_id not in requests:
                body = rig[5].copy()
                if current is not None:
                    body |= {1: "renew", 15: rig[0].accept_digest(transport.session, current_id, current)}
                requests[request_id] = encode(body)
            raw = requests[request_id]
            if step["changed_body"]:
                raw = encode(rig[0].decode_body("REQUEST", raw) | {13: 30})

            def call():
                return gateway.request(transport, request_id, sequence, raw)
        else:

            def call():
                return gateway.prove(transport, request_id, sequence, proofs[request_id])

        if step["expected"] in ("REPLAY", "OVER_CAPACITY"):
            with error(getattr(ErrorCode, "NBSR_E_" + step["expected"])):
                call()
        else:
            result = call()
            if step["expected"] == "CHALLENGE":
                context = rig[0].exporter_context(transport.session, request_id, requests[request_id], result)
                proofs[request_id] = encode({0: 1, 1: result[1], 2: result[2], 3: transport.export(rig[0].EXPORTER_LABEL, context)})
            else:
                current, current_id = result, request_id
        state = gateway.connections.get(id(transport))
        assert (state.operation_high_water if state else 0) == int(step["high_water"])
        assert (sum(key != state.pending for key in state.operations) if state else 0) == step["retained"]
        pending = None if state is None or state.pending is None else str(int.from_bytes(state.pending[8:], "big"))
        assert pending == step["pending"]
