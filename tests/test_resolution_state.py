from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from nbsr.originset import (
    AuthorityKind,
    DerivedOriginSet,
    DnssecStatus,
    OriginEndpoint,
    PublicationMode,
)
from nbsr.protocol import ErrorCode, ProtocolViolation, RouteIntent
from nbsr.resolution_state import (
    NameClassification,
    ResolutionBinding,
    ResolutionContextStore,
)
from nbsr.synthetic import SyntheticMapping


CONTEXT_ID = bytes(range(32))
CONTEXT_DIGEST = bytes.fromhex(
    "630dcd2966c4336691125448bbb25b4ff412a49c732db2c8abc1b8581bd710dd",
)


def mapping(
    *,
    hostname: str = "api.example.com",
    ipv4: str = "127.80.0.1",
    ipv6: str = "fd00:6e62:7372::1",
    expires_at: int = 200,
) -> SyntheticMapping:
    return SyntheticMapping(
        hostname=hostname,
        ipv4=ipv4,
        ipv6=ipv6,
        expires_at=datetime.fromtimestamp(expires_at, UTC),
    )


def route_intent(
    *,
    canonical_name: str = "api.example.com",
    service_id: str = "svc_api",
    record_sequence: int = 42,
    resolution_context_digest: bytes = CONTEXT_DIGEST,
    created_at: int = 90,
    expires_at: int = 180,
    route_id: bytes = b"route-id-0000001",
) -> RouteIntent:
    return RouteIntent(
        intent_version=1,
        resolution_context_digest=resolution_context_digest,
        canonical_name=canonical_name,
        service_id=service_id,
        source_operator_id="op_source",
        source_edge_id="edge-source",
        destination_operator_id="op_destination",
        destination_edge_set=("edge-a",),
        allowed_transports=("tcp",),
        allowed_ports=(443,),
        created_at=created_at,
        expires_at=expires_at,
        record_sequence=record_sequence,
        policy_hash=b"p" * 32,
        route_id=route_id,
        lease_id=b"lease-id-0000001",
    )


def originset(
    *,
    service_id: str = "svc_api",
    service_record_generation: int = 42,
) -> DerivedOriginSet:
    return DerivedOriginSet(
        service_id=service_id,
        service_record_generation=service_record_generation,
        origin_generation=7,
        sequence=9,
        endpoints=(
            OriginEndpoint(
                address="192.0.2.10",
                port=443,
                transport="tcp",
                priority=10,
                weight=20,
                region="eu",
                locality="bud",
            ),
        ),
        publication_mode=PublicationMode.LEGACY_DNS,
        authority_kind=AuthorityKind.LOCAL_DERIVATION,
        issuer_id=b"resolver-a",
        not_before=80,
        expires_at=170,
        dnssec_status=DnssecStatus.SECURE,
    )


def resolution_binding(
    *,
    synthetic_mapping: SyntheticMapping | object | None = None,
    intent: RouteIntent | object | None = None,
    classification: NameClassification | object = NameClassification.NBSR_SERVICE,
    accepted_originset: DerivedOriginSet | object | None = None,
    resolution_context_id: bytes | object = CONTEXT_ID,
    expires_at: int | object = 150,
) -> ResolutionBinding:
    return ResolutionBinding(
        mapping=mapping() if synthetic_mapping is None else synthetic_mapping,
        route_intent=route_intent() if intent is None else intent,
        classification=classification,
        originset=accepted_originset,
        resolution_context_id=resolution_context_id,
        expires_at=expires_at,
    )


def legacy_binding(**changes: object) -> ResolutionBinding:
    values: dict[str, object] = {
        "classification": NameClassification.LEGACY_SERVICE,
        "accepted_originset": originset(),
    }
    values.update(changes)
    return resolution_binding(**values)


def assert_profile_unsupported(exc_info: pytest.ExceptionInfo[ProtocolViolation]) -> None:
    assert exc_info.value.code is ErrorCode.NBSR_E_PROFILE_UNSUPPORTED


def test_store_commits_one_binding_under_both_synthetic_addresses() -> None:
    binding = resolution_binding()
    store = ResolutionContextStore(max_entries=2)

    store.commit(binding, now=100)

    assert store.lookup(binding.mapping.ipv4, now=100) == binding
    assert store.lookup(binding.mapping.ipv6, now=100) == binding


