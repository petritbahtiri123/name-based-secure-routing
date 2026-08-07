from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from nbsr.federation.fields import (
    _Record,
    _authority_reference,
    _authority_target,
    _bytes,
    _common,
    _fail,
    _uint,
)
from nbsr.federation.registry import AuthorityClass, ObjectType


SERVICE_ID_DOMAIN = b"NBSR-FEDERATION-SERVICE-ID-v1\x00"


def _canonical_name(value: object) -> str:
    if type(value) is not str:
        _fail("name_scope must be text")
    try:
        encoded = value.encode("ascii")
        idna = value.encode("idna").decode("ascii")
    except UnicodeError:
        _fail("name_scope is not a canonical A-label")
    if (
        not 1 <= len(encoded) <= 255
        or value != value.lower()
        or value != unicodedata.normalize("NFC", value)
        or value != idna
        or value.endswith(".")
    ):
        _fail("name_scope must be the exact lowercase NFC A-label form")
    for label in value.split("."):
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label):
            _fail("name_scope contains an invalid A-label")
        if label.startswith("xn--"):
            try:
                if label.encode("ascii").decode("idna").encode("idna").decode("ascii") != label:
                    _fail("name_scope contains a malformed ACE label")
            except UnicodeError:
                _fail("name_scope contains a malformed ACE label")
    return value


def derive_service_id(genesis_owner_operator_id: bytes, canonical_name: str) -> bytes:
    _bytes(genesis_owner_operator_id, 32, 32, "genesis owner Operator ID")
    name = _canonical_name(canonical_name)
    encoded = name.encode("utf-8")
    return hashlib.sha256(SERVICE_ID_DOMAIN + genesis_owner_operator_id + len(encoded).to_bytes(2, "big") + encoded).digest()


@dataclass(frozen=True, slots=True)
class OwnershipTransitionBinding:
    """Trusted output of independently validated transfer/recovery semantics.

    This is not a transport container or signature-threshold proof. The exact
    multi-signature packaging remains unfrozen and must be validated before a
    binding is constructed at an integration boundary.
    """

    digest: bytes
    accepted: bool
    object_type: ObjectType
    transfer_state: int
    service_id: bytes
    name_scope: str
    old_owner_id: bytes
    new_owner_id: bytes
    old_generation: int
    new_generation: int
    dual_authorized: bool


@dataclass(frozen=True, slots=True)
class NameOwnershipRecord(_Record):
    REQUIRED = {1, 2, 3, 4, 5, 6, 7, 32, 33, 34, 36, 37}
    ALLOWED = REQUIRED | {8, 31, 35}

    @classmethod
    def from_bytes(cls, raw: bytes, *, context: Mapping[str, object] | None = None) -> NameOwnershipRecord:
        payload = cls._decode(raw)
        _common(payload, ObjectType.NameOwnershipRecord, cls.REQUIRED, cls.ALLOWED)
        issuer = _authority_reference(payload[3], "issuer_id")
        owner = _authority_reference(payload[33], "owner_reference")
        if issuer[1] != AuthorityClass.NAME_OWNER or owner[1] != AuthorityClass.NAME_OWNER:
            _fail("ownership authority class must be NAME_OWNER")
        if owner[4] is None or owner[2] != owner[4] or issuer[2] != owner[2] or issuer[4] != owner[4]:
            _fail("owner authority must bind one exact Operator ID")
        name = _canonical_name(payload[32])
        _bytes(payload[34], 32, 32, "service_id")
        if payload[4] == 1 and payload[5] == 1 and payload[34] != derive_service_id(owner[4], name):
            _fail("service_id does not match genesis owner and canonical name")
        if 35 in payload and payload[35] is not None:
            _bytes(payload[35], 32, 32, "bootstrap_evidence_digest")
        _uint(payload[36], 0, 3, "ownership transfer state")
        if payload[37] is not None:
            _authority_target(payload[37], "revocation_reference")
        return cls(MappingProxyType(payload))

    @property
    def name_scope(self) -> str:
        return self._payload[32]

    @property
    def owner_operator_id(self) -> bytes:
        return self._payload[33][4]

    @property
    def operator_id(self) -> bytes:
        return self.owner_operator_id

    @property
    def service_id(self) -> bytes:
        return self._payload[34]

    @property
    def revoked(self) -> bool:
        return self._payload[37] is not None

    def require_newer_than(
        self,
        current: NameOwnershipRecord,
        *,
        transition: OwnershipTransitionBinding | None = None,
    ) -> bool:
        if not isinstance(current, NameOwnershipRecord):
            _fail("ownership lineage object type mismatch")
        candidate_version = (self.generation, self.sequence)
        current_version = (current.generation, current.sequence)
        if candidate_version < current_version:
            _fail("ownership update is a rollback")
        if candidate_version == current_version:
            if self.digest == current.digest:
                return False
            _fail("equal-version ownership record equivocates")
        if current.revoked:
            _fail("terminal ownership state cannot be resurrected")
        if self.name_scope != current.name_scope or self.service_id != current.service_id:
            _fail("ownership identity fields are immutable")
        if self.generation == current.generation:
            if self.sequence != current.sequence + 1 or self._payload.get(8) != current.digest:
                _fail("ordinary ownership continuity is invalid")
            if self.owner_operator_id != current.owner_operator_id or self._payload[36] in {2, 3}:
                _fail("ordinary ownership update cannot transfer authority")
        elif self.generation == current.generation + 1 and self.sequence == 1 and self._payload.get(8) == current.digest:
            state = self._payload[36]
            if state not in {2, 3}:
                _fail("new ownership generation requires transfer or recovery")
            if (
                not isinstance(transition, OwnershipTransitionBinding)
                or type(transition.digest) is not bytes
                or len(transition.digest) != 32
                or not transition.accepted
                or transition.object_type is not ObjectType.NameOwnershipRecord
                or transition.transfer_state != state
                or transition.service_id != self.service_id
                or transition.name_scope != self.name_scope
                or transition.old_owner_id != current.owner_operator_id
                or transition.new_owner_id != self.owner_operator_id
                or transition.old_generation != current.generation
                or transition.new_generation != self.generation
                or (state == 2 and not transition.dual_authorized)
                or (state == 3 and transition.dual_authorized)
            ):
                _fail("ownership transition binding is invalid")
        else:
            _fail("new ownership generation continuity is invalid")
        return True
