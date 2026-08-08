# WP8 Task 10 packet-capture procedure

Status: **captured and privacy-checked**. PktMon could not observe the filtered
Windows kernel loopback flow on this host; that attempt is not protocol
evidence. Npcap 1.88 subsequently captured the live flow through
`\Device\NPF_Loopback` using the exact BPF filter
`udp port 45975 and host 127.0.0.1`.

The public pcapng contains 36 packets, is 20,260 bytes, and has SHA-256
`84c7c026b45acd98550c3487adfa3ce60cbc62c591a16aae7046ce9cd6b1c798`.
Dumpcap reported 36 packets received and zero dropped. The inventory contains
both client-to-server and server-to-client packets plus protected QUIC
short-header traffic after the Initial exchange.

The checked-in wrapper prebuilds the focused test, starts dumpcap immediately
before the deterministic
loopback Rust/Quinn test
`federated_two_operator_route_transfers_only_after_f75_admission` and stops it
and uses a bounded two-second dumpcap autostop so the pcapng and interface
statistics are flushed gracefully after the test. It writes the capture tool/version, interface, filter,
packet count, available drop count, length, SHA-256, and test correlation to the
manifest. The resulting capture is acceptable only if
`tests/federation/test_packet_evidence.py` passes. That test inventories every
packet and rejects any interface, endpoint, protocol, or port outside the
approved flow.

The intended public evidence contains QUIC/TLS ciphertext between loopback test
endpoints. It must not contain private keys, credentials, subscriber identity,
protected Origin Endpoint literals, or the deterministic plaintext payload.
Packet ciphertext can demonstrate the live flow and encryption boundary; it
cannot by itself prove RouteGrant, Federation, admission, or application-state
correctness. Those properties require the conformance and runtime tests.