def test_expiry_removes_both_reverse_entries_atomically() -> None:
    binding = resolution_binding(expires_at=101)
    store = ResolutionContextStore(max_entries=2)
    store.commit(binding, now=100)

    assert store.lookup(binding.mapping.ipv4, now=101) is None
    assert store.lookup(binding.mapping.ipv6, now=101) is None


@pytest.mark.parametrize(
    "context_id",
    (b"short", b"x" * 33, bytearray(CONTEXT_ID)),
)
def test_binding_requires_immutable_exact_32_byte_context_id(context_id: object) -> None:
    with pytest.raises(ProtocolViolation) as rejected:
        resolution_binding(resolution_context_id=context_id)

    assert_profile_unsupported(rejected)


def test_binding_requires_context_digest_match() -> None:
    intent = route_intent(resolution_context_digest=b"x" * 32)

    with pytest.raises(ProtocolViolation) as rejected:
        resolution_binding(intent=intent)

    assert_profile_unsupported(rejected)


def test_binding_requires_mapping_and_intent_name_match() -> None:
    with pytest.raises(ProtocolViolation) as rejected:
        resolution_binding(synthetic_mapping=mapping(hostname="other.example.com"))

    assert_profile_unsupported(rejected)


def test_binding_rejects_noncanonical_synthetic_address_text() -> None:
    expanded_ipv6 = mapping(ipv6="fd00:6e62:7372:0:0:0:0:1")

    with pytest.raises(ProtocolViolation) as rejected:
        resolution_binding(synthetic_mapping=expanded_ipv6)

    assert_profile_unsupported(rejected)


@pytest.mark.parametrize(
    ("synthetic_mapping", "intent", "expires_at"),
    (
        (mapping(expires_at=149), route_intent(), 150),
        (mapping(), route_intent(expires_at=149), 150),
        (mapping(), route_intent(), True),
        (mapping(), route_intent(), 90),
    ),
    ids=("mapping-expiry", "intent-expiry", "boolean-expiry", "nonpositive-window"),
)
def test_binding_expiry_is_exact_and_bounded(
    synthetic_mapping: SyntheticMapping,
    intent: RouteIntent,
    expires_at: object,
) -> None:
    with pytest.raises(ProtocolViolation) as rejected:
        resolution_binding(
            synthetic_mapping=synthetic_mapping,
            intent=intent,
            expires_at=expires_at,
        )

    assert_profile_unsupported(rejected)


def test_nbsr_binding_rejects_originset_and_legacy_requires_one() -> None:
    with pytest.raises(ProtocolViolation) as nbsr_rejected:
        resolution_binding(accepted_originset=originset())
    with pytest.raises(ProtocolViolation) as legacy_rejected:
        resolution_binding(classification=NameClassification.LEGACY_SERVICE)

    assert_profile_unsupported(nbsr_rejected)
    assert_profile_unsupported(legacy_rejected)


@pytest.mark.parametrize(
    "accepted_originset",
    (
        originset(service_id="svc_other"),
        originset(service_record_generation=41),
    ),
    ids=("service-id", "record-generation"),
)
def test_legacy_binding_requires_originset_identity_match(
    accepted_originset: DerivedOriginSet,
) -> None:
    with pytest.raises(ProtocolViolation) as rejected:
        legacy_binding(accepted_originset=accepted_originset)

    assert_profile_unsupported(rejected)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("synthetic_mapping", {}),
        ("intent", {}),
        ("classification", "nbsr-service"),
        ("accepted_originset", []),
    ),
)
def test_binding_rejects_mutable_or_inexact_inputs(field: str, value: object) -> None:
    changes: dict[str, object] = {field: value}
    if field == "accepted_originset":
        changes["classification"] = NameClassification.LEGACY_SERVICE

    with pytest.raises(ProtocolViolation) as rejected:
        resolution_binding(**changes)

    assert_profile_unsupported(rejected)


def test_binding_is_frozen() -> None:
    binding = resolution_binding()

    with pytest.raises((FrozenInstanceError, AttributeError)):
        binding.expires_at = 160  # type: ignore[misc]


