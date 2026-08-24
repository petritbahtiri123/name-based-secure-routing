# Tranche 4 Stream Credits and Application Streams Design

## Scope

Tranche 4 extends the production Go client's existing owned Transport Session
and Service Channel hierarchy with the accepted `nbsr-stream-credit-1` sender
state and explicitly owned Application Streams. It does not change the frozen
wire profile, RouteGrant authority, TS rotation, recovery, resolver, proxy, or
Synthetic IP behavior.

## Ownership and bounds

Each owned Service Channel contains one credit window and a bounded map of
Application Streams. The credit binding includes the exact TS generation,
local `ServiceHandle`, wire `channel_id`, wire channel generation, RouteGrant
digest, and authority generation. The window contains exactly 64 slots in the
current epoch, at most one draining epoch, and at most one pending refill.
Credits are reserved once and are never returned for reuse after a network
attempt.

Application Streams are keyed by the exact TS generation, ServiceHandle, and
actual QUIC StreamID returned by the transport adapter. Their state is
`PENDING_ADMISSION`, `ACCEPTED`, or `CLOSED/FAILED`. Configured limits bound
committed streams, pending admissions, and logical state bytes.

## Admission flow

The manager validates the owned current TS, Service Channel, authority
generation, and credit window under its state lock, atomically reserves one
credit, and reserves one pending-admission slot. It then releases the lock,
opens an actual bidirectional QUIC stream, writes the exact accepted P2D CBOR
preface containing the actual StreamID, and waits for the accepted admission
response. No ownership lock is held across these operations.

After ACCEPT, a final local barrier revalidates authority freshness and
revocation outside the state lock, then rechecks the exact TS, SC, authority,
credit epoch/binding, and StreamID under the lock before publishing the stream.
Any failure closes the wire stream, removes pending state, and leaves the
credit consumed. The stream write API checks `ACCEPTED` itself before every
payload write.

## Refill and epochs

Initial epoch 1 has 64 credits. When reservation makes the current epoch's
available count at most 16, one coalesced refill operation may request the next
monotonic epoch. A successful refill moves the old current epoch to draining
and installs a fresh 64-credit current epoch. Refill failure or cancellation
clears the single pending marker. A third simultaneously recognized epoch is
rejected. Draining epochs accept only already-reserved work and retire only
after their pending assignments reach zero.

## Teardown

Application Stream close removes only that stream and closes its wire resource;
repeated close is safe. Service Channel teardown first removes ownership,
invalidates all unused credits and pending refill state, and detaches all child
streams before closing network resources outside the lock. Transport Session
teardown does the same recursively for every Service Channel. Admission races
with authority invalidation or teardown fail at the final barrier.

## Wire authority and validation

The Go codec is checked against accepted P2D vectors and the Rust gateway. The
production integration test starts real Go and Rust processes over QUIC and
proves ACCEPT-before-payload, duplicate rejection, wrong-profile rejection,
binding rejection supported by the harness, and multiple streams/refill over
one SC. Unit mocks cover ownership races but are not closure interop evidence.

The final gate runs the complete Go client suite, Go race suite under UCRT,
`go vet`, relevant Rust transport/P1F/P2D/vector regressions, a focused security
review, and one scoped re-review. Claims remain local-loopback interoperability,
not WAN, physical-NIC, capacity, recovery, or production-readiness evidence.
