# WP8 Task 10 evidence decision

Observed evidence tier:

- live two-operator federation integration: PROVEN
- independent federation semantic verification: PROVEN
- independent route/stream wire interoperability: PROVEN
- WP8 evidence closure: COMPLETE — READY FOR HUMAN APPROVAL

The live lab uses distinct source and destination TLS identities and separate
typed Federation authority, then exercises the same Rust/Quinn `nbsr-quic-1`
Transport Session, F75 ROUTE_OPEN v2 destination admission, Route Context,
Service Channel binding, and Application Stream. It transfers only the safe
fixture `NBSR-WP8-TASK10-LIVE-v1` after admission. Because both peers use the
same Rust transport implementation, this path alone is not independent wire
interoperability. Task 10B provides the separate independent proof.

Python remains the Federation reference authority. Node and the Task 9 Go
implementation independently verify frozen Federation semantics and are not
wire peers. Separately, Task 10B implements a clean Go/quic-go source peer that
independently validates Core v0.2, COSE RouteGrant authority, F75, correlation,
the WP4 exporter context, stream admission, and payload gating. It exchanged
`CLIENT_HELLO`, `EDGE_HELLO`, `ROUTE_OPEN` v2, `ROUTE_ACCEPT`, `STREAM_OPEN`,
and `STREAM_ACCEPT` with the Rust/Quinn destination and transferred the
33-byte safe fixture only after admission.

Public-safe packet evidence is
`evidence/wp8-task10/live-federation.pcapng`, 20,260 bytes, SHA-256
`84c7c026b45acd98550c3487adfa3ce60cbc62c591a16aae7046ce9cd6b1c798`.
Npcap 1.88 captured 36 packets with zero drops on `\Device\NPF_Loopback` with the exact BPF
filter `udp port 45975 and host 127.0.0.1`. Complete inventory validation pins
interface 0, both endpoints to `127.0.0.1`, UDP, and one endpoint to port
45975. The capture contains traffic in both directions and protected QUIC
short-header packets after the Initial exchange. The privacy regression finds
no private-key marker, subscriber literal, protected Origin Endpoint, or safe
plaintext fixture.

Task 10B public-safe packet evidence is
`evidence/wp8-task10b/independent-go-rust.pcapng`, 16,500 bytes, SHA-256
`00b1c645f08521ecc88c8e8892fca3da986f679b1b6c4de5ba4532bda7341ac1`.
Npcap loopback capture contains 27 allowlisted UDP/45976 packets with zero
drops, no decryption key logging, and traffic in both directions.

Run `python scripts/verify_wp8_conformance.py` for the manifest-first public
matrix. The final run observed 2,594 passed, 0 failed, and one documented
Windows platform skip for a POSIX-only file-mode assertion. Task 10B's nested
runner observed 37 passed, 0 failed, and 0 skipped. Independent correctness and
security/privacy reviews both returned `READY`.

The original 110-artifact Core v0.2 lock remains byte-identical. The separate
closed F75 overlay pins exactly four approved Rust integration replacements and
does not authorize any other Core artifact or behavior.

This evidence does not claim production readiness, Internet-scale federation,
performance, vendor or ISP adoption, production key custody, global governance,
anonymity, DDoS elimination, deployment SLA, or standard status.