def test_store_replaces_same_name_and_pair_atomically() -> None:
    first = resolution_binding()
    second = resolution_binding(
        intent=route_intent(
            resolution_context_digest=bytes.fromhex(
                "cd93782b7fb95559de14f738b65988af85d41dc1565f7c7d1ed2d035665b519c",
            ),
            route_id=b"route-id-0000002",
        ),
        resolution_context_id=b"c" * 32,
        expires_at=160,
    )
    store = ResolutionContextStore(max_entries=1)
    store.commit(first, now=100)

    store.commit(second, now=101)

    assert store.lookup(first.mapping.ipv4, now=101) == second
    assert store.lookup(first.mapping.ipv6, now=101) == second


def test_store_rejects_same_name_with_changed_pair_without_mutation() -> None:
    first = resolution_binding()
    changed_pair = resolution_binding(
        synthetic_mapping=mapping(
            ipv4="127.80.0.2",
            ipv6="fd00:6e62:7372::2",
        ),
    )
    store = ResolutionContextStore(max_entries=2)
    store.commit(first, now=100)

    with pytest.raises(ProtocolViolation) as rejected:
        store.commit(changed_pair, now=101)

    assert_profile_unsupported(rejected)
    assert store.lookup(first.mapping.ipv4, now=101) == first
    assert store.lookup(changed_pair.mapping.ipv4, now=101) is None


def test_store_rejects_live_address_collision_without_mutation() -> None:
    first = resolution_binding()
    other = resolution_binding(
        synthetic_mapping=mapping(
            hostname="other.example.com",
            ipv4=first.mapping.ipv4,
            ipv6="fd00:6e62:7372::2",
        ),
        intent=route_intent(canonical_name="other.example.com"),
    )
    store = ResolutionContextStore(max_entries=2)
    store.commit(first, now=100)

    with pytest.raises(ProtocolViolation) as rejected:
        store.commit(other, now=101)

    assert_profile_unsupported(rejected)
    assert store.lookup(first.mapping.ipv4, now=101) == first
    assert store.lookup(other.mapping.ipv6, now=101) is None


def test_store_capacity_fails_closed_and_never_evicts_live_state() -> None:
    first = resolution_binding()
    second = resolution_binding(
        synthetic_mapping=mapping(
            hostname="other.example.com",
            ipv4="127.80.0.2",
            ipv6="fd00:6e62:7372::2",
        ),
        intent=route_intent(canonical_name="other.example.com"),
    )
    store = ResolutionContextStore(max_entries=1)
    store.commit(first, now=100)

    with pytest.raises(ProtocolViolation) as rejected:
        store.commit(second, now=101)

    assert rejected.value.code is ErrorCode.NBSR_E_HANDLE_EXHAUSTED
    assert store.lookup(first.mapping.ipv4, now=101) == first
    assert store.lookup(second.mapping.ipv4, now=101) is None


def test_store_rejects_expired_commit_and_boolean_times() -> None:
    store = ResolutionContextStore(max_entries=1)

    for now in (150, True):
        with pytest.raises(ProtocolViolation) as rejected:
            store.commit(resolution_binding(), now=now)
        assert_profile_unsupported(rejected)


def test_store_validates_capacity_and_unknown_lookup() -> None:
    with pytest.raises(ValueError):
        ResolutionContextStore(max_entries=0)
    with pytest.raises(ValueError):
        ResolutionContextStore(max_entries=True)

    store = ResolutionContextStore(max_entries=1)
    assert store.lookup("127.80.0.99", now=100) is None


def test_expired_entry_frees_capacity_for_a_new_binding() -> None:
    first = resolution_binding(expires_at=101)
    second = resolution_binding(
        synthetic_mapping=mapping(
            hostname="other.example.com",
            ipv4="127.80.0.2",
            ipv6="fd00:6e62:7372::2",
        ),
        intent=replace(
            route_intent(canonical_name="other.example.com"),
            created_at=100,
        ),
    )
    store = ResolutionContextStore(max_entries=1)
    store.commit(first, now=100)

    store.commit(second, now=101)

    assert store.lookup(first.mapping.ipv4, now=101) is None
    assert store.lookup(second.mapping.ipv4, now=101) == second


