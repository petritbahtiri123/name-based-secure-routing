# Production Go client Tranche 4 implementation status

Status: COMPLETE AND VERIFIED on `codex/nbsr-v3-wp0-wp1`.

## Accepted P2D semantics reused

The production Go client reuses `nbsr-stream-credit-1` without changing the
wire contract: 64 one-use slots, low watermark 16, refill to a new 64-slot
epoch, one current plus at most one draining epoch, one pending refill, exact
channel generation and actual source-bidirectional QUIC StreamID in the
deterministic CBOR preface, and same-stream ACCEPT value `0x00`. Unknown
profiles and Legacy downgrade do not enter the credited path. RouteGrant and
verified authority remain the authorization chain; a credit is only
synchronized admission state.

## Go ownership model

`internal/session.Manager` extends the existing TS/SC hierarchy. Each SC owns
one bounded credit window and a bounded Application Stream map. A reservation
contains the exact TS generation, local `ServiceHandle`, wire `channel_id`,
wire channel generation, authority generation, credit epoch, and credit slot.
The 64-bit epoch bitmap is mutated atomically under the manager lock, so one
slot cannot be reserved twice or moved to another SC or TS generation.

Application Streams are keyed by the exact TS generation, `ServiceHandle`, and
actual QUIC StreamID. Their states are pending admission, accepted, closed, and
failed. Limits cover committed streams, pending admissions, and logical stream
state bytes in addition to the Tranche 3 bounds.

## Refill and epochs

Closing admitted work after allocation leaves at most 16 current credits creates
at most one pending refill. The accepted control exchange runs outside the
ownership lock with bounded cancellation. An
exact matching grant activates the next monotonic epoch, moves the former
current epoch to draining, and restores 64 current slots. Failure or
cancellation clears pending state without restoring consumed credits. A
second draining epoch and therefore a third recognized epoch are rejected.
An inactive former epoch is retired immediately, so sequential refills remain
bounded without retaining an unusable draining epoch.

## Payload gate and final barrier

The manager reserves one credit before opening an actual wire stream. The
production admission helper writes the exact credited preface, reads exactly
one decision byte, closes on any malformed/reject result, and does not return
the wire stream before ACCEPT. `ApplicationStream.Write` independently checks
that state is accepted.

After ACCEPT, the authority manager performs a local grant-specific barrier for
freshness, expiry, revocation, exact owner, generation, and checkpoint while the
session manager atomically rechecks TS/SC identity, full credit binding/epoch,
duplicate StreamID, cancellation, capacity, and state bytes before publishing.
No provider or network authority call occurs on this path.

## Teardown

Stream close removes only the exact stream, releases its epoch assignment, and
closes its wire resource; repeated close is safe. SC teardown removes the
credit window and every child stream before closing network resources outside
the ownership lock. TS teardown recursively detaches all channels, credits,
and streams. Descendant lookups and writes fail after teardown.

## Real Go-to-Rust interoperability

The independent-process loopback harness routes positive credited admission
through an owned `streamclient.OwnedChannel` backed by production
`session.Manager`, against the existing Rust Quinn gateway
over QUIC v1, TLS 1.3, and `nbsr-quic-1`.

The final committed-source evidence path is recorded in the closure review.
It passes one ordinary stream and 128 sequential streams over one SC with two
ordered refills and 32 credits remaining. Malformed preface, profile mismatch,
Legacy downgrade, wrong-channel credit, and replayed credit are fail-closed
`APPLICATION_STREAM_REJECTED` cases with `payload_exposed=false`.

## Nonclaims and future work

This is local-loopback interoperability and bounded lifecycle evidence. It is
not WAN, physical-NIC, server-class capacity, recovery, or broad production
readiness evidence. Tranche 4 does not implement TS generation rotation,
reconnect/recovery, application replay, stream migration, Synthetic IP, DNS
interception, resolver/proxy integration, routing UI, or a performance campaign.
