"""Privacy-safe, bounded local observability for the WP2A Name Node."""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from threading import Lock

from nbsr.protocol import ErrorCode
from nbsr.protocol.fields import require_canonical_name
from nbsr.resolution_state import NameClassification


_EVENT_KINDS = frozenset(("resolution-failed", "resolution-succeeded"))
_DURATION_BUCKETS_MS = (1, 5, 10, 25, 50, 100, 250, 500, 1_000, 2_000)
_CAPACITY_BUCKETS = frozenset(("available", "exhausted"))
_AUDIT_ID_PATTERN = re.compile(r"[0-9a-f]{16}\Z")


def _duration_bucket(duration_ms: object) -> int:
    if type(duration_ms) not in (int, float) or duration_ms < 0:
        raise ValueError("duration_ms must be a non-negative number")
    for bucket in _DURATION_BUCKETS_MS:
        if duration_ms <= bucket:
            return bucket
    return _DURATION_BUCKETS_MS[-1]


@dataclass(frozen=True, slots=True)
class NameNodeEvent:
    event_kind: str
    classification: NameClassification | None
    error_code: ErrorCode | None
    service_audit_id: str
    duration_bucket_ms: int
    capacity_bucket: str

    def __post_init__(self) -> None:
        if self.event_kind not in _EVENT_KINDS:
            raise ValueError("event_kind is not allowed")
        if self.classification is not None and type(self.classification) is not NameClassification:
            raise TypeError("classification has an invalid type")
        if self.error_code is not None and type(self.error_code) is not ErrorCode:
            raise TypeError("error_code has an invalid type")
        if self.event_kind == "resolution-succeeded" and (self.classification is None or self.error_code is not None):
            raise ValueError("successful event fields are inconsistent")
        if self.event_kind == "resolution-failed" and self.error_code is None:
            raise ValueError("failed event requires an error code")
        if type(self.service_audit_id) is not str or _AUDIT_ID_PATTERN.fullmatch(self.service_audit_id) is None:
            raise ValueError("service_audit_id must be 16 lowercase hexadecimal characters")
        if self.duration_bucket_ms not in _DURATION_BUCKETS_MS:
            raise ValueError("duration_bucket_ms is not allowed")
        if self.capacity_bucket not in _CAPACITY_BUCKETS:
            raise ValueError("capacity_bucket is not allowed")

    @classmethod
    def create(
        cls,
        *,
        audit_key: bytes,
        canonical_name: str,
        event_kind: str,
        classification: NameClassification | None,
        error_code: ErrorCode | None,
        duration_ms: int | float,
        capacity_exhausted: bool,
    ) -> NameNodeEvent:
        if type(audit_key) is not bytes or not 32 <= len(audit_key) <= 64:
            raise ValueError("audit_key must contain 32 to 64 bytes")
        checked_name = require_canonical_name(canonical_name)
        audit_id = hmac.new(
            audit_key,
            checked_name.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()[:16]
        return cls(
            event_kind=event_kind,
            classification=classification,
            error_code=error_code,
            service_audit_id=audit_id,
            duration_bucket_ms=_duration_bucket(duration_ms),
            capacity_bucket="exhausted" if capacity_exhausted else "available",
        )


@dataclass(frozen=True, slots=True)
class NameNodeMetricsSnapshot:
    result_counts: tuple[tuple[str, int], ...]
    duration_counts: tuple[tuple[int, int], ...]
    capacity_counts: tuple[tuple[str, int], ...]


class BoundedNameNodeMetrics:
    """Aggregate only over the fixed event label sets."""

    def __init__(self) -> None:
        self._result_counts: dict[str, int] = {}
        self._duration_counts: dict[int, int] = {}
        self._capacity_counts: dict[str, int] = {}
        self._lock = Lock()

    def record(self, event: NameNodeEvent) -> None:
        if type(event) is not NameNodeEvent:
            raise TypeError("metrics require a NameNodeEvent")
        if event.error_code is None:
            result_label = f"{event.event_kind}:{event.classification.value}"
        else:
            result_label = f"{event.event_kind}:{int(event.error_code)}"
        with self._lock:
            self._result_counts[result_label] = self._result_counts.get(result_label, 0) + 1
            self._duration_counts[event.duration_bucket_ms] = self._duration_counts.get(event.duration_bucket_ms, 0) + 1
            self._capacity_counts[event.capacity_bucket] = self._capacity_counts.get(event.capacity_bucket, 0) + 1

    def snapshot(self) -> NameNodeMetricsSnapshot:
        with self._lock:
            return NameNodeMetricsSnapshot(
                result_counts=tuple(sorted(self._result_counts.items())),
                duration_counts=tuple(sorted(self._duration_counts.items())),
                capacity_counts=tuple(sorted(self._capacity_counts.items())),
            )
