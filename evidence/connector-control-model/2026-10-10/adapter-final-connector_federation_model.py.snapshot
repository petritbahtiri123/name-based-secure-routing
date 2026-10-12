"""Offline federation-to-connector experiment. NOT production authorization.

Binding is an explicit fixture association, not a connector identity mapping.
Existing COSE authentication and bilateral authorization are reused. Supplied
trust evidence is not discovered here. Incident delivery remains explicitly
simulated; no raw FederationResult is accepted as proof or as an event.
"""

from dataclasses import replace

from nbsr.connector_control_model import Binding, CompletionGrace, Model, Permission
from nbsr.federation.authorization import AuthorizationEvidence, BilateralAuthorizer
from nbsr.federation.cose import AuthenticatedBilateralContext
from nbsr.federation.fields import FederationValidationError
from nbsr.federation.profile import FederationProfile
from nbsr.federation.registry import DecisionOutcome, EnforcementMode, KeyLifecycle, KeyPurpose, ReasonCode
from nbsr.federation.revocation import DependencyIndex
from nbsr.federation.state import FederationEvent, FederationState


class Adapter:
    """One owner/context only; no reconnect, rotation, durable trust or live I/O."""

    def __init__(self, binding: Binding, clock, *, lease: int, grace: CompletionGrace):
        if type(grace) is not CompletionGrace or grace.seconds != FederationProfile.drain_ceiling_seconds or not grace.profile:
            raise ValueError("explicit development-profile drain fixture required")
        self.binding, self.clock, self.grace = binding, clock, grace
        self.model = Model(binding, self._permission, clock, lease=lease, attempts=1, retry_delay=0)
        self._owner = None
        self._session = None
        self._permission_snapshot = None
        self._context = None
        self._event = None
        self._state = FederationState.empty()
        self._outage = False
        self._latched = False
        self.result = None

    def _verify(self, signed, source, destination, now):
        if (
            type(signed) is not AuthenticatedBilateralContext
            or type(source) is not AuthorizationEvidence
            or type(destination) is not AuthorizationEvidence
        ):
            raise FederationValidationError("full authenticated bilateral evidence required")
        if type(now) is not int or source.now != now or destination.now != now:
            raise FederationValidationError("current evidence time required")
        for authority in (signed.source_authority, signed.destination_authority):
            if (
                authority.purpose is not KeyPurpose.FEDERATION_AUTHORIZATION
                or authority.lifecycle is not KeyLifecycle.ACTIVE
                or authority.revoked
                or not authority.not_before <= now < authority.expires_at
            ):
                raise FederationValidationError("current signer authority required")
        # Use a fresh decision cache per verification so changed evidence at
        # the same clock instant is still independently evaluated.
        authorizer = BilateralAuthorizer()
        for result in (authorizer.authorize_source(signed, source), authorizer.authorize_destination(signed, destination)):
            if result.outcome is not DecisionOutcome.ACCEPT:
                raise FederationValidationError("bilateral authorization rejected")
        context = signed.context
        expires = min(
            context._payload[41],
            source.authority_proof._payload[42],
            destination.authority_proof._payload[42],
            signed.source_authority.expires_at,
            signed.destination_authority.expires_at,
        )
        if now >= expires:
            raise FederationValidationError("authority expired independently of cache freshness")
        return Permission(self.binding, expires, expires, self.grace)

    def _fresh_state(self, context, now):
        # Rebuild only this ephemeral outage view from freshly verified exact
        # evidence. This is not the federation's durable continuity/replay store.
        event = FederationEvent(
            context.digest.hex(),
            context._payload[42],
            context._payload[43],
            context.digest,
            "context",
            context._payload[33],
            context._payload[34],
            context._payload[35],
            dependencies=tuple(sorted(context.dependencies)),
            valid_until=context._payload[41],
            source_fresh_at=now,
        )
        # State.apply's genesis rule requires sequence 1; an accepted snapshot
        # carries the verified context's actual sequence without inventing lineage.
        from nbsr.federation.state import AcceptedFederationObject

        accepted = AcceptedFederationObject(
            event.key,
            event.generation,
            event.sequence,
            event.object_digest,
            event.object_kind,
            event.operator_id,
            event.peer_operator_id,
            event.service_id,
            event.dependencies,
            event.valid_until,
            now,
            False,
        )
        self._event = event
        self._state = FederationState(accepted=(accepted,))

    def open(self, transport, signed, source, destination):
        if self._owner is not None:
            if transport is not self._owner.transport:
                transport.close()
            return None
        try:
            now = self.clock()
            permission = self._verify(signed, source, destination, now)
        except (FederationValidationError, TypeError, AttributeError, ValueError):
            transport.close()
            return None
        self._session = transport.session
        self._permission_snapshot = permission
        self._context = signed.context
        self._fresh_state(signed.context, now)
        attempt = self.model.begin(transport, self.binding)
        if attempt is None:
            return None
        self._owner = attempt
        if not self.model.authenticate(attempt):
            return None
        ticket = self.model.register(attempt)
        return attempt if ticket is not None and self.model.confirm(attempt, ticket) else None

    def _matches(self, owner):
        return owner is not None and owner is self._owner and owner is self.model._current and owner.transport.session is self._session

    def _permission(self, binding, session, now):
        if binding != self.binding or session is not self._session or self._permission_snapshot is None:
            return None
        permission = self._permission_snapshot
        if not self._outage:
            return permission
        _, self.result = self._state.apply(replace(self._event, operation="existing_context"), now)
        deadline = self._event.source_fresh_at + FederationProfile.degraded_staleness_seconds
        # Do not treat ordinary unavailable refresh as invalid authority. This
        # fixture allows existing work only, even in the fresh-cache interval.
        return replace(permission, new_use=False, admission_expires=min(permission.admission_expires, deadline))

    def outage(self, owner):
        if not self._matches(owner):
            return False
        self._outage = True
        self.model.poll()
        return True

    def recover(self, owner, signed, source, destination):
        self.model.poll()
        if not self._matches(owner) or self._latched or self.model._halted or owner.phase != "ready":
            return False
        try:
            now = self.clock()
            permission = self._verify(signed, source, destination, now)
            if signed.context.digest != self._context.digest:
                return False
        except (FederationValidationError, TypeError, AttributeError, ValueError):
            return False
        # Recheck the old eligibility after verification; a clock boundary
        # crossed during it must not erase an already due drain.
        self.model.poll()
        if not self._matches(owner) or self.model._halted or owner.phase != "ready":
            return False
        self._permission_snapshot = permission
        self._fresh_state(signed.context, now)
        self._outage = False
        return self.model.select() is owner

    def simulate_dependency_event(self, owner, context_digest, dependencies, mode):
        """Explicit fake incident; NOT authenticated revocation transport.

        Models dependency dispatch only after a full bilateral fixture was
        accepted. Caller-supplied cause is not cryptographic revocation evidence.
        """
        if type(mode) is not EnforcementMode or mode not in (EnforcementMode.DENY_NEW_USE, EnforcementMode.TERMINATE_ACTIVE_USE):
            raise ValueError("exact supported enforcement required")
        if not self._matches(owner) or context_digest != self._context.digest:
            return False
        index = DependencyIndex()
        index.add(self._context.digest, set(self._context.dependencies))
        if self._context.digest not in index.invalidate(set(dependencies)):
            return False
        event = replace(
            self._event,
            operation="existing_context",
            compromised=mode is EnforcementMode.TERMINATE_ACTIVE_USE,
            validation_failures=(ReasonCode.ERR_REVOKED,) if mode is EnforcementMode.DENY_NEW_USE else (),
        )
        _, self.result = self._state.apply(event, self.clock())
        self._latched = True
        self.model.enforce(owner, self.result.enforcement)
        return True
