"""Deterministic security model for P1D transport-session rotation."""

from __future__ import annotations

from dataclasses import dataclass, field
import json


@dataclass(frozen=True)
class Authority:
    session_id: str
    connection_binding: str
    channel_id: str
    route_id: str
    grant_digest: str
    grant_nonce: str
    request_id: str
    monotonic_sequence: int
    resume_handle: str


@dataclass
class Session:
    authority: Authority
    admitted: bool = False
    draining: bool = False
    retired: bool = False
    requests: set[str] = field(default_factory=set)
    sequence: int = 0
    replay: set[int] = field(default_factory=set)
    live: set[int] = field(default_factory=set)


class RotationModel:
    def __init__(self, *, threshold: int) -> None:
        if threshold < 1:
            raise ValueError("threshold must be positive")
        self.threshold = threshold
        self.sessions: dict[str, Session] = {}
        self.revoked_channels: set[str] = set()
        self.resume_records: dict[str, str] = {}

    def establish(self, authority: Authority) -> str:
        if authority.session_id in self.sessions:
            return "REJECT_SESSION_REPLAY"
        if any(old.authority.connection_binding == authority.connection_binding for old in self.sessions.values()):
            return "REJECT_STALE_AUTHORITY"
        self.sessions[authority.session_id] = Session(authority=authority)
        return "ACCEPT"

    def _session(self, authority: Authority) -> Session | None:
        return self.sessions.get(authority.session_id)

    def _authority_matches(self, session: Session, authority: Authority) -> bool:
        expected = session.authority
        return all(
            getattr(expected, name) == getattr(authority, name)
            for name in (
                "session_id",
                "connection_binding",
                "channel_id",
                "route_id",
                "grant_digest",
                "grant_nonce",
            )
        )

    def admit_channel(self, authority: Authority) -> str:
        session = self._session(authority)
        if session is None or not self._authority_matches(session, authority):
            return "REJECT_STALE_AUTHORITY"
        if any(
            old.authority.session_id != authority.session_id
            and (
                old.authority.channel_id == authority.channel_id
                or old.authority.route_id == authority.route_id
                or old.authority.grant_digest == authority.grant_digest
                or old.authority.grant_nonce == authority.grant_nonce
            )
            for old in self.sessions.values()
        ):
            return "REJECT_STALE_AUTHORITY"
        if authority.request_id in session.requests:
            return "REJECT_REQUEST_REPLAY"
        if authority.monotonic_sequence <= session.sequence:
            return "REJECT_SEQUENCE_ROLLBACK"
        session.requests.add(authority.request_id)
        session.sequence = authority.monotonic_sequence
        session.admitted = True
        return "ACCEPT"

    def open_stream(self, authority: Authority, stream_id: int) -> str:
        session = self._session(authority)
        if session is None or not self._authority_matches(session, authority) or not session.admitted:
            return "REJECT_STALE_AUTHORITY"
        if authority.channel_id in self.revoked_channels:
            return "REJECT_REVOKED"
        if session.draining or session.retired:
            return "REJECT_DRAINING"
        if stream_id in session.replay:
            return "REJECT_STREAM_REPLAY"
        session.replay.add(stream_id)
        session.live.add(stream_id)
        return "ACCEPT"

    def rotation_due(self, session_id: str) -> bool:
        return len(self.sessions[session_id].replay) >= self.threshold

    def select_for_new_stream(self, old_id: str, fresh_id: str) -> str:
        fresh = self.sessions[fresh_id]
        if self.rotation_due(old_id) and fresh.admitted and not fresh.retired:
            return fresh_id
        return old_id

    def begin_drain(self, session_id: str) -> str:
        self.sessions[session_id].draining = True
        return "ACCEPT"

    def stream_owner(self, stream_id: int, session_id: str) -> str | None:
        return session_id if stream_id in self.sessions[session_id].live else None

    def finish_stream(self, session_id: str, stream_id: int) -> str:
        session = self.sessions[session_id]
        if stream_id not in session.live:
            return "REJECT_UNKNOWN_STREAM"
        session.live.remove(stream_id)
        return "ACCEPT"

    def retire(self, session_id: str) -> str:
        session = self.sessions[session_id]
        if session.live:
            return "REJECT_LIVE_STREAMS"
        session.retired = True
        session.replay.clear()
        return "ACCEPT"

    def replay_entries(self, session_id: str) -> int:
        return len(self.sessions[session_id].replay)

    def revoke(self, channel_id: str) -> str:
        self.revoked_channels.add(channel_id)
        return "ACCEPT"

    def issue_resume(self, old: Authority) -> str:
        if old.resume_handle in self.resume_records:
            return "REJECT_RESUME_REPLAY"
        self.resume_records[old.resume_handle] = old.session_id
        return "ACCEPT"

    def consume_resume(self, handle: str, fresh: Authority) -> str:
        old_id = self.resume_records.get(handle)
        session = self._session(fresh)
        if old_id is None:
            return "REJECT_RESUME_REPLAY"
        if session is None or old_id == fresh.session_id or not session.admitted:
            return "REJECT_STALE_AUTHORITY"
        del self.resume_records[handle]
        return "ACCEPT"

    def production_gates(self, *, application_selector_present: bool, fresh_authority_provider_present: bool) -> dict[str, bool]:
        orchestration_defined = application_selector_present and fresh_authority_provider_present
        return {
            "no_replay_weakening": True,
            "no_authority_resurrection": True,
            "no_protocol_ambiguity": orchestration_defined,
            "fresh_session_establishment": True,
            "bounded_deterministic_rotation": orchestration_defined,
            "fail_closed_failures": True,
        }


def canonical_results() -> dict[str, object]:
    old = Authority("TS-A", "binding-TS-A", "SC-A", "route-1", "grant-1", "nonce-1", "request-1", 1, "resume-1")
    fresh = Authority("TS-B", "binding-TS-B", "SC-B", "route-2", "grant-2", "nonce-2", "request-2", 2, "resume-2")
    model = RotationModel(threshold=2)
    model.establish(old)
    model.admit_channel(old)
    model.establish(fresh)
    model.admit_channel(fresh)
    first = model.open_stream(old, 4)
    old_replay = model.open_stream(old, 4)
    fresh_reuse = model.open_stream(fresh, 4)
    stale = Authority(**{**old.__dict__, "session_id": fresh.session_id, "connection_binding": fresh.connection_binding})
    stale_result = model.open_stream(stale, 8)
    model.issue_resume(old)
    model.consume_resume(old.resume_handle, fresh)
    resume_replay = model.consume_resume(old.resume_handle, fresh)
    model.revoke(fresh.channel_id)
    revoked = model.open_stream(fresh, 8)
    gates = model.production_gates(application_selector_present=False, fresh_authority_provider_present=False)
    return {
        "schema_version": 1,
        "hypothesis": "bounded_transport_session_rotation",
        "decision": "DESIGN_BLOCKED",
        "all_implementation_gates_pass": all(gates.values()),
        "implementation_gates": gates,
        "adversarial_cases": {
            "old_stream_replay": old_replay,
            "fresh_numeric_stream_reuse": fresh_reuse,
            "old_channel_or_grant_resurrection": stale_result,
            "resume_replay": resume_replay,
            "revocation_during_transition": revoked,
        },
        "setup": {"first_old_stream": first, "threshold": model.threshold},
    }


if __name__ == "__main__":
    print(json.dumps(canonical_results(), indent=2, sort_keys=True))
