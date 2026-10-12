# Connector development-only slice: completed bounded implementation

Base `c7abbc4423a9ad05cea9cdf6678c231a34cafd59`, branch `codex/nbsr-v3-wp0-wp1`; changes remain uncommitted.
The earlier incomplete handoff is historical. The parent relayed renewed evening
authorization; the previous overnight cutoff did not govern this continuation.

## Delivered and reviewed scope

The separate development registry assigns profile
`connector-registration-development-v1`, ALPN `nbsr-connector-dev-1`, independent
envelope version 1, six messages 24576..24581 and connector-local register/renew
action 24576. No frozen Core/Federation registry or signer purpose changed.
Strict Go/Rust decoders independently accept six shared vectors and reject 19.
The test-only Rust gateway owns one service's registration, operation counters,
four-result cache, pending exchange, authority revision and cleanup. The Go
coordinator implements bounded fixture attempts, proof/retry correlation,
renewal, withdrawal and explicit expiry cleanup. Runtime trust is not exported.
See `interop/nbsr-go-peer/connector/README.md` for interfaces, placement and commands.

## Diagnosis, corrections and retained negative evidence

The two owner failures at handoff were real: incomplete principal pinning and
confirmed cleanup not releasing a connection slot. Both regressions now pass.
Review also required preserving an unrelated pending proof, checking REQUEST
freshness, timer cleanup with failure retention, bounded authority deadlines,
and passing the complete request into the authority fixture.

Further deterministic red runs reproduced: two Rust failures (failed cancellation
still allowed proof completion; a late first request restarted an expired attempt),
four Go failure cases (local authority denial consumed a wire counter; reconnect
reused session state; ACCEPT was accepted before proof; expired ownership remained
eligible), and one Go callback-expiry failure. Minimal fixes keep cancellation
terminal, require fresh coordinators, preserve uncertainty for lost ACCEPT retries,
and recheck expiry immediately before installing ownership. All final regressions
pass. Independent review reported no remaining blocker in this narrow scope.

All failed attempts remain in evidence: expected availability failures, two initial
cache-permission failures (no test evidence), a SHA-256 formatting compile failure,
the behavioral red runs and four Clippy style diagnostics. Permission retries used
the existing caches; no dependencies or toolchains were downloaded.

## Final measured validation

| Check | Result |
|---|---|
| Python development package + configuration/CRP/model/federation/CBOR neighbors | 462 passed, zero failed/skipped |
| Rust development codec + owner | 1 + 13 passed, zero failed/ignored |
| Go development connector | 12 top-level tests; 58 passing test/subtest events |
| Go strict-CBOR neighbors | 3 top-level tests; 10 passing test/subtest events |
| Retained Go executable | Same 58 connector events pass; binary SHA-256 retained |
| Generator | 27 artifacts exact, including registry and manifest |
| Go vet/gofmt, scoped Rust Clippy/rustfmt, Python Ruff check/format | PASS |
| Source preservation | 19 tracked registry/build/transport/CBOR files unchanged; 24 historical source/vector artifacts unchanged |
| Scoped diff check and index | PASS; index empty |

The previous 459-test baseline is not substituted for these new checks: it was
rerun with three development-package tests, yielding 462. Go counts include parent
and subtest events and are not added to Python/Rust counts as unique scenarios.
Rust style-only edits were followed by a final test run to bind binary hashes to
the final sources. Exact commands, exit codes, durations and hashes are in the JSON
manifest and `evidence/connector-registration-development/2026-10-10-final/`.

## Resource and cleanup evidence

31 supervised Stage 3 runs are retained, including failures. Every direct
child was reaped; no resource/deadline abort occurred. All builds used offline
provisioned caches, at most two workers, 95-second work/120-second cleanup limits,
8 GiB starting disk, 6 GiB floor, a stricter 256 MiB per-run growth guard and 2 GiB
RAM reserve. Final read-only process check found zero visible relevant processes.
No containers, sockets, credentials, trust installation or deployment were created.
Existing caches, unrelated work and earlier evidence remain intact.

## Remaining real Stage 3 work

Stage 3 remains **partial; 2/10 stages complete**. The code uses synthetic authority,
non-TLS exporter fixtures, explicit time/polling and synchronous injected callbacks.
It proves no cryptographic registration authority, authenticated revocation receipt,
async cancellation, durable identity, origin traffic, live cross-language transport
exchange or READY state. Production client integration and independently reviewed
authenticated Go/Rust transport/authority composition, timers, cleanup and live
conformance remain. No commit, push, production allocation, authority-pin refresh,
security setting change or deployment was performed.
