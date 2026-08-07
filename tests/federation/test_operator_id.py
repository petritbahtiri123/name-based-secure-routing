from __future__ import annotations

import pytest

from nbsr.federation.identity import OperatorId, OperatorIdError


GENESIS_KEY = bytes(range(32))
EXPECTED_BINARY = bytes.fromhex("56c83296d5d62b74a9f161125c5fc9b441fb8f85b174606f3379ca57503e1e86")
EXPECTED_TEXT = "nbsr12myr99k46c4hf203vyf9ch7fk3qlhru9k96xqmen0899w5p7r6rqgutt5k"


def test_operator_id_matches_approved_genesis_vector() -> None:
    operator_id = OperatorId.from_genesis_key(GENESIS_KEY)
    assert operator_id.binary == EXPECTED_BINARY
    assert operator_id.text == EXPECTED_TEXT
    assert len(operator_id.text) == 63


def test_operator_id_round_trips_from_lowercase_bech32m() -> None:
    assert OperatorId.from_text(EXPECTED_TEXT) == OperatorId.from_genesis_key(GENESIS_KEY)


@pytest.mark.parametrize(
    "text",
    [
        EXPECTED_TEXT.upper(),
        "N" + EXPECTED_TEXT[1:],
        "oops" + EXPECTED_TEXT[4:],
        EXPECTED_TEXT[:-1] + ("q" if EXPECTED_TEXT[-1] != "q" else "p"),
        EXPECTED_TEXT.replace("12myr", "1myr", 1),
    ],
)
def test_operator_id_rejects_noncanonical_or_invalid_text(text: str) -> None:
    with pytest.raises(OperatorIdError):
        OperatorId.from_text(text)


def test_operator_id_rejects_wrong_genesis_key_length() -> None:
    with pytest.raises(OperatorIdError):
        OperatorId.from_genesis_key(GENESIS_KEY[:-1])


def test_operator_id_rejects_wrong_algorithm_discriminator() -> None:
    with pytest.raises(OperatorIdError):
        OperatorId.from_genesis_key(GENESIS_KEY, algorithm_discriminator=2)


def test_operator_id_is_stable_across_operational_key_rotation() -> None:
    operator_id = OperatorId.from_genesis_key(GENESIS_KEY)
    old_operational_key = bytes(range(32, 64))
    new_operational_key = bytes(range(64, 96))
    assert old_operational_key != new_operational_key
    assert operator_id == OperatorId.from_genesis_key(GENESIS_KEY)
