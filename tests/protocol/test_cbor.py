from __future__ import annotations

from dataclasses import replace

import cbor2
import pytest

from nbsr.protocol.cbor import (
    DEFAULT_LIMITS,
    CborLimits,
    decode_deterministic,
    encode_deterministic,
)
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.registry import ErrorCode


def test_default_resource_limits_are_frozen() -> None:
    assert DEFAULT_LIMITS == CborLimits(
        max_total_bytes=65_536,
        max_depth=16,
        max_array_items=256,
        max_map_pairs=128,
        max_text_bytes=4_096,
        max_byte_string_bytes=32_768,
    )


def test_map_encoding_is_stable() -> None:
    first = encode_deterministic({2: b"b", 1: b"a"})
    second = encode_deterministic({1: b"a", 2: b"b"})

    assert first == second == bytes.fromhex("a2014161024162")
    assert decode_deterministic(first) == {1: b"a", 2: b"b"}


def test_map_keys_use_rfc8949_bytewise_not_legacy_length_first_order() -> None:
    wire = encode_deterministic({-1: "short", 1000: "long"})
    legacy_length_first = bytes.fromhex("a2206573686f72741903e8646c6f6e67")

    assert wire == bytes.fromhex("a21903e8646c6f6e67206573686f7274")
    assert wire != legacy_length_first
    assert decode_deterministic(wire) == {1000: "long", -1: "short"}
    with pytest.raises(ProtocolViolation):
        decode_deterministic(legacy_length_first)


@pytest.mark.parametrize(
    "value",
    (
        None,
        False,
        True,
        -(2**64),
        -1,
        0,
        23,
        24,
        255,
        256,
        2**64 - 1,
        b"",
        b"nbsr",
        "",
        "nbsr",
        [],
        [1, "two", b"three"],
        {},
        {1: "one", 2: [False, None]},
    ),
)
def test_supported_core_values_round_trip(value: object) -> None:
    wire = encode_deterministic(value)

    assert decode_deterministic(wire) == value
    assert encode_deterministic(decode_deterministic(wire)) == wire


@pytest.mark.parametrize(
    "wire",
    (
        bytes.fromhex("1817"),
        bytes.fromhex("1900ff"),
        bytes.fromhex("3800"),
        b"\x58\x17" + b"x" * 23,
        b"\x78\x17" + b"x" * 23,
        bytes.fromhex("9817"),
        bytes.fromhex("b817"),
        bytes.fromhex("5f4161ff"),
        bytes.fromhex("7f6161ff"),
        bytes.fromhex("9f0102ff"),
        bytes.fromhex("bf0102ff"),
        bytes.fromhex("a201020103"),
        bytes.fromhex("a202000100"),
        bytes.fromhex("f90000"),
        bytes.fromhex("fa00000000"),
        bytes.fromhex("fb0000000000000000"),
        bytes.fromhex("c000"),
        bytes.fromhex("d81800"),
        bytes.fromhex("f7"),
        bytes.fromhex("f800"),
        bytes.fromhex("ff"),
        bytes.fromhex("61ff"),
        bytes.fromhex("0000"),
    ),
)
def test_non_core_deterministic_forms_are_rejected(wire: bytes) -> None:
    with pytest.raises(ProtocolViolation):
        decode_deterministic(wire)


def test_structural_rejection_happens_before_cbor2_loads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_loads(_: bytes) -> object:
        raise AssertionError("cbor2.loads must not receive structurally invalid input")

    monkeypatch.setattr(cbor2, "loads", unexpected_loads)

    with pytest.raises(ProtocolViolation):
        decode_deterministic(bytes.fromhex("a201020103"))


@pytest.mark.parametrize(
    ("limits", "wire"),
    (
        (replace(DEFAULT_LIMITS, max_total_bytes=1), bytes.fromhex("1818")),
        (replace(DEFAULT_LIMITS, max_depth=2), bytes.fromhex("818180")),
        (replace(DEFAULT_LIMITS, max_array_items=1), bytes.fromhex("820102")),
        (replace(DEFAULT_LIMITS, max_map_pairs=1), bytes.fromhex("a201000200")),
        (replace(DEFAULT_LIMITS, max_text_bytes=2), bytes.fromhex("63616263")),
        (
            replace(DEFAULT_LIMITS, max_byte_string_bytes=2),
            bytes.fromhex("43010203"),
        ),
        (
            replace(DEFAULT_LIMITS, max_byte_string_bytes=16),
            bytes.fromhex("5a00010000"),
        ),
    ),
)
def test_decode_resource_limits_fail_before_allocation(
    limits: CborLimits,
    wire: bytes,
) -> None:
    with pytest.raises(ProtocolViolation) as exc_info:
        decode_deterministic(wire, limits)

    assert exc_info.value.code is ErrorCode.NBSR_E_OVER_CAPACITY


def test_depth_limit_accepts_its_exact_boundary() -> None:
    limits = replace(DEFAULT_LIMITS, max_depth=2)

    assert decode_deterministic(bytes.fromhex("8180"), limits) == [[]]


@pytest.mark.parametrize(
    ("limits", "value"),
    (
        (replace(DEFAULT_LIMITS, max_array_items=1), [1, 2]),
        (replace(DEFAULT_LIMITS, max_map_pairs=1), {1: 1, 2: 2}),
        (replace(DEFAULT_LIMITS, max_text_bytes=2), "abc"),
        (replace(DEFAULT_LIMITS, max_byte_string_bytes=2), b"abc"),
    ),
)
def test_encode_resource_limits_fail_closed(
    limits: CborLimits,
    value: object,
) -> None:
    with pytest.raises(ProtocolViolation) as exc_info:
        encode_deterministic(value, limits)

    assert exc_info.value.code is ErrorCode.NBSR_E_OVER_CAPACITY


@pytest.mark.parametrize("value", (1.5, {1, 2}, object(), 2**64, -(2**64) - 1))
def test_encoder_rejects_unsupported_values(value: object) -> None:
    with pytest.raises(ProtocolViolation) as exc_info:
        encode_deterministic(value)

    assert exc_info.value.code is ErrorCode.NBSR_E_PROFILE_UNSUPPORTED
