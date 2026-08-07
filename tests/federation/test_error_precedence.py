from __future__ import annotations

import pytest

from nbsr.federation import DecisionOutcome, ReasonCode
from nbsr.federation.state import FederationEvent, FederationState


@pytest.mark.parametrize(
    ("failures", "primary"),
    [
        ((ReasonCode.ERR_LOCAL_POLICY, ReasonCode.ERR_RESOURCE_LIMIT), ReasonCode.ERR_RESOURCE_LIMIT),
        ((ReasonCode.ERR_FRESHNESS, ReasonCode.ERR_SIGNATURE_INVALID), ReasonCode.ERR_SIGNATURE_INVALID),
        ((ReasonCode.ERR_TERMINAL_STATE, ReasonCode.ERR_SCHEMA), ReasonCode.ERR_SCHEMA),
        ((ReasonCode.ERR_CHECKPOINT, ReasonCode.ERR_SCOPE), ReasonCode.ERR_SCOPE),
        ((ReasonCode.ERR_REVOKED, ReasonCode.ERR_ROLLBACK), ReasonCode.ERR_ROLLBACK),
    ],
)
def test_exact_frozen_error_precedence(failures: tuple[ReasonCode, ...], primary: ReasonCode) -> None:
    event = FederationEvent(
        "policy:a",
        1,
        1,
        b"x" * 32,
        "policy",
        b"o" * 32,
        b"p" * 32,
        b"s" * 32,
        validation_failures=failures,
    )
    state = FederationState.empty()
    unchanged, result = state.apply(event, 1)
    assert unchanged is state
    assert (result.outcome, result.reason) == (DecisionOutcome.REJECT, primary)
