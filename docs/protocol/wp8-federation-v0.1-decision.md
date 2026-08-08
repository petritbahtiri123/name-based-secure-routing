# WP8 Task 10 evidence decision

Observed evidence tier:

- live two-operator federation integration: PROVEN
- independent federation semantic verification: PROVEN
- independent route/stream wire interoperability: NOT YET PROVEN
- WP8 evidence closure: BLOCKED

The live lab uses distinct source and destination TLS identities and separate
typed Federation authority, then exercises the same Rust/Quinn `nbsr/1`
Transport Session, F75 ROUTE_OPEN v2 destination admission, Route Context,
Service Channel binding, and Application Stream. It transfers only the safe
fixture `NBSR-WP8-TASK10-LIVE-v1` after admission. Because both peers use the
same Rust transport implementation, this is not independent wire
interoperability.

Python remains the Federation reference authority. Node and Go independently
verify frozen Federation semantics and conformance artifacts; they are not
wire peers. Implementing a second strict QUIC/TLS, Core, COSE, F75, session,
exporter, channel, and stream implementation was assessed as a material
transport architecture and was not fabricated for this task.

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

Run `python scripts/verify_wp8_conformance.py` for the manifest-first public
matrix. The current result is `PASS_WITH_SKIPS`; the sole explicit skip is the
unproven independent route/stream peer.

The original 110-artifact Core v0.2 lock remains byte-identical. The separate
closed F75 overlay pins exactly four approved Rust integration replacements and
does not authorize any other Core artifact or behavior.

This evidence does not claim production readiness, Internet-scale federation,
performance, vendor or ISP adoption, production key custody, global governance,
anonymity, DDoS elimination, deployment SLA, or standard status.
