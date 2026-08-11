# NBSR Stream Credit Extension 1

Status: approved P2D implementation profile, 2026-08-11.

## Scope and profile

`nbsr-stream-credit-1` is a versioned Core v0.2-compatible extension for one
authenticated Transport Session. It changes only admission of Application
Streams belonging to an already-active Service Channel. Core v0.1 and the
existing Core v0.2 `STREAM_OPEN`/`STREAM_ACCEPT`/`STREAM_REJECT` path remain
unchanged when this profile is absent.

The profile is selected before channel activation from authenticated local
policy and peer capability state. Both peers must record the exact profile
identifier. A peer required by policy to use credits rejects an absent,
stripped, unknown, or differently versioned critical profile with the existing
safe unsupported/downgrade failure. Failure never triggers automatic fallback.
Explicit policy may select the legacy path before a new session is attempted.

## Authority separation

A RouteGrant authorizes a route and service context. A Service Channel binds
that authority to one authenticated Transport Session. A stream credit permits
one admission attempt inside that channel; it is synchronized state, not a
signed token or bearer credential. It carries no key, RouteGrant body, origin
address, hostname, or application metadata.

The logical credit identity is the tuple `(session_id, route_id, channel_id,
channel_generation, revocation_generation, credit_epoch, slot)`. Validation
also requires the channel's existing RouteGrant digest, service, policy,
capacity, expiry, revocation, and replay invariants to remain valid.

## Window state

The mandatory profile constants are `credit_count = 64` and
`low_watermark = 16`. Each endpoint stores, per active channel:

- exact profile selection;
- session, route, channel, RouteGrant, generation, revocation, and lease binding;
- current epoch with a 64-bit consumed bitmap;
- optionally one immediately preceding draining epoch with a 64-bit bitmap;
- one bounded assigned-stream count for each recognized epoch; and
- at most one pending refill request.

Epochs are non-zero unsigned 64-bit integers and advance by exactly one.
Wrapping is forbidden. A new channel generation starts with epoch 1. No more
than current plus one draining epoch is recognized. Retiring a draining epoch
releases its bitmap; older epochs reject without allocation.

Credits are opportunities, not reservations. Granting a window allocates no
Application Stream, upstream connection, payload buffer, or per-slot object.
An admitted ordinary stream stores its epoch in its existing stream entry;
the two epoch counts therefore require no per-credit or per-admission heap
object.

## Application Stream preface and response

The credited stream starts with a shortest-form QUIC variable-length length
prefix followed by one deterministic CBOR item. The encoded CBOR item is at
most 128 bytes and must be completely buffered in a fixed bounded preface
buffer before semantic work. Indefinite lengths, duplicate keys, non-preferred
integers, tags, floats, unknown keys, trailing bytes, or oversized lengths fail
closed before audit, capacity reservation, or upstream work.

The preface is the closed map:

| Key | Field | Type and bound |
|---:|---|---|
| 0 | profile version | uint, exactly 1 |
| 1 | channel ID | bstr, exactly 16 bytes |
| 2 | channel generation | uint64, non-zero |
| 3 | credit epoch | uint64, non-zero |
| 4 | credit slot | uint, 0 through 63 |
| 5 | QUIC stream ID | uint, source bidirectional ID, non-zero, divisible by 4 |

The receiver verifies key 5 equals the actual QUIC stream identity. Session,
route, grant, service, lease, and revocation bindings are taken from
authenticated local channel state rather than repeated on the data stream.

The same stream returns a bounded one-byte decision: `0x00` ACCEPT or `0x01`
REJECT. Other values and EOF fail closed. The source sends no application byte
until it receives ACCEPT. The destination exposes no payload read/write permit
until it has atomically committed credit and stream replay state and written
ACCEPT. REJECT resets/stops only that stream.

## Consumption transaction

For one received preface the destination, under the owning session's state
lock, performs in order: profile, session, channel, generation, live
route/channel lease, revocation generation, epoch, slot range, duplicate bit,
live channel/session capacity, P1F replay-history hard cap, existing binding
and policy checks, and audit availability. It then atomically sets the bit,
commits the actual QUIC stream ID to `used_stream_ids`, creates the ordinary
stream gate/state, and emits ACCEPT. Any failure before commit leaves both
credit and stream replay state unchanged. Failure after commit is terminal for
that credit and stream ID; neither becomes reusable.

Different slots have no protocol ordering dependency and use no
`ControlEnvelope.monotonic_sequence`. The control stream retains monotonic
ordering for channel lifecycle and refill mutations. Concurrent attempts for
the same slot serialize only on the bounded channel-state mutation; exactly
one may commit.

## Refill and transition

After a successful local allocation leaves 16 usable current credits, the
source records one asynchronous refill request. It continues with remaining
credits. Repeated allocations at or below the watermark do not create another
request. A request while an immediately preceding epoch is still draining
fails before pending state is set. Refill control revalidates active state,
lease, revocation generation, route and policy, current per-channel ordinary
stream capacity, and remaining per-session P1F replay-history capacity, then
grants exactly the next epoch with 64 clear bits. Revalidation reserves no
stream, replay entry, byte quota, or other resource. It neither creates nor
renews a RouteGrant.

