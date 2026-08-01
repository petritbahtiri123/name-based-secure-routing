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
file reads. Corruption and rollback expose no state. Reports are deterministic
and privacy-safe. Live consensus, multi-host HA, crash/reboot durability,
partition tolerance, operational rollback, interoperability, and production
readiness remain unavailable and unclaimed.
