from __future__ import annotations

import hashlib
from dataclasses import dataclass


_DOMAIN = b"NBSR-FEDERATION-OPERATOR-ID-v1\x00"
_ED25519_DISCRIMINATOR = 1
_HRP = "nbsr"
_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_CHARSET_INDEX = {character: index for index, character in enumerate(_CHARSET)}
_BECH32M_CONSTANT = 0x2BC830A3


class OperatorIdError(ValueError):
    """The Operator ID is not in the approved Federation profile."""


def _polymod(values: list[int]) -> int:
    checksum = 1
    generators = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    for value in values:
        top = checksum >> 25
        checksum = ((checksum & 0x1FFFFFF) << 5) ^ value
        for index, generator in enumerate(generators):
            if (top >> index) & 1:
                checksum ^= generator
    return checksum


def _expand_hrp(hrp: str) -> list[int]:
    return [ord(character) >> 5 for character in hrp] + [0] + [ord(character) & 31 for character in hrp]


def _convert_bits(values: bytes | list[int], from_bits: int, to_bits: int, *, pad: bool) -> list[int]:
    accumulator = 0
    bit_count = 0
    result: list[int] = []
    maximum = (1 << to_bits) - 1
    for value in values:
        if value < 0 or value >> from_bits:
            raise OperatorIdError("invalid Operator ID data")
        accumulator = (accumulator << from_bits) | value
        bit_count += from_bits
        while bit_count >= to_bits:
            bit_count -= to_bits
            result.append((accumulator >> bit_count) & maximum)
    if pad:
        if bit_count:
            result.append((accumulator << (to_bits - bit_count)) & maximum)
    elif bit_count >= from_bits or ((accumulator << (to_bits - bit_count)) & maximum):
        raise OperatorIdError("non-canonical Operator ID padding")
    return result


def _encode(binary: bytes) -> str:
    data = _convert_bits(binary, 8, 5, pad=True)
    polymod = _polymod(_expand_hrp(_HRP) + data + [0] * 6) ^ _BECH32M_CONSTANT
    checksum = [(polymod >> (5 * (5 - index))) & 31 for index in range(6)]
    return _HRP + "1" + "".join(_CHARSET[value] for value in data + checksum)


def _decode(text: str) -> bytes:
    if type(text) is not str or text != text.lower() or len(text) != 63:
        raise OperatorIdError("Operator ID text must be the exact lowercase form")
    separator = text.rfind("1")
    if separator != len(_HRP) or text[:separator] != _HRP:
        raise OperatorIdError("Operator ID HRP is invalid")
    try:
        data = [_CHARSET_INDEX[character] for character in text[separator + 1 :]]
    except KeyError as exc:
        raise OperatorIdError("Operator ID alphabet is invalid") from exc
    if len(data) < 6 or _polymod(_expand_hrp(_HRP) + data) != _BECH32M_CONSTANT:
        raise OperatorIdError("Operator ID checksum is invalid")
    binary = bytes(_convert_bits(data[:-6], 5, 8, pad=False))
    if len(binary) != 32 or _encode(binary) != text:
        raise OperatorIdError("Operator ID length or encoding is invalid")
    return binary


@dataclass(frozen=True, slots=True)
class OperatorId:
    binary: bytes

    def __post_init__(self) -> None:
        if type(self.binary) is not bytes or len(self.binary) != 32:
            raise OperatorIdError("Operator ID binary form must be 32 bytes")

    @classmethod
    def from_genesis_key(cls, raw_key: bytes, *, algorithm_discriminator: int = _ED25519_DISCRIMINATOR) -> OperatorId:
        if type(raw_key) is not bytes or len(raw_key) != 32:
            raise OperatorIdError("genesis Ed25519 public key must be 32 bytes")
        if type(algorithm_discriminator) is not int or algorithm_discriminator != _ED25519_DISCRIMINATOR:
            raise OperatorIdError("unsupported genesis key algorithm")
        return cls(hashlib.sha256(_DOMAIN + bytes((algorithm_discriminator,)) + raw_key).digest())

    @classmethod
    def from_text(cls, text: str) -> OperatorId:
        return cls(_decode(text))

    @property
    def text(self) -> str:
        return _encode(self.binary)
