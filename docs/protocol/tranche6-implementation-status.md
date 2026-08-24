# Production Go client Tranche 6 implementation status

Status: IMPLEMENTED; final verification is recorded at handoff.

## Implemented scope

The production Go client now canonicalizes presentation names with the IDNA
lookup profile, rejects IP literals and invalid DNS names, and derives
`ServiceDigest` as SHA-256 over canonical ASCII bytes. An immutable resolution
result preserves the opaque service identity and exact RouteIntent provenance.

The existing bounded MappingTable now owns that provenance. A bounded,
single-use FlowStore correlates explicit-proxy application flows to immutable
MappingIDs. Mappings are monotonic, byte-accounted, non-evicting, expiry-bound,
retained only for active references, and rebuilt empty after restart.

The approved first adapter is an explicit local SOCKS5 domain-name and HTTP
CONNECT proxy. It resolves the request target before secure authority
selection, supports unrelated services on the same shared Synthetic IP and
port, bounds request bytes and active connections, and fails closed when the
target or correlation is missing. HTTP Host and TLS SNI are not selectors.

Mapping-owned RouteIntent fields construct the existing AuthorityKey request.
The verified authority and existing TS, SC, Stream Credit, and Application
Stream ownership remain unchanged. Digest and service-identity mismatches fail
at each local transition. MappingID and FlowContext remain local-only; no wire
message or field changed.

## Nonclaims

This tranche does not provide transparent DNS interception, a TUN/WFP adapter,
automatic application proxy configuration, UDP routing, resolver failover, or
install/rollback packaging. The explicit proxy requires a proxy-aware or
locally configured application. The configured shared Synthetic IP is local
configuration, not a protocol address or authority.

## Verification

The final uncommitted Tranche 6 worktree based on
`b5c66bb005a326f81c352d38ad87c48b71f550d9` was verified with:

- `go test ./... -count=1 -timeout=120s`;
- UCRT `go test -race ./internal/corestate ./internal/resolution
  ./internal/adapter/... ./internal/authority ./internal/session ./streamclient
  -count=1 -timeout=180s`;
- `go vet ./internal/corestate ./internal/resolution ./internal/adapter/...
  ./internal/authority ./internal/session ./streamclient`;
- `git diff --check` (line-ending warnings only).
