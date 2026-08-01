# WP6 replicated origin and continuity state decision

**Status:** Approved for a deterministic storage-neutral prototype and
simulated multi-replica conformance evidence only.

WP6 uses a closed, canonical, bounded snapshot around existing domain
authority. It does not define a database, consensus protocol, message type,
field key, wrapper, handover proof, resume proof, or OriginSet wire format.

Authoritative keys are tenant- and service-scoped and distinguish origin,
policy, revocation, replay, tombstone, grant, and channel facts. Origin state
reuses `DerivedOriginSet` generation/sequence/digest and
`OriginSetTombstone`; policy state reuses trusted version/fingerprint inputs;
grant, revocation, replay, and channel entries retain safe digests and bounded
authority metadata only. WP4 remains the authority for channel lifecycle,
fresh grants, exporter binding, 30-second drain, and same-edge resume.

Per-key generation and sequence are monotonic. Equal-version equal-digest
updates are idempotent; equal-version different-digest updates are
equivocation; lower versions and policy rollback are rejected. Higher versions
chain to the retained digest. Terminal revocation, replay, tombstone, grant,
and channel facts cannot become positive authority. Capacity exhaustion fails
closed rather than evicting security state.

Snapshots use `nbsr-continuity-snapshot-v1`, canonical ASCII JSON, SHA-256,
sorted records/replicas, at most 32 replicas, 4096 records, and 256 KiB. The
configured replica set and strict-majority quorum are trusted local inputs.
Reads require one unambiguous quorum over an exact complete snapshot and fail
closed for missing, stale, conflicting, partial, corrupt, unavailable, or
forged-identity evidence.

Failover requires a fresh quorum and is bounded to 5 seconds of monotonic
elapsed time. Drain is bounded to 30 seconds and cannot extend other authority.
Continuity is only a local safe decision over already approved state; it never
mints cross-edge handover/resumption authority.

Persistence uses atomic private writes and bounded descriptor-bound regular
file reads. Cooperating writers use an exclusive private-directory lock, and
one repository instance serializes loads/saves with a process-lifetime
monotonic watermark. Higher snapshots must preserve and monotonically advance
every retained record. A stale lock after abrupt process death fails closed
and requires operator cleanup. This is not external compare-and-swap,
cross-process monotonic storage, or crash/reboot durability.

Corruption and detected rollback expose no state. Reports are deterministic
and privacy-safe. There is no live etcd, no live Raft, no live PostgreSQL, no
live multi-host consensus, no production HA, no crash/reboot durability, no
cross-edge handover, no cross-edge resumption, no OriginSet publication
interoperability, no new wire protocol, no complete partition tolerance, no
global federation, and no production-readiness claim.

## Completion evidence

WP6 is complete and evidence-closed at bounded deterministic prototype scope.
Fresh validation on 2026-08-01 recorded 65 focused WP6 tests and 971 passed and
1 skipped in the full Python suite. Ruff check passed; Ruff format reported
132 files already formatted; `pip check`, Core v0.1/Core v0.2 regeneration,
WP4 exporter Python and independent Node verification, the independent WP6
snapshot verifier, Rustfmt, Clippy with `-D warnings`, Docker Compose
configuration, OPA 5/5, and `git diff --check` passed. Cargo ran 114 executable
tests and 16 doctests (130 total).

Two independent review tracks validated five original security candidates and
one follow-up concurrency defect. Regression-first fixes closed them all; the
final correctness and security closure reviews report zero remaining confirmed
findings.
