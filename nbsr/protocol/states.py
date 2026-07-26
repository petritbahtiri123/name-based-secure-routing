from __future__ import annotations

from enum import StrEnum, auto
from types import MappingProxyType
from typing import TypeAlias

from nbsr.protocol.errors import InvalidTransition


class ResolutionState(StrEnum):
    RECEIVED = auto()
    NORMALIZED = auto()
    LEGACY_RESOLVED = auto()
    NBSR_RECORD_VALIDATED = auto()
    ROUTE_INTENT_CREATED = auto()
    HANDLE_BOUND = auto()
    RESPONSE_SENT = auto()
    NEGATIVE_OR_ERROR = auto()


class TunnelState(StrEnum):
    IDLE = auto()
    DISCOVERING = auto()
    HANDSHAKING = auto()
    AUTHENTICATING = auto()
    ACTIVE = auto()
    RENEWING = auto()
    DRAINING = auto()
    CLOSED = auto()
    FAILED = auto()
    REVOKED = auto()
    MIGRATING = auto()
    RESUMING = auto()


class StreamState(StrEnum):
    NEW = auto()
    OPEN_PENDING = auto()
    OPEN = auto()
    HALF_CLOSED = auto()
    CLOSED = auto()
    REJECTED = auto()
    RESET = auto()


class ConnectorState(StrEnum):
    DISCONNECTED = auto()
    CONNECTING_OUTBOUND = auto()
    AUTHENTICATED = auto()
    READY = auto()
    DRAINING = auto()


State: TypeAlias = ResolutionState | TunnelState | StreamState | ConnectorState


def _targets(*states: State) -> frozenset[State]:
    return frozenset(states)


_RESOLUTION_TRANSITIONS = MappingProxyType(
    {
        ResolutionState.RECEIVED: _targets(
            ResolutionState.NORMALIZED,
            ResolutionState.NEGATIVE_OR_ERROR,
        ),
        ResolutionState.NORMALIZED: _targets(
            ResolutionState.LEGACY_RESOLVED,
            ResolutionState.NBSR_RECORD_VALIDATED,
            ResolutionState.NEGATIVE_OR_ERROR,
        ),
        ResolutionState.LEGACY_RESOLVED: _targets(
            ResolutionState.RESPONSE_SENT,
            ResolutionState.NEGATIVE_OR_ERROR,
        ),
        ResolutionState.NBSR_RECORD_VALIDATED: _targets(
            ResolutionState.ROUTE_INTENT_CREATED,
            ResolutionState.NEGATIVE_OR_ERROR,
        ),
        ResolutionState.ROUTE_INTENT_CREATED: _targets(
            ResolutionState.HANDLE_BOUND,
            ResolutionState.NEGATIVE_OR_ERROR,
        ),
        ResolutionState.HANDLE_BOUND: _targets(
            ResolutionState.RESPONSE_SENT,
            ResolutionState.NEGATIVE_OR_ERROR,
        ),
        ResolutionState.RESPONSE_SENT: _targets(),
        ResolutionState.NEGATIVE_OR_ERROR: _targets(),
    }
)

_TUNNEL_TRANSITIONS = MappingProxyType(
    {
        TunnelState.IDLE: _targets(TunnelState.DISCOVERING),
        TunnelState.DISCOVERING: _targets(
            TunnelState.HANDSHAKING,
            TunnelState.FAILED,
        ),
        TunnelState.HANDSHAKING: _targets(
            TunnelState.AUTHENTICATING,
            TunnelState.FAILED,
        ),
        TunnelState.AUTHENTICATING: _targets(
            TunnelState.ACTIVE,
            TunnelState.FAILED,
        ),
        TunnelState.ACTIVE: _targets(
            TunnelState.RENEWING,
            TunnelState.DRAINING,
            TunnelState.REVOKED,
            TunnelState.MIGRATING,
            TunnelState.FAILED,
        ),
        TunnelState.RENEWING: _targets(
            TunnelState.ACTIVE,
            TunnelState.REVOKED,
        ),
        TunnelState.DRAINING: _targets(TunnelState.CLOSED),
        TunnelState.CLOSED: _targets(),
        TunnelState.FAILED: _targets(TunnelState.RESUMING),
        TunnelState.REVOKED: _targets(),
        TunnelState.MIGRATING: _targets(TunnelState.ACTIVE),
        TunnelState.RESUMING: _targets(TunnelState.ACTIVE),
    }
)

_STREAM_TRANSITIONS = MappingProxyType(
    {
        StreamState.NEW: _targets(
            StreamState.OPEN_PENDING,
            StreamState.REJECTED,
        ),
        StreamState.OPEN_PENDING: _targets(
            StreamState.OPEN,
            StreamState.REJECTED,
        ),
        StreamState.OPEN: _targets(
            StreamState.HALF_CLOSED,
            StreamState.RESET,
        ),
        StreamState.HALF_CLOSED: _targets(StreamState.CLOSED),
        StreamState.CLOSED: _targets(),
        StreamState.REJECTED: _targets(),
        StreamState.RESET: _targets(),
    }
)

_CONNECTOR_TRANSITIONS = MappingProxyType(
    {
        ConnectorState.DISCONNECTED: _targets(
            ConnectorState.CONNECTING_OUTBOUND,
        ),
        ConnectorState.CONNECTING_OUTBOUND: _targets(
            ConnectorState.AUTHENTICATED,
        ),
        ConnectorState.AUTHENTICATED: _targets(ConnectorState.READY),
        ConnectorState.READY: _targets(ConnectorState.DRAINING),
        ConnectorState.DRAINING: _targets(ConnectorState.DISCONNECTED),
    }
)

_TRANSITIONS = MappingProxyType(
    {
        ResolutionState: _RESOLUTION_TRANSITIONS,
        TunnelState: _TUNNEL_TRANSITIONS,
        StreamState: _STREAM_TRANSITIONS,
        ConnectorState: _CONNECTOR_TRANSITIONS,
    }
)


def transition(current: State, target: State) -> State:
    state_type = type(current)
    if state_type is not type(target) or state_type not in _TRANSITIONS:
        raise InvalidTransition
    if target not in _TRANSITIONS[state_type][current]:
        raise InvalidTransition
    return target
