> Scope: component-level implementation notes retained from development. Historical test counts and verification paths below describe development evidence that is intentionally not distributed. See [current setup and delivery status](../README.md) for the integrated workflow. A standalone component does not start a collector.

# Local capture persistence prerequisite (2026-11-14)

`lab.capture.CaptureSession` is an opt-in single-owner library, not an activated
collector, CLI, watcher, remote transport or live dashboard connection. Existing
extractor, exporter, app, production inbox and data store remain unchanged.

A caller supplies a new directory under an existing private parent, plus a
source-identity label. Existing directories are rejected; sessions cannot be
resumed. The label remains explicitly unverified. The future transport must
independently establish source identity, exact offsets, append-only behavior,
reconnect continuity and run provenance before using this seam.

Each successful append writes a complete bundle containing exact captured
`raw.bin`, extraction ledger in `manifest.json`, and, when available, exact grouped
`grouped.ndjson`. All files are exclusive-created and flushed with fsync; a
same-parent directory rename makes the complete bundle visible. This is atomic
visibility, not a promise of directory-metadata durability across power failure.
Prior bundles are never overwritten by this library; filesystem permissions do
not make them immutable against other local software. Incomplete `.pending-*`
bundles are retained for diagnosis on I/O failure.

The caller must use `snapshot_path()` after a successful operation, not watch the
capture directory. It returns the last *advancing grouped* prefix, or None before
one exists. Diagnostic-only/partial-tail appends do not publish an old prefix as
new. The existing exporter deduplicates unchanged bytes. Only grouped bytes go
to it; raw evidence and manifests must stay private outside the inbox. There is
no automatic export or on-disk current-path pointer.

Any extraction or persistence error permanently disables this object, including
access to its prior snapshot path. A previously returned path is historical
only after failure. The bridge must stop export and expose unavailable/stale,
not keep exporting a remembered path. Best-effort `failure-raw.bin` preserves
extractor-admitted bytes, but storage failure can prevent even that write. The
original exception remains visible. Identity-conflicting or over-limit chunks
are not admitted by the extractor; the caller retains rejected input separately
within its own bounded transport policy.

`finish()` is explicit owner closure requiring a framed final marker. It retains
a manifest with owner_closed true; neither final nor owner_closed establishes
remote cleanup or measurement validity. No closure is inferred from silence.

Bounds: existing extractor 4 MiB/4096 records/64 KiB line; capture additionally
limits successful bundles to 4096 and cumulative serialized bundle bytes to
64 MiB. Best-effort failure raw can add at most 4 MiB. Full prefixes are copied,
so this is a bounded diagnostic seam, not an efficient long-run archive. The
caller must preflight cadence and run size; there is no automatic deletion.
Parent directory confidentiality and exclusive ownership are caller obligations;
this library does not change ACLs or protect against a malicious local owner.

## Verification

Five initial tests failed because the module did not yet exist. Eight focused
tests passed, covering retained exact bytes, diagnostic exclusion, unchanged
prefix handling, no-artifact partials, explicit closure, existing-dir rejection,
failure latch, interrupted writes and persistence budget.

Full final suite: 114 passed in 6.96 seconds; exact output is retained in docs/verification/2026-11-14-capture/full-suite.log. Default Windows sandbox first produced 44
failures / 64 passes due existing os.link temporary-file permission restrictions;
unchanged code passed outside that sandbox. No production data/inbox writes,
server restart, SSH connection, VM trial, dependency install or benchmark run.
Independent read-only review accepted the production source for the documented trusted-private-parent scope. Six additional tests cover rename/fsync failures, failure-evidence write failure preserving the primary error, snapshot-count exhaustion, and source identity/offset rejection. This is not evidence of real live integration.

## Still required

Owner-approved actual source/run identity, bounded authenticated read-only
transport, advancing real snapshots, final original-byte reconciliation,
cleanup proof and collector OFF/ON overhead qualification remain separate gates.
