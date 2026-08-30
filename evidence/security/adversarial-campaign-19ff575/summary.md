# NBSR Security Adversarial Campaign

Overall: **PARTIAL**

| Scenario | Expected | Observed reason/code | Service reachable | Cleanup | Status |
| --- | --- | --- | --- | --- | --- |
| replayed_grant_ticket | Reject as replay and retain zero active channel state. | AdmissionReject::Replay | NO | CLEAN | PASS |
| tampered_grant_ticket | Reject signature validation before route admission. | CoreV02Reject::GrantInvalid | NO | CLEAN | PASS |
| wrong_service_name | Reject the binding and retain no cached or pending authority. | authority.ErrBindingMismatch | NO | CLEAN | PASS |
| wrong_port_transport | Reject each vector with the declared fail-closed protocol error. | NBSR_E_GRANT_INVALID/NBSR_E_ROUTE_DENIED | NO | CLEAN | PASS |
| wrong_pop_key | Reject before dialing any transport. | session.ErrProofBinding | NO | CLEAN | PASS |
| expired_grant | Reject as expired and retain no cached or pending authority. | authority.ErrExpired | NO | CLEAN | PASS |
| revoked_credential_grant | Reject as revoked without authorizing new work. | authority.ErrRevoked | NO | CLEAN | PASS |
| stale_generation_sequence | Reject before transport/application creation and retain no authority state. | authority.ErrStaleGeneration | NO | CLEAN | PASS |
| downgrade_attempt | Reject the legacy path without consuming credit/replay/live capacity; allow only a valid credited retry. | ApplicationStreamRejected::ProfileUnsupported | NO | CLEAN | PASS |
| unauthorized_source | Reject the handshake before allocating an authenticated connection. | TLS_UNTRUSTED_CLIENT_CERTIFICATE | NO | CLEAN | PASS |
| direct_origin_scan | The private origin must be unreachable from the client network. | NOT_CURRENT_SHA_NETWORK_ISOLATION | UNKNOWN | NOT_APPLICABLE | INCONCLUSIVE |
| malformed_control_wire | Reject before admission without consuming credit, replay history, live capacity, or audit state. | ApplicationStreamRejected::MalformedPreface | NO | CLEAN | PASS |
| forged_identity_source_binding | Reject the handshake before exposing an authenticated connection. | TLS_SOURCE_IDENTITY_MISMATCH | NO | CLEAN | PASS |
| edge_session_failure_recovery | Never restore a draining generation, never replay payload, bound retries, and clean pending ownership. | session.ErrTransport/session.ErrRecoveryExhausted | NO | CLEAN | PASS |

All PASS rows are current-SHA executable regressions whose underlying assertions verify the stated rejection and cleanup/state boundary.

The direct-origin scan is INCONCLUSIVE because this campaign did not create a current-SHA network-isolated private-origin topology. Adjacent no-route/no-fallback regressions passed, but they are not equivalent to a network reachability scan.

Reproduce: `python scripts/security/adversarial_campaign.py --output <new-empty-output-directory>`. Exact per-scenario commands and working-directory labels are stored in `environment.json`; raw stdout/stderr are stored under `raw/`.

Git SHA: `19ff57504a760f35ab1579d93cc9cd7cb874deb8`
Branch: `codex/nbsr-v3-wp0-wp1`
Platform: Windows-11-10.0.26200
