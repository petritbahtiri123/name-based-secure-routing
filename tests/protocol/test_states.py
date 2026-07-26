from __future__ import annotations

from enum import StrEnum
from itertools import product

import pytest

from nbsr.protocol.errors import InvalidTransition
from nbsr.protocol.states import (
    ConnectorState,
    ResolutionState,
    StreamState,
    TunnelState,
    transition,
)


EXPECTED_TRANSITIONS: dict[type[StrEnum], set[tuple[StrEnum, StrEnum]]] = {
    ResolutionState: {
        (ResolutionState.RECEIVED, ResolutionState.NORMALIZED),
        (ResolutionState.NORMALIZED, ResolutionState.LEGACY_RESOLVED),
        (ResolutionState.LEGACY_RESOLVED, ResolutionState.RESPONSE_SENT),
        (ResolutionState.NORMALIZED, ResolutionState.NBSR_RECORD_VALIDATED),
        (
            ResolutionState.NBSR_RECORD_VALIDATED,
            ResolutionState.ROUTE_INTENT_CREATED,
        ),
        (ResolutionState.ROUTE_INTENT_CREATED, ResolutionState.HANDLE_BOUND),
        (ResolutionState.HANDLE_BOUND, ResolutionState.RESPONSE_SENT),
        (ResolutionState.RECEIVED, ResolutionState.NEGATIVE_OR_ERROR),
        (ResolutionState.NORMALIZED, ResolutionState.NEGATIVE_OR_ERROR),
        (ResolutionState.LEGACY_RESOLVED, ResolutionState.NEGATIVE_OR_ERROR),
        (
            ResolutionState.NBSR_RECORD_VALIDATED,
            ResolutionState.NEGATIVE_OR_ERROR,
        ),
        (
            ResolutionState.ROUTE_INTENT_CREATED,
            ResolutionState.NEGATIVE_OR_ERROR,
        ),
        (ResolutionState.HANDLE_BOUND, ResolutionState.NEGATIVE_OR_ERROR),
    },
    TunnelState: {
        (TunnelState.IDLE, TunnelState.DISCOVERING),
        (TunnelState.DISCOVERING, TunnelState.HANDSHAKING),
        (TunnelState.HANDSHAKING, TunnelState.AUTHENTICATING),
        (TunnelState.AUTHENTICATING, TunnelState.ACTIVE),
        (TunnelState.ACTIVE, TunnelState.RENEWING),
        (TunnelState.RENEWING, TunnelState.ACTIVE),
        (TunnelState.ACTIVE, TunnelState.DRAINING),
        (TunnelState.DRAINING, TunnelState.CLOSED),
        (TunnelState.DISCOVERING, TunnelState.FAILED),
        (TunnelState.HANDSHAKING, TunnelState.FAILED),
        (TunnelState.AUTHENTICATING, TunnelState.FAILED),
        (TunnelState.ACTIVE, TunnelState.REVOKED),
        (TunnelState.RENEWING, TunnelState.REVOKED),
        (TunnelState.ACTIVE, TunnelState.MIGRATING),
        (TunnelState.MIGRATING, TunnelState.ACTIVE),
        (TunnelState.ACTIVE, TunnelState.FAILED),
        (TunnelState.FAILED, TunnelState.RESUMING),
        (TunnelState.RESUMING, TunnelState.ACTIVE),
    },
    StreamState: {
        (StreamState.NEW, StreamState.OPEN_PENDING),
        (StreamState.OPEN_PENDING, StreamState.OPEN),
        (StreamState.OPEN, StreamState.HALF_CLOSED),
        (StreamState.HALF_CLOSED, StreamState.CLOSED),
        (StreamState.NEW, StreamState.REJECTED),
        (StreamState.OPEN_PENDING, StreamState.REJECTED),
        (StreamState.OPEN, StreamState.RESET),
    },
    ConnectorState: {
        (ConnectorState.DISCONNECTED, ConnectorState.CONNECTING_OUTBOUND),
        (ConnectorState.CONNECTING_OUTBOUND, ConnectorState.AUTHENTICATED),
        (ConnectorState.AUTHENTICATED, ConnectorState.READY),
        (ConnectorState.READY, ConnectorState.DRAINING),
        (ConnectorState.DRAINING, ConnectorState.DISCONNECTED),
    },
}


@pytest.mark.parametrize(
    ("state_type", "expected_names"),
    (
        (
            ResolutionState,
            {
                "RECEIVED",
                "NORMALIZED",
                "LEGACY_RESOLVED",
                "NBSR_RECORD_VALIDATED",
                "ROUTE_INTENT_CREATED",
                "HANDLE_BOUND",
                "RESPONSE_SENT",
                "NEGATIVE_OR_ERROR",
            },
        ),
        (
            TunnelState,
            {
                "IDLE",
                "DISCOVERING",
                "HANDSHAKING",
                "AUTHENTICATING",
                "ACTIVE",
                "RENEWING",
                "DRAINING",
                "CLOSED",
                "FAILED",
                "REVOKED",
                "MIGRATING",
                "RESUMING",
            },
        ),
        (
            StreamState,
            {
                "NEW",
                "OPEN_PENDING",
                "OPEN",
                "HALF_CLOSED",
                "CLOSED",
                "REJECTED",
                "RESET",
            },
        ),
        (
            ConnectorState,
            {
                "DISCONNECTED",
                "CONNECTING_OUTBOUND",
                "AUTHENTICATED",
                "READY",
                "DRAINING",
            },
        ),
    ),
)
def test_state_names_are_frozen(
    state_type: type[StrEnum],
    expected_names: set[str],
) -> None:
    assert {state.name for state in state_type} == expected_names
    assert {state.value for state in state_type} == {name.lower() for name in expected_names}


@pytest.mark.parametrize("state_type", tuple(EXPECTED_TRANSITIONS))
def test_transition_matrix_is_exact(state_type: type[StrEnum]) -> None:
    expected = EXPECTED_TRANSITIONS[state_type]
    for current, target in product(state_type, repeat=2):
        if (current, target) in expected:
            assert transition(current, target) is target
        else:
            with pytest.raises(InvalidTransition):
                transition(current, target)


@pytest.mark.parametrize(
    "state_type",
    (ResolutionState, TunnelState, StreamState, ConnectorState),
)
def test_unknown_states_are_rejected(state_type: type[StrEnum]) -> None:
    with pytest.raises(ValueError):
        state_type("unknown")


def test_cross_machine_and_untyped_transitions_are_rejected() -> None:
    with pytest.raises(InvalidTransition):
        transition(TunnelState.ACTIVE, StreamState.OPEN)
    with pytest.raises(InvalidTransition):
        transition("active", "renewing")
