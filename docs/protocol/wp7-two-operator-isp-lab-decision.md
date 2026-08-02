# WP7 two-operator ISP lab decision

**Status:** WP7 is complete and evidence-closed at deterministic two-operator
lab scope. The implemented boundary is single-threaded, in-process, and
configuration-only. It is not a live two-ISP deployment or federation
protocol.

## Authority and admission boundary

One `OperatorPairRuntime` owns the bounded limiter, allocation registry,
source and destination audit logs, replay ledger, and destination connector
for one modeled operator pair. Trusted composition must retain one
OperatorPairRuntime per modeled operator pair. Its bounded registry freezes
each exact admission context, local trust tuple, and caller-verified
`VerifiedAuthority`, then issues a sealed `TwoOperatorLab` handle pinned to
that registered entry.

Source-first admission validates the source operator, tenant, subscriber
pseudonym, name, route, service, edge, policy, gateway, continuity, RouteGrant,
channel, exporter, and freshness evidence before destination validation. The
destination then independently validates its operator-owned route, service,
channel, tunnel, edge, policy, gateway, continuity, and exact configured trust
evidence. The 5-second source admission and 5-second destination admission
limits accept exactly 5,000 ms and deny 5,001 ms. Drain is bounded to 30
seconds and cannot outlive authority expiry.

Successful admission preflights quota, allocation, replay, capability, and
both owned audit changes before committing them together in the deterministic
single-thread model. Failed gates, overload, audit exhaustion, and failed
drain do not partially grant authority. Pair-wide state prevents fresh
same-pair handles from bypassing aggregate capacity or replay protection.
Deterministic fair-share eviction revokes the exact displaced connector
capability and records safe revocation events for both operators.

## Connector and privacy boundary

The Origin Endpoint remains confined to the ISP-B `DestinationConnector` and
the connector performs no network I/O. Connector use requires the exact
registered capability object issued by the owning runtime. Its public receipt
is domain-separated over the connector label and capability digest and is not
derived from the Origin Endpoint. Profiles, admission state, audits, reports,
topology, scan results, exceptions, and verifier output contain no raw endpoint
or endpoint-derived verifier.

Subscriber inputs are operator-local HMAC-SHA-256 pseudonyms supplied by the
trusted source boundary; the model never receives a raw subscriber identity.
The canonical bounded topology has only synthetic/public lab nodes and one
opaque connector label. Raw-scan evidence proves non-discovery and
non-reachability only inside that exact simulated topology.

## Review disposition

Independent correctness and security review confirmed the original composed
authorization, verified-authority, audit integrity, endpoint-oracle,
fair-share, timing, and duplicate-member gaps. Regression-first fixes closed
those boundaries. A second review found that separately constructed handles
could bypass pair-wide capacity and replay state; `OperatorPairRuntime` now
owns the shared authoritative state. The final static closure reviews report
zero remaining confirmed findings and no new Critical or Important security
regression within the approved lab model.

## Completion evidence

Fresh validation on 2026-08-02 recorded 106 focused WP7 tests and 1,077 passed
and 1 skipped in the full Python suite. Ruff check passed; Ruff format reported
140 files already formatted; and `pip check`, Core v0.1/Core v0.2 regeneration,
WP4 exporter Python and independent Node verification (2 valid and 21
invalid/mutation cases), and the independent WP6 snapshot verifier passed. The
WP7 verifier passed twice with byte-identical safe JSON output.

With `CARGO_TARGET_DIR` set to the explicit writable non-OneDrive path
`C:\codex-cargo-target\nbsr-wp7-final`, Rustfmt and Clippy with `-D warnings`
passed, and Cargo ran 114 executable tests plus 16 doctests (130 total). Docker
Compose configuration passed, and OPA passed 5/5 policy tests. The bounded
nine-file WP7 runtime/config/script/document scan found zero known-endpoint,
forbidden raw-identifier, or positive-overclaim matches; the tracked-artifact
scan found zero suspicious temp/generated/scan artifacts. `git diff --check`
passed.

## Non-claims

WP7 makes no production readiness, no live two-ISP deployment, no independent
real administration, no real subscriber enforcement, no DDoS mitigation or
elimination, no origin anonymity, no global federation, no signed ownership
or delegation, no transparency, no trust distribution or rotation, no new
wire protocol, no OriginSet publication interoperability, no cross-edge
handover or resumption, no live consensus, no complete partition tolerance,
no independent interoperability, and no raw-scan resistance outside the exact
simulated topology claims.

The local verified authority is caller-verified evidence only: WP7 does not
parse, mint, sign, distribute, rotate, or persist WP3-WP6 authority. The model
also provides no process-global uniqueness, no distributed replay protection,
no persistence, no concurrency safety, no crash durability, no distributed
transaction, and no protection from hostile same-process access to private
Python internals. Rebalance is simulated eviction, not a live resource
scheduler.
