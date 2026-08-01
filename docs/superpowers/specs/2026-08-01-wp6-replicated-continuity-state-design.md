# WP6 replicated origin and continuity state design

**Status:** Approved for implementation on 2026-08-01 under the bounded
delegated approval in the WP6 work request. The approved evidence boundary is
a deterministic storage-neutral prototype and multi-replica simulation. It is
not live consensus, multi-host HA, or production readiness.

## Goal and selected approach

WP6 adds a deterministic authority-state boundary that preserves accepted
OriginSet, policy, revocation, replay, tombstone, grant, and Service Channel
continuity state across simulated replicas without adding a wire value or
inventing a database or consensus protocol.

Three approaches were considered. Live etcd, Raft, or PostgreSQL would give
stronger operational evidence, but this Windows checkout cannot establish
credible multi-host, privileged, crash, or partition evidence. A custom NBSR
replication protocol would violate the roadmap. The approved approach is a
storage-neutral immutable state machine, repository abstraction, bounded
private-file persistence adapter, deterministic snapshot format, and quorum
simulation. A later adapter may put the same compare-and-swap state behind a
proven consensus store.

## Authority keys and ownership

The tenant is the top-level isolation boundary. Every authoritative object key
is `(tenant_id, service_id, kind, object_id)` with normalized ASCII textual
tenant/service IDs and a bounded opaque hexadecimal object ID. The kinds are
`origin`, `policy`, `revocation`, `replay`, `tombstone`, `grant`, and `channel`.
Keys never contain an Origin Endpoint, raw client identifier, credential,
exporter, grant bytes, or payload.

WP6 owns only the replicated envelope, ordering, retention, persistence, read,
and continuity decisions. Existing `DerivedOriginSet` and
`OriginSetTombstone` remain the origin authority models. Existing policy
version/fingerprint values remain caller-trusted policy authority. Existing
Core v0.1 `Revocation` and `RouteGrant` types are referenced by safe digests
and expiry, never reserialized. WP4 session/channel lifecycle and same-edge
resume rules remain authoritative; WP6 can deny or carry forward a safe
continuity marker but cannot mint a grant, resume proof, exporter binding, or
cross-edge authority.

## Monotonic state and non-resurrection

Every record has a positive 64-bit generation and sequence, a canonical
SHA-256 digest, an explicit retained-until timestamp, and a terminal flag.
For a key, generation and sequence never decrease. Equal generation and
sequence with the same digest is idempotent; equal version with a different
digest is equivocation; any component below retained state is stale. A higher
version must name the prior digest. Policy version is independently monotonic,
and the same policy version with another fingerprint is equivocation.

Revocation, consumed replay keys, tombstones, revoked channels, and revoked or
expired grants are terminal security facts. They remain represented by a
terminal record through their retention horizon. Expiry removes positive use
authority but never converts terminal state into reusable authority. Pruning
is allowed only when the entire protected authority lifetime has ended and a
higher durable tombstone prevents the old version from being accepted. The
prototype therefore retains terminal facts within a bounded snapshot and
fails closed at capacity instead of evicting them.

## Snapshot schema and integrity

The repository snapshot is a closed JSON object with schema
`nbsr-continuity-snapshot-v1`, tenant ID, monotonically increasing snapshot
generation, replica-set ID, sorted authorized replica IDs, quorum size,
logical `created_at`, sorted records, and a SHA-256 digest over ASCII canonical
JSON excluding the digest field. Unknown or missing fields, duplicate keys,
unsorted collections, non-canonical JSON, invalid types, excessive counts,
oversized strings/files, digest mismatch, and inconsistent tenant/replica
contexts are rejected before state is exposed.

Bounds are: 32 replicas, quorum between a strict majority and replica count,
4096 records, 256 KiB encoded snapshot, 64-byte text IDs, 64-byte object IDs,
and unsigned 64-bit counters/timestamps. Serialization is deterministic and
contains only digests and safe metadata. The file adapter uses the existing
atomic private-file writer and a descriptor-bound, regular-file, no-symlink,
bounded read before parsing. Persistence errors leave the prior in-memory
state unchanged.

## Replica, quorum, and read rules

Replica identities and the replica-set ID are local trusted configuration, not
snapshot claims. A simulated replica may attest only to the exact snapshot
digest it loaded. A read succeeds only when at least quorum distinct configured
replicas agree on one complete snapshot digest, generation, and context and no
other quorum-capable digest exists. Missing, unavailable, stale, partial,
forged-identity, conflicting, split-brain, or rollback evidence fails closed.
The simulator does not claim Byzantine consensus; injected attestations stand
in for authenticated store/client identity supplied by a future proven store.

## Failover, drain, and continuity

Failover is bounded to 5 seconds of caller-supplied monotonic elapsed time and
requires a fresh quorum read. Wall-clock timestamps determine authority
validity; monotonic elapsed time determines only operation duration. Drain is
bounded to the existing WP4 maximum of 30 seconds and never extends a grant,
session, policy, replay, or revocation lifetime.

A continuity read returns only a denial or a safe `ContinuityPermit` naming
tenant, service, prior channel digest, policy fingerprint, and snapshot digest.
It requires an active nonterminal channel, unexpired nonterminal grant, current
policy, no matching revocation/tombstone, and an unconsumed replay key. The
permit is not a wire proof and cannot authorize cross-edge resumption or
handover. Revoked/draining channels and consumed replay keys remain denied.

## Corruption, rollback, logging, and privacy

Snapshot rollback, same-generation digest conflict, torn or partial files,
corruption, and unavailable storage produce stable fail-closed error codes and
no state. Planning, simulation, verification, and reads never mutate a live
system. Reports contain counts, safe reason codes, snapshot generations, and
digests only; they never contain secrets, Origin Endpoints, raw client IDs,
credentials, exporter values, grant bytes, or payloads.

## Testing and evidence boundary

All runtime behavior uses RED-GREEN TDD. Tests cover canonical snapshots,
independent digest fixtures, corruption, unsafe deserialization, bounds,
symlinks, oversized files, tenant/service isolation, stale/replay/rollback/
equivocation rejection, split-brain ambiguity, quorum identity, fail-closed
reads, failover/drain limits, and exact non-resurrection invariants. Runtime
documentation tests prevent claims from drifting beyond deterministic and
simulated evidence.

No live etcd, Raft, PostgreSQL, multi-host, partition, crash/reboot durability,
operational rollback, cross-edge handover/resumption, OriginSet publication
interoperability, new wire protocol, global federation, or production HA is
implemented or claimed.
