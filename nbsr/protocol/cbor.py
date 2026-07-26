from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cbor2

from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.registry import ErrorCode


@dataclass(frozen=True, slots=True)
class CborLimits:
    max_total_bytes: int
    max_depth: int
    max_array_items: int
    max_map_pairs: int
    max_text_bytes: int
    max_byte_string_bytes: int

    def __post_init__(self) -> None:
        for value in (
            self.max_total_bytes,
            self.max_depth,
            self.max_array_items,
            self.max_map_pairs,
            self.max_text_bytes,
            self.max_byte_string_bytes,
        ):
            if type(value) is not int or value <= 0:
                raise ValueError("CBOR limits must be positive integers")


DEFAULT_LIMITS = CborLimits(
    max_total_bytes=65_536,
    max_depth=16,
    max_array_items=256,
    max_map_pairs=128,
    max_text_bytes=4_096,
    max_byte_string_bytes=32_768,
)


def _invalid() -> ProtocolViolation:
    return ProtocolViolation(
        ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
        "Unsupported or non-deterministic CBOR",
    )


def _unsupported() -> ProtocolViolation:
    return ProtocolViolation(
        ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
        "Unsupported CBOR profile value",
    )


def _over_capacity() -> ProtocolViolation:
    return ProtocolViolation(
        ErrorCode.NBSR_E_OVER_CAPACITY,
        "CBOR resource limit exceeded",
    )


def _encode_head(major: int, argument: int) -> bytes:
    initial = major << 5
    if argument < 24:
        return bytes((initial | argument,))
    if argument <= 0xFF:
        return bytes((initial | 24, argument))
    if argument <= 0xFFFF:
        return bytes((initial | 25,)) + argument.to_bytes(2, "big")
    if argument <= 0xFFFFFFFF:
        return bytes((initial | 26,)) + argument.to_bytes(4, "big")
    if argument <= 0xFFFFFFFFFFFFFFFF:
        return bytes((initial | 27,)) + argument.to_bytes(8, "big")
    raise _unsupported()


def _encode_value(
    value: object,
    limits: CborLimits,
    depth: int,
    active_containers: set[int],
    budget: int,
) -> bytes:
    if depth > limits.max_depth:
        raise _over_capacity()
    if value is None:
        encoded = b"\xf6"
        if len(encoded) > budget:
            raise _over_capacity()
        return encoded
    if value is False:
        encoded = b"\xf4"
        if len(encoded) > budget:
            raise _over_capacity()
        return encoded
    if value is True:
        encoded = b"\xf5"
        if len(encoded) > budget:
            raise _over_capacity()
        return encoded
    if type(value) is int:
        if value >= 0:
            encoded = _encode_head(0, value)
        else:
            encoded = _encode_head(1, -1 - value)
        if len(encoded) > budget:
            raise _over_capacity()
        return encoded
    if isinstance(value, bytes):
        if len(value) > limits.max_byte_string_bytes:
            raise _over_capacity()
        head = _encode_head(2, len(value))
        if len(head) + len(value) > budget:
            raise _over_capacity()
        return head + value
    if isinstance(value, str):
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise _unsupported() from exc
        if len(encoded) > limits.max_text_bytes:
            raise _over_capacity()
        head = _encode_head(3, len(encoded))
        if len(head) + len(encoded) > budget:
            raise _over_capacity()
        return head + encoded
    if isinstance(value, (list, tuple)):
        if len(value) > limits.max_array_items:
            raise _over_capacity()
        head = _encode_head(4, len(value))
        if len(head) > budget:
            raise _over_capacity()
        container_id = id(value)
        if container_id in active_containers:
            raise _unsupported()
        active_containers.add(container_id)
        try:
            parts = [head]
            remaining = budget - len(head)
            for item in value:
                encoded_item = _encode_value(
                    item,
                    limits,
                    depth + 1,
                    active_containers,
                    remaining,
                )
                parts.append(encoded_item)
                remaining -= len(encoded_item)
        finally:
            active_containers.remove(container_id)
        return b"".join(parts)
    if isinstance(value, dict):
        if len(value) > limits.max_map_pairs:
            raise _over_capacity()
        head = _encode_head(5, len(value))
        if len(head) > budget:
            raise _over_capacity()
        container_id = id(value)
        if container_id in active_containers:
            raise _unsupported()
        active_containers.add(container_id)
        try:
            remaining = budget - len(head)
            entries: list[tuple[bytes, object]] = []
            for key, item in value.items():
                encoded_key = _encode_value(
                    key,
                    limits,
                    depth + 1,
                    active_containers,
                    remaining,
                )
                entries.append((encoded_key, item))
                remaining -= len(encoded_key)
            entries.sort(key=lambda entry: entry[0])
            if any(previous[0] == current[0] for previous, current in zip(entries, entries[1:], strict=False)):
                raise _invalid()
            parts = [head]
            for encoded_key, item in entries:
                parts.append(encoded_key)
                encoded_item = _encode_value(
                    item,
                    limits,
                    depth + 1,
                    active_containers,
                    remaining,
                )
                parts.append(encoded_item)
                remaining -= len(encoded_item)
        finally:
            active_containers.remove(container_id)
        return b"".join(parts)
    raise _unsupported()