class CountingNameIndex(dict[str, ResolutionBinding]):
    """Keep real index behavior while counting full-scan entry points."""

    def __init__(self) -> None:
        super().__init__()
        self.scans = 0

    def items(self):
        self.scans += 1
        return super().items()


def other_binding(*, expires_at: int = 170) -> ResolutionBinding:
    return resolution_binding(
        synthetic_mapping=mapping(
            hostname="other.example.com",
            ipv4="127.80.0.2",
            ipv6="fd00:6e62:7372::2",
        ),
        intent=route_intent(canonical_name="other.example.com"),
        expires_at=expires_at,
    )


def test_live_operations_skip_expiry_scans_before_earliest_expiry() -> None:
    store = ResolutionContextStore(max_entries=2)
    index = CountingNameIndex()
    store._by_name = index
    first = resolution_binding()
    second = other_binding()
    replacement = replace(first, expires_at=160)

    assert store.lookup("127.80.0.99", now=100) is None
    store.commit(first, now=100)
    store.commit(second, now=101)
    store.commit(replacement, now=102)

    assert store.lookup(first.mapping.ipv4, now=149) is replacement
    assert store.lookup(first.mapping.ipv6, now=149) is replacement
    assert store.lookup(second.mapping.ipv4, now=149) is second
    assert store.lookup("127.80.0.99", now=149) is None
    assert index.scans == 0


def test_expiry_scan_reuses_survivor_bound_and_skips_empty_store() -> None:
    store = ResolutionContextStore(max_entries=2)
    index = CountingNameIndex()
    store._by_name = index
    first = resolution_binding(expires_at=110)
    second = other_binding(expires_at=150)
    store.commit(first, now=100)
    store.commit(second, now=100)
    index.scans = 0

    assert store.lookup(first.mapping.ipv4, now=110) is None
    assert store.lookup(first.mapping.ipv6, now=110) is None
    assert store.lookup(second.mapping.ipv4, now=149) is second
    assert store.lookup(second.mapping.ipv6, now=149) is second
    assert index.scans == 1

    assert store.lookup(second.mapping.ipv4, now=150) is None
    assert store.lookup(second.mapping.ipv6, now=150) is None
    assert store.lookup("127.80.0.99", now=151) is None
    assert index.scans == 2


def test_shorter_replacement_expires_at_its_new_boundary() -> None:
    store = ResolutionContextStore(max_entries=2)
    first = resolution_binding(expires_at=150)
    second = other_binding()
    replacement = replace(first, expires_at=110)
    store.commit(first, now=100)
    store.commit(second, now=100)
    store.commit(replacement, now=101)

    assert store.lookup(first.mapping.ipv4, now=109) is replacement
    assert store.lookup(first.mapping.ipv6, now=109) is replacement
    assert store.lookup(first.mapping.ipv4, now=110) is None
    assert store.lookup(first.mapping.ipv6, now=110) is None
    assert store.lookup(second.mapping.ipv4, now=110) is second


def test_longer_replacement_preserves_the_next_other_expiry() -> None:
    store = ResolutionContextStore(max_entries=2)
    first = resolution_binding(expires_at=110)
    second = other_binding(expires_at=130)
    replacement = replace(first, expires_at=150)
    store.commit(first, now=100)
    store.commit(second, now=100)
    store.commit(replacement, now=101)

    assert store.lookup(first.mapping.ipv4, now=110) is replacement
    assert store.lookup(first.mapping.ipv6, now=110) is replacement
    assert store.lookup(second.mapping.ipv4, now=129) is second
    assert store.lookup(second.mapping.ipv6, now=130) is None
    assert store.lookup(second.mapping.ipv4, now=130) is None
    assert store.lookup(first.mapping.ipv4, now=149) is replacement
    assert store.lookup(first.mapping.ipv4, now=150) is None
    assert store.lookup(first.mapping.ipv6, now=150) is None


def test_equal_expiries_remove_all_aliases_without_clock_rollback_resurrection() -> None:
    store = ResolutionContextStore(max_entries=2)
    first = resolution_binding(expires_at=110)
    second = other_binding(expires_at=110)
    store.commit(first, now=100)
    store.commit(second, now=100)

    for binding in (first, second):
        assert store.lookup(binding.mapping.ipv4, now=109) is binding
        assert store.lookup(binding.mapping.ipv6, now=109) is binding

    assert store.lookup(first.mapping.ipv4, now=110) is None
    for now in (110, 100):
        for binding in (first, second):
            assert store.lookup(binding.mapping.ipv4, now=now) is None
            assert store.lookup(binding.mapping.ipv6, now=now) is None


