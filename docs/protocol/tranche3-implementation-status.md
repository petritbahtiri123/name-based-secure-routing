# Production Go client Tranche 3 implementation status

Status: COMPLETE AND VERIFIED on the working branch.

## Transport Session ownership

`client/nbsr-go-client/internal/session` owns ephemeral TS resources by a full
reuse key containing Source Operator, gateway, profile, transport, device
identity generation, and policy generation/digest. Creation requires a current
sealed authority barrier, a current device credential, and the exact
generation-specific `PurposeTSProof` key. The proof key reference must differ
from both the Device ACP request key and local-state integrity key.

Each reuse key has one `CURRENT` generation and may retain one `DRAINING`
generation. The hard maximum is two. Generation numbers are monotonic and a
torn-down generation cannot be reopened. Tranche 3 exposes the explicit
`CURRENT` to `DRAINING` transition but implements no rotation trigger, recovery,
or automatic selection policy.

## Service Channel ownership

SC creation captures the TS and authority generation, validates the sealed
single-use RouteGrant reservation, releases all manager locks for wire I/O, and
then rechecks authority, TS eligibility, service, proof, grant, and `channel_id`
bindings before publication. The exact independently verified RouteGrant bytes
remain bounded sealed-authority state and are copied into the wire attempt;
provider output never authorizes a channel directly.

`ServiceHandle` remains a nonzero `uint32` local alias. Allocation is monotonic
within a TS generation and removed handles are never reused. The accepted wire
`channel_id` and channel generation are stored independently and remain the
wire identity. No ServiceHandle wire field was added.

## Bounds and teardown

Limits cover reuse keys, TS entries, SC entries, pending TS/SC creations,
coalesced waiters, per-item string bytes, and total committed logical state
bytes. Network calls occur outside ownership locks. Same-binding concurrent SC
creation is coalesced; differing bindings fail closed.

SC teardown removes only its handle and wire resource. TS teardown first
removes generation-local ownership, then closes every child channel and the
transport outside the lock. Repeated TS teardown is idempotent. Authority
invalidation makes an existing SC lookup fail closed and removes that SC.

## Tranche 3 nonclaims

This tranche does not implement Stream Credits, Application Streams, payload
forwarding, TS rotation policy, reconnect/recovery, automatic replay, Synthetic
IP, DNS interception, proxy/resolver integration, or performance optimization.
It does not change Core v0.2, QUIC framing, ROUTE_OPEN/ROUTE_ACCEPT schemas,
RouteGrant semantics, or existing `channel_id` behavior.

## Closure verification

Fresh closure runs passed the complete production Go client suite, the complete
Go race suite under UCRT, and `go vet ./...`. The focused Go interop
core/authority/transport packages passed, and the Rust admission,
channel-lifecycle, multi-channel, and Core v0.2 vector regressions passed 13/13.
A focused Tranche 3 security diff review completed with no remaining reportable
finding.
