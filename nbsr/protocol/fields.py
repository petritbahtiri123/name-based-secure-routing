from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Callable, TypeVar

from nbsr.protocol.cbor import encode_deterministic
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.registry import ErrorCode


MAX_UINT64 = 2**64 - 1
MAX_TIMESTAMP = 253_402_300_799
TEXT_ID_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")
DNS_LABEL_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")

T = TypeVar("T")


def _invalid(
    message: str,
    code: ErrorCode = ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
) -> ProtocolViolation:
    return ProtocolViolation(code, message)


def require_uint(
    value: object,
    *,
    minimum: int = 0,
    maximum: int = MAX_UINT64,
    message: str = "Invalid unsigned integer",
    code: ErrorCode = ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise _invalid(message, code)
    return value


def require_bytes(
    value: object,
    *,
    minimum: int,
    maximum: int,
    message: str = "Invalid byte string",
    code: ErrorCode = ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
) -> bytes:
    if not isinstance(value, bytes) or not minimum <= len(value) <= maximum:
        raise _invalid(message, code)
    return bytes(value)


def require_text_id(
    value: object,
    *,
    message: str = "Invalid textual NBSR identifier",
    code: ErrorCode = ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
) -> str:
    if not isinstance(value, str):
        raise _invalid(message, code)
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise _invalid(message, code) from exc
    if not 1 <= len(encoded) <= 64 or TEXT_ID_PATTERN.fullmatch(value) is None:
        raise _invalid(message, code)
    return value


def require_canonical_name(value: object) -> str:
    message = "Invalid canonical NBSR name"
    if not isinstance(value, str):
        raise _invalid(message, ErrorCode.NBSR_E_NAME_INVALID)
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise _invalid(message, ErrorCode.NBSR_E_NAME_INVALID) from exc
    if not 1 <= len(encoded) <= 253 or value.endswith(".") or value != value.lower():
        raise _invalid(message, ErrorCode.NBSR_E_NAME_INVALID)
    labels = value.split(".")
    if any(DNS_LABEL_PATTERN.fullmatch(label) is None for label in labels):
        raise _invalid(message, ErrorCode.NBSR_E_NAME_INVALID)
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise _invalid(message, ErrorCode.NBSR_E_NAME_INVALID)


def normalize_presentation_name(value: str) -> str:
    if not isinstance(value, str):
        raise _invalid("Invalid presentation name", ErrorCode.NBSR_E_NAME_INVALID)
    without_dot = value[:-1] if value.endswith(".") else value
    try:
        canonical = without_dot.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise _invalid("Invalid presentation name", ErrorCode.NBSR_E_NAME_INVALID) from exc
    return require_canonical_name(canonical)


def require_timestamp(value: object, *, message: str = "Invalid timestamp") -> int:
    return require_uint(value, maximum=MAX_TIMESTAMP, message=message)


def require_sequence(value: object, *, message: str = "Invalid sequence") -> int:
    return require_uint(value, minimum=1, message=message)


def require_port(value: object) -> int:
    return require_uint(value, minimum=1, maximum=65_535, message="Invalid port")


def require_time_window(
    start: object,
    end: object,
    *,
    maximum_lifetime: int | None,
    code: ErrorCode = ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
) -> tuple[int, int]:
    valid_start = require_timestamp(start)
    valid_end = require_timestamp(end)
    if valid_end <= valid_start:
        raise _invalid("Invalid time window", code)
    if maximum_lifetime is not None and valid_end - valid_start > maximum_lifetime:
        raise _invalid("Time window exceeds Core v0.1 bound", code)
    return valid_start, valid_end


def require_ordered_unique_tuple(
    value: object,
    *,
    item_validator: Callable[[object], T],
    minimum_items: int,
    maximum_items: int,
    message: str,
) -> tuple[T, ...]:
    if not isinstance(value, (list, tuple)):
        raise _invalid(message)
    if not minimum_items <= len(value) <= maximum_items:
        raise _invalid(message)
    items = tuple(item_validator(item) for item in value)
    encoded = tuple(encode_deterministic(item) for item in items)
    if any(current <= previous for previous, current in zip(encoded, encoded[1:], strict=False)):
        raise _invalid(message)
    return items


@dataclass(frozen=True, slots=True)
class FrozenMap(Mapping[object, object]):
    _items: tuple[tuple[object, object], ...]

    def __getitem__(self, key: object) -> object:
        for item_key, item_value in self._items:
            if item_key == key:
                return item_value
        raise KeyError(key)

    def __iter__(self) -> Iterator[object]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)


def freeze_core_value(value: object) -> object:
    if value is None or type(value) in (bool, bytes, str):
        return value
    if type(value) is int:
        if not -(2**64) <= value <= MAX_UINT64:
            raise _invalid("Core integer exceeds the CBOR profile")
        return value
    if isinstance(value, (list, tuple)):
        return tuple(freeze_core_value(item) for item in value)
    if isinstance(value, Mapping):
        items = [(freeze_core_value(key), freeze_core_value(item)) for key, item in value.items()]
        try:
            items.sort(key=lambda entry: encode_deterministic(entry[0]))
        except (ProtocolViolation, TypeError) as exc:
            raise _invalid("Invalid immutable Core map") from exc
        return FrozenMap(tuple(items))
    raise _invalid("Unsupported mutable Core value")


def freeze_uint_map(
    value: object,
    *,
    minimum_key: int,
    maximum_key: int = MAX_UINT64,
    maximum_pairs: int = 128,
) -> FrozenMap:
    if not isinstance(value, Mapping) or len(value) > maximum_pairs:
        raise _invalid("Invalid bounded numeric map")
    copied: dict[int, object] = {}
    for key, item in value.items():
        valid_key = require_uint(
            key,
            minimum=minimum_key,
            maximum=maximum_key,
            message="Invalid numeric map key",
        )
        copied[valid_key] = freeze_core_value(item)
    return FrozenMap(
        tuple(
            sorted(
                copied.items(),
                key=lambda entry: encode_deterministic(entry[0]),
            )
        )
    )


def thaw_core_value(value: object) -> object:
    if isinstance(value, FrozenMap):
        return {_thaw_core_key(key): thaw_core_value(item) for key, item in value._items}
    if isinstance(value, tuple):
        return [thaw_core_value(item) for item in value]
    return value


def _thaw_core_key(value: object) -> object:
    if isinstance(value, tuple):
        return tuple(_thaw_core_key(item) for item in value)
    return value
