from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType

from nbsr.federation.fields import _Record, _authority_target, _bytes, _common, _fail, _uint
from nbsr.federation.registry import AuthorityClass, ObjectType


@dataclass(frozen=True, slots=True)
class DiscoveryCandidate:
    source: str
    operator_id: bytes
    locator: str
    port: int
    transport_key_digest: bytes

    def __post_init__(self) -> None:
        if self.source not in {"DNS", "HTTPS", "STATIC"}:
            _fail("discovery source is not approved candidate metadata")
        _bytes(self.operator_id, 32, 32, "candidate Operator ID")
        _bytes(self.transport_key_digest, 32, 32, "candidate transport key")
        _uint(self.port, 1, 65_535, "candidate port")

    @property
    def authoritative(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class OperatorEndpointRecord(_Record):
    REQUIRED = set(range(1, 8)) | set(range(32, 43))
    ALLOWED = REQUIRED | {8, 31}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: object = None) -> OperatorEndpointRecord:
        payload = cls._decode(raw)
        _common(payload, ObjectType.OperatorEndpointRecord, cls.REQUIRED, cls.ALLOWED)
        issuer = payload[3]
        _bytes(payload[32], 32, 32, "operator_id")
        if issuer[1] not in {AuthorityClass.OPERATOR_ENDPOINT, AuthorityClass.DELEGATE} or issuer[4] != payload[32]:
            _fail("endpoint issuer is not exactly Operator ID bound")
        _bytes(payload[33], 1, 64, "endpoint_id")
        if type(payload[34]) is not str or not 1 <= len(payload[34].encode()) <= 255 or not re.fullmatch(r"[a-z0-9.-]+", payload[34]):
            _fail("endpoint locator is invalid")
        if "origin" in payload[34].split("."):
            _fail("Origin Endpoint exposure is forbidden")
        _uint(payload[35], 1, 3, "endpoint role")
        if payload[36] is not None and (type(payload[36]) is not str or not re.fullmatch(r"[a-z0-9-]{1,32}", payload[36])):
            _fail("endpoint region is invalid")
        if payload[37] != 1:
            _fail("transport profile is invalid")
        _uint(payload[38], 1, 65_535, "endpoint port")
        _uint(payload[39], 0, 65_535, "endpoint priority")
        _bytes(payload[40], 32, 32, "transport key digest")
        _uint(payload[41], 1, 4, "endpoint lifecycle")
        if (payload[41] == 4) != (payload[42] is not None):
            _fail("revoked endpoint requires exactly one revocation reference")
        if payload[42] is not None:
            _authority_target(payload[42], "revocation reference")
        return cls(MappingProxyType(payload))

    @property
    def endpoint_id(self) -> bytes:
        return self._payload[33]

    @property
    def locator(self) -> str:
        return self._payload[34]

    @property
    def role(self) -> int:
        return self._payload[35]

    @property
    def region(self) -> str | None:
        return self._payload[36]

    @property
    def transport_profile(self) -> int:
        return self._payload[37]

    @property
    def port(self) -> int:
        return self._payload[38]

    @property
    def transport_key_digest(self) -> bytes:
        return self._payload[40]

    @property
    def lifecycle(self) -> int:
        return self._payload[41]


class EndpointDirectory:
    def __init__(self) -> None:
        self._records: dict[tuple[bytes, bytes], OperatorEndpointRecord] = {}
        self._terminal: set[tuple[bytes, bytes]] = set()

    def publish(
        self,
        authenticated: object,
        *,
        expected_operator_id: bytes,
        expected_transport_key_digest: bytes,
        now: int,
    ) -> None:
        from nbsr.federation.cose import AuthenticatedFederationRecord

        if not isinstance(authenticated, AuthenticatedFederationRecord) or not isinstance(authenticated.record, OperatorEndpointRecord):
            _fail("endpoint record is not authenticated")
        record = authenticated.record
        record.require_valid_at(now)
        if record.operator_id != expected_operator_id:
            _fail("endpoint Operator ID binding is invalid")
        if record.transport_key_digest != expected_transport_key_digest:
            _fail("endpoint transport key binding is invalid")
        key = (record.operator_id, record.endpoint_id)
        if key in self._terminal and record.lifecycle != 4:
            _fail("terminal endpoint cannot resurrect")
        current_key = key
        current = self._records.get(key)
        if current is None and 8 in record._payload:
            predecessor = [
                (candidate_key, candidate)
                for candidate_key, candidate in self._records.items()
                if candidate.operator_id == record.operator_id and candidate.digest == record._payload[8]
            ]
            if len(predecessor) != 1:
                _fail("endpoint predecessor is missing or ambiguous")
            current_key, current = predecessor[0]
        if current is not None:
            record._require_lineage(current)
            if current_key != key:
                del self._records[current_key]
        self._records[key] = record
        if record.lifecycle == 4:
            self._terminal.add(key)

    def consider(self, candidate: DiscoveryCandidate, *, now: int | None = None) -> tuple[OperatorEndpointRecord, ...]:
        if now is None:
            return ()
        matches = tuple(
            item
            for item in self._records.values()
            if item.operator_id == candidate.operator_id
            and item.locator == candidate.locator
            and item.port == candidate.port
            and item.transport_key_digest == candidate.transport_key_digest
            and item.lifecycle == 1
            and item.not_before <= now <= item.expires_at
        )
        return tuple(sorted(matches, key=lambda item: (item._payload[39], item.endpoint_id)))

    def resolve(self, operator_id: bytes, endpoint_id: bytes, *, now: int) -> tuple[OperatorEndpointRecord, ...]:
        record = self._records.get((operator_id, endpoint_id))
        return (record,) if record is not None and record.lifecycle == 1 and record.not_before <= now <= record.expires_at else ()

    def resolve_origin(self, canonical_name: str) -> tuple[()]:
        return ()

    def static_trust_fallback(self, operator_id: bytes) -> tuple[()]:
        return ()
