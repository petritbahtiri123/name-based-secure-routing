# Receive/ACK revocation followed by future Drop

Base: `b6afdcdfe6daa85f50d633461df050d0e870ee7f`, the published 7/7-green CI baseline. This correction is reviewed for the authorized local source/evidence commit; authority activation and publication remain pending. It addresses the inherited receive/ACK gap identified in the owned-send review, not a newly introduced ACK regression.

## Root cause and minimal correction

`force_reset` marks cancellation, clears retained receive/completed reservations and notifies waiters. Its transport RESET/STOP uses `try_lock`, which cannot acquire a mutex held by a pending receive or ACK future. If that future is dropped without another poll, notification handling never resets the transport, despite quota already being zero.

Each affected method now declares the existing unarmed `BorrowedSendCancellation` before its async mutex guard. Reverse Drop order unlocks first, then retries the existing reset only when cancellation is marked. Ordinary receive cancellation still retains bytes/quota for resume; ordinary ACK cancellation preserves FIN and quota. ACK remains transport acknowledgment, not application processing or quota release. No authority/security semantics, frames, timeouts or limits change; no background task is introduced.

## Reproduction and validation

Two current-thread authenticated loopback tests with 64-byte windows establish pending mutex ownership, revoke, and drop the future without repoll. Stream/connection owners remain alive while the peer observes terminal behavior. Current-thread scheduling prevents endpoint progress between FIN, the initial ACK poll and revocation. Quota release and eventual owner release are separate assertions; expected failure assertions run after bounded cleanup.

Before implementation: both fail as intended. Receive waits two seconds without RESET; ACK produces clean EOF. After the two guards: both pass, observing RESET and STOP with code 1. An ordinary ACK-cancellation control preserves FIN, resumes ACK waiting, retains quota until explicit release, and passes.

- Focused GREEN: 2 passed (0.15 s; supervisor 7.63 s).
- Full library: 111 passed, 1 existing ignored soak (6.89 s; supervisor 7.25 s).
- Application stream: 4 passed; stream-credit integration: 12 passed, including ordinary ACK cancellation/revocation/peer-close tests (combined supervisor 26.89 s).
- All-target benchmark Clippy with denied warnings, default-feature library check, Cargo formatting and diff whitespace: passed.
- Independent static review: no blocking findings; reviewer ran no tests.

Raw RED/GREEN sources, final patch, command logs/results and source/binary hashes are recorded in the adjacent JSON. Offline existing cache, two workers and the 95-second supervisor/resource guards were used. Every child was reaped; no matching Rust build/test processes remained. No containers were created.

## Authority and remaining limits

Authority files remain untouched. The direct working-tree validator stopped on unchanged `admission.rs` CRLF bytes; normalization matches its HEAD bytes. Separately, canonical adapter comparison confirms HEAD matched the approved pin and this correction no longer does. This is not a green authority result. A separately approved versioned source authority is required before integrating the new adapter into that gate; no old pin may be refreshed in place.

No hosted/Linux run, real-process prerequisite expansion, WAN/capacity trial or prolonged soak was performed. The existing ignored soak remains excluded. Root AGENTS guidance already describes the required versioned-authority boundary and needs no change. A later explicit instruction authorizes a scoped local source/evidence commit and an approval proposal; no authority activation, push, bypass or deployment is included.
