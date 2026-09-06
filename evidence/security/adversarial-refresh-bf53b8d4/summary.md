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

Reproduce: `python scripts/security/adversarial_campaign.py --output <new-empty-output-directory>`. Exact per-scenario commands and working-directory labels are stored in `environment.json`; raw stdout/stderr remain under the external raw root `C:/NBSR-build/security-refresh-bf53b8d4/raw/` (see `external-inputs.json`).

Git SHA: `bf53b8d4fbbd512ae925496f13f5f9dabef35214`
Branch: `codex/nbsr-v3-wp0-wp1`
Platform: Windows-11-10.0.26200

## Current refresh and integrity

This fresh refresh at `bf53b8d4fbbd512ae925496f13f5f9dabef35214` records **13 PASS, 0 FAIL, 1 INCONCLUSIVE**. All 45 raw artifact hashes were independently verified; all 14 per-scenario raw records match the analysis and command manifest. Both recorded runner/test source hashes match current bytes and the named commit after newline normalization. This establishes the recorded source binding, not an independent historical clean-worktree attestation.

The separately accepted [f831c9bb Docker isolation proof](../isp-isolation-f831c9bb/REPORT.md) is retained on its own SHA and topology. It does not turn this runner's direct-origin result into PASS or establish a same-SHA network scan. The prior b7df259b campaign is preserved. No tests were rerun during packaging.

Canonical JSON uses UTF-8 LF normalization. `external-checksums.sha256` preserves the original raw index byte-for-byte; `checksums.sha256` separately covers canonical files. Raw logs remain outside the checkout.