def encode_deterministic(
    value: object,
    limits: CborLimits = DEFAULT_LIMITS,
) -> bytes:
    return _encode_value(value, limits, 1, set(), limits.max_total_bytes)


class _StructuralScanner:
    def __init__(self, data: bytes, limits: CborLimits) -> None:
        self.data = data
        self.limits = limits
        self.offset = 0

    def scan(self) -> None:
        self._scan_item(1)
        if self.offset != len(self.data):
            raise _invalid()

    def _take(self, count: int) -> bytes:
        end = self.offset + count
        if end > len(self.data):
            raise _invalid()
        value = self.data[self.offset : end]
        self.offset = end
        return value

    def _argument(self, additional: int) -> int:
        if additional < 24:
            return additional
        widths = {24: 1, 25: 2, 26: 4, 27: 8}
        width = widths.get(additional)
        if width is None:
            raise _invalid()
        argument = int.from_bytes(self._take(width), "big")
        minimum = {24: 24, 25: 0x100, 26: 0x10000, 27: 0x100000000}[additional]
        if argument < minimum:
            raise _invalid()
        return argument

    def _scan_item(self, depth: int) -> None:
        if depth > self.limits.max_depth:
            raise _over_capacity()
        initial = self._take(1)[0]
        major = initial >> 5
        additional = initial & 0x1F

        if major in (0, 1):
            self._argument(additional)
            return
        if major in (2, 3):
            length = self._argument(additional)
            maximum = self.limits.max_byte_string_bytes if major == 2 else self.limits.max_text_bytes
            if length > maximum:
                raise _over_capacity()
            content = self._take(length)
            if major == 3:
                try:
                    content.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise _invalid() from exc
            return
        if major == 4:
            item_count = self._argument(additional)
            if item_count > self.limits.max_array_items:
                raise _over_capacity()
            for _ in range(item_count):
                self._scan_item(depth + 1)
            return
        if major == 5:
            pair_count = self._argument(additional)
            if pair_count > self.limits.max_map_pairs:
                raise _over_capacity()
            previous_key: bytes | None = None
            for _ in range(pair_count):
                key_start = self.offset
                self._scan_item(depth + 1)
                encoded_key = self.data[key_start : self.offset]
                if previous_key is not None and encoded_key <= previous_key:
                    raise _invalid()
                previous_key = encoded_key
                self._scan_item(depth + 1)
            return
        if major == 6:
            raise _unsupported()
        if major == 7 and additional in (20, 21, 22):
            return
        raise _unsupported()


def decode_deterministic(
    data: bytes,
    limits: CborLimits = DEFAULT_LIMITS,
) -> Any:
    if not isinstance(data, bytes):
        raise _unsupported()
    if len(data) > limits.max_total_bytes:
        raise _over_capacity()

    _StructuralScanner(data, limits).scan()
    try:
        value = cbor2.loads(data)
    except (cbor2.CBORDecodeError, UnicodeDecodeError, ValueError, TypeError) as exc:
        raise _invalid() from exc
    if encode_deterministic(value, limits) != data:
        raise _invalid()
    return value