def test_expired_pair_and_capacity_can_be_reused_by_another_name() -> None:
    store = ResolutionContextStore(max_entries=1)
    first = resolution_binding(expires_at=110)
    second = resolution_binding(
        synthetic_mapping=replace(first.mapping, hostname="other.example.com"),
        intent=route_intent(canonical_name="other.example.com"),
    )
    store.commit(first, now=100)

    store.commit(second, now=110)

    assert store.lookup(first.mapping.ipv4, now=110) is second
    assert store.lookup(first.mapping.ipv6, now=110) is second
    assert store.lookup(first.mapping.ipv4, now=100) is second
    assert store.lookup(first.mapping.ipv4, now=150) is None
    assert store.lookup(first.mapping.ipv6, now=150) is None


@pytest.mark.parametrize("rejection", ("changed-pair", "address-collision", "capacity"))
def test_rejected_commit_preserves_live_state_and_expiry_scan_bound(rejection: str) -> None:
    store = ResolutionContextStore(max_entries=1)
    index = CountingNameIndex()
    store._by_name = index
    first = resolution_binding(expires_at=150)
    candidate = other_binding(expires_at=110)
    if rejection == "changed-pair":
        candidate = replace(candidate, mapping=replace(first.mapping, ipv4="127.80.0.2"), route_intent=first.route_intent)
    elif rejection == "address-collision":
        candidate = replace(candidate, mapping=replace(candidate.mapping, ipv6=first.mapping.ipv6))
    store.commit(first, now=100)
    index.scans = 0

    with pytest.raises(ProtocolViolation) as rejected:
        store.commit(candidate, now=101)

    expected_code = ErrorCode.NBSR_E_HANDLE_EXHAUSTED if rejection == "capacity" else ErrorCode.NBSR_E_PROFILE_UNSUPPORTED
    assert rejected.value.code is expected_code
    assert store.lookup(first.mapping.ipv4, now=110) is first
    assert store.lookup(first.mapping.ipv6, now=110) is first
    assert store.lookup(candidate.mapping.ipv4, now=110) is None
    assert index.scans == 0
    assert store.lookup(first.mapping.ipv4, now=150) is None
    assert store.lookup(first.mapping.ipv6, now=150) is None


def test_rejected_commit_still_expires_other_entries_before_collision_check() -> None:
    store = ResolutionContextStore(max_entries=2)
    first = resolution_binding(expires_at=110)
    second = other_binding(expires_at=150)
    collision = replace(first, mapping=replace(first.mapping, ipv6=second.mapping.ipv6), expires_at=160)
    store.commit(first, now=100)
    store.commit(second, now=100)

    with pytest.raises(ProtocolViolation) as rejected:
        store.commit(collision, now=110)

    assert_profile_unsupported(rejected)
    assert store.lookup(first.mapping.ipv4, now=100) is None
    assert store.lookup(first.mapping.ipv6, now=100) is None
    assert store.lookup(second.mapping.ipv4, now=100) is second
    assert store.lookup(second.mapping.ipv6, now=100) is second
    assert store.lookup(second.mapping.ipv4, now=150) is None
    assert store.lookup(second.mapping.ipv6, now=150) is None


@pytest.mark.parametrize("invalid_operation", ("expired-commit", "invalid-binding", "invalid-address"))
def test_validation_rejection_does_not_expire_state_before_lock(invalid_operation: str) -> None:
    store = ResolutionContextStore(max_entries=1)
    first = resolution_binding(expires_at=110)
    store.commit(first, now=100)

    with pytest.raises(ProtocolViolation) as rejected:
        if invalid_operation == "expired-commit":
            store.commit(other_binding(expires_at=120), now=130)
        elif invalid_operation == "invalid-binding":
            store.commit({}, now=130)
        else:
            store.lookup("invalid-address", now=130)

    assert_profile_unsupported(rejected)
    assert store.lookup(first.mapping.ipv4, now=100) is first
    assert store.lookup(first.mapping.ipv6, now=100) is first