On activation, the prior current epoch becomes draining and the new epoch
becomes current. Streams already assigned from either may arrive in any order.
No third epoch activates until the draining epoch is retired. A control failure
or cancelled refill clears only pending state; already-granted credits remain
valid. Exhaustion without an activated refill rejects new attempts.

### Ordered refill control frame

Refill request and grant use the authenticated Transport Session's existing
ordered bidirectional control stream. Exactly one such control stream is
claimed per authenticated QUIC connection/session by the first open or accept
API call. Route and channel lifecycle messages and every refill reuse that
claimed stream. A second open or accept fails closed and cannot become an
alternate refill or lifecycle authority. Each refill message is one
shortest-form QUIC variable-length length prefix followed by an exact 30-byte
extension body. The length prefix is therefore the single byte `0x1e`. The
body is closed and has this fixed layout:

| Offset | Bytes | Field | Required value |
|---:|---:|---|---|
| 0 | 4 | magic | ASCII `NSCR` (`4e534352`) |
| 4 | 1 | version | `0x01` |
| 5 | 1 | kind | request `0x01`; grant `0x02` |
| 6 | 16 | channel ID | exact active Service Channel ID |
| 22 | 8 | epoch | non-zero unsigned 64-bit, network byte order |

No other body length, magic, version, kind, zero epoch, trailing byte, or
alternate encoding is valid. A receiver expecting a request rejects a grant
and a receiver expecting a grant rejects a request. Malformed or unsupported
frames fail as the existing privacy-safe invalid control frame and do not
activate an epoch, consume a credit, create stream replay state, allocate an
Application Stream, or reveal version inventory. A terminal control failure
or cancellation clears the source's pending refill through the typed session
cancel operation; it does not restore consumed credits.

After a successful local allocation first leaves 16 current credits, the
source records exactly one pending next epoch and sends REQUEST. It may keep
allocating the 16 remaining credits and does not block at the low watermark.
The destination accepts REQUEST only when the named channel is active under
the same authenticated session, route, RouteGrant digest, channel generation,
revocation generation, lease, and policy, with at least one current
per-channel stream slot and one per-session P1F replay-history entry remaining.
The check reserves neither resource. Its remaining current credit count is at
most 16, it has no pending refill, and it has no already draining epoch. It
records and activates exactly the requested current epoch plus one, then sends
GRANT with the identical channel and epoch. The source
activates only an exact GRANT matching its one pending epoch. Wrong-channel,
stale, skipped, repeated, wrapped, unsolicited, and concurrent refill values
fail closed. Neither message creates or renews a RouteGrant.

Once all streams assigned from the prior epoch have reached terminal
admission state, each endpoint may retire that draining epoch. Each successful
ordinary stream release, cancellation, or rejection removes its existing live
stream entry and decrements that entry's epoch count exactly once; repeated
terminal cleanup cannot decrement it again. Retirement fails closed while the
draining epoch's count is nonzero, including when newer-epoch streams finish
before delayed older-epoch streams. Retirement is a local bounded-state
transition; the ordered request/grant exchange already synchronizes the epoch
activation. Until retirement, a further refill request is rejected before
pending state is created and cannot activate a third recognized epoch.

The deterministic control vectors use channel ID
`404142434445464748494a4b4c4d4e4f` and epoch 2. The exact complete framed
request is
`1e4e5343520101404142434445464748494a4b4c4d4e4f0000000000000002`; the
exact complete framed grant is
`1e4e5343520102404142434445464748494a4b4c4d4e4f0000000000000002`.

## Revocation, expiry, close, and cleanup

Revocation and expiry dominate unused credits. Admission rechecks authoritative
channel state immediately before commit, including races after preface parse.
Revoke, channel close, and session close discard all window and pending-refill
state. Existing admitted streams retain the repository's established immediate
revoke/completion-grace behavior. Renewal or a new channel generation creates a
fresh epoch namespace; old credits never extend authority.

## Errors and privacy

Internally the profile distinguishes malformed preface, unsupported profile,
invalid slot, duplicate slot, stale epoch, wrong channel, wrong generation,
wrong session/stream, expired, revoked, over capacity, replay capacity, and
internal/audit failure. On the data stream all are the same bounded REJECT;
existing privacy-safe audit records may retain the typed category. No response
reveals policy internals, supported-version inventory, RouteGrant bytes, or
origin information.

## Security invariants

Credits never cross a Transport Session, route, service, channel, generation,
destination edge, epoch, lease, or revocation generation. The bitmap does not
replace `used_stream_ids` or `ReplayHistoryLimit`. No payload or upstream side
effect occurs before ACCEPT. Malformed/flooded prefices consume only fixed
bounded parsing work. Refill state and recognized epochs are strictly bounded.
Core v0.1 numeric meanings and bytes are untouched.

## Deterministic vectors

Conformance vectors live under `vectors/stream-credit-v1/`. Each case records
the exact preface hex, authenticated context, actual stream ID, expected typed
decision, whether the slot and stream replay state mutate, and the resulting
bitmaps. The closed manifest includes valid slots 0 and 63 plus invalid slot
64, duplicate, stale epoch, wrong channel/generation/session/stream, malformed,
unsupported-profile, expired, revoked, capacity, and replay-cap cases.
