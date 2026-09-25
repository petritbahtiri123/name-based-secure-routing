# Go/Rust held-lifecycle completion coordination

Observed RED at dfc22f2c: channels32 repeat2 completes32/32 Go responses, then
Rust panics in application.wait_for_send_ack with ApplicationStreamFailed.
The Go benchmark writes connection.ack and immediately CloseWithError(0), while
Rust still requires transport send acknowledgment. Receiving the response is not
proof that the destination's send-completion wait has returned. Preserve the
failure; no precise packet-loss or production failure attribution is claimed.

Bounded harness repair: an explicit default-off held-lifecycle completion option
for one sequential Go source. Rust publishes a per-cycle local completion marker
only after the existing run_lifecycle_connection returns (all unchanged send-ACK
waits and local cleanup). Go waits for that exact marker before publishing its
existing controller ack and closing the transport. Existing global/provider/
transport/controller deadlines stay unchanged. Missing/malformed markers fail;
source cancellation still closes its owned peer. No network message or public
wire/security/ACK semantics changes, and no production library edits.

The option is limited to held concurrent streams with one sequential source,
not multi-process/fanout scheduling. Feature-gated Rust publication rejects
unsupported modes. Old workload remains named and retained; fixed runs have a
new explicit configuration and fresh release binaries. Timed request results
remain before the completion gate; phase/cooldown lifetime changes are disclosed.

Verify observed RED, focused marker/close ordering/cancellation/default-off tests,
affected Go race/vet and Rust release tests/clippy/fmt, Python command/config
gates, then matched32-channel and50-cycle repeats with all failures preserved.
Do not call the marker itself proof of production cleanup or a transport ACK.

Implementation verification:28 Rust server release tests PASS; release Clippy -D warnings PASS; full Go interop race/vet PASS;156 affected Python tests PASS,1 existing skip; Ruff/fmt PASS. Independent focused review clean; final collected-marker binding separately reviewed and tested. Raw: C:/NBSR-build/go-completion-tests-20260925. Actual corrected release trials remain the next evidence gate.
