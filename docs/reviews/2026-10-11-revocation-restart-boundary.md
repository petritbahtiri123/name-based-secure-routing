# Inclusion restart integration: decision boundary

Investigation only; no implementation or persistence semantics changed. The
completed inclusion-v2 verifier remains a finite local conformance oracle.
Stage 3 remains partial; runtime and live authority remain disabled.

## Existing reusable pieces

`nbsr/federation/store.py` supplies closed canonical schema-1 encoding,
bounded descriptor-bound reads, retained tombstone/quarantine/replay checks,
and per-key generation/sequence/digest watermarks. Its repository writes the
primary snapshot and colocated watermark separately. The watermark can detect
an older primary when the newer watermark survives; it is not an independent
anchor against restoration of both files. Snapshot hashes establish integrity,
not the provenance or currentness of governing authority.

`scripts/revocation_inclusion_v2.py:FixtureState` additionally needs the exact
canonical record bytes, accepted checkpoint floor, retained revocation markers,
and event-ID-to-record-digest bindings. Schema 1 stores accepted-object metadata
and digest/timestamp replay entries; it has no defined lossless projection of
those inclusion fields. Encoding new meanings in existing keys or replay
digests would create an unreviewed persistence contract.

The approved WP6 continuity decision is explicitly a deterministic prototype.
Its trusted replica inputs and process-lifetime watermarks do not establish
crash/reboot durability or a trusted bootstrap for this path. The connector
federation adapter also explicitly excludes durable trust.

## Proposed next decision (not implemented)

Approve a separate, explicitly selected, versioned local inclusion snapshot
contract rather than reinterpret the existing schema. Specify exact record
bytes, checkpoint/log/profile identity, event-to-record bindings, retained
terminal facts, and the reference to independently accepted governing context.
Define size/cardinality limits, retention and capacity rejection, and the atomic
commit/recovery rule for these fields together. Restore must not manufacture
authority provenance, freshness, or a newer floor from a snapshot hash.

Real restart acceptance additionally needs an approved source of the retained
floor and current governing configuration, including what happens if all local
files are rolled back together. That provisioning decision remains separate
from a local serialization test. No external trust source is invented here.

Windows `secure_write_private` and `ensure_private_directory` harden ACLs;
repository `save` and one `load` repair branch invoke them. Current authority
excludes security-setting changes. Consequently no private-write/recovery test
was run, and the helpers were not bypassed or mocked to claim persistence.
A later authorized test can constrain the existing ACL helper to a fresh
test-owned temporary root; this does not itself settle the schema or trust gates.

## Measured validation and limits

Three existing pure store tests passed under the resource supervisor: canonical
round trip, fresh-node current-proof rejection, and invalid/oversized semantic
state rejection. No skips or deselections. These tests do not exercise filesystem
restart, interrupted writes, ACLs, or inclusion persistence. Exact command,
resource measurements, source hashes and independent review are in the adjacent
JSON manifest and retained evidence directory.

Root guidance was reviewed; no durable workflow or command changed, so AGENTS.md
was not edited for this investigation. Existing dirty work and historical
evidence were preserved. No keys, sockets, containers, installations, runtime
activation, commits or pushes were created by this iteration.
