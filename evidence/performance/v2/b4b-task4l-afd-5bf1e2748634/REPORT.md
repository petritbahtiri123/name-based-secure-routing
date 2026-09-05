# Task 4l matched AFD capture

DIAGNOSTIC. Repository SHA, measured sources and release binaries match for controls and captured runs at 5bf1e2748634e588a09d7dbe6eb9f8df4e6d7891. Both complete source/raw manifests and trace SHA-256 were verified. All 20 runs are valid with zero residual ownership. ETW lost events and buffers: zero.

Both observer gates FAIL; do not substitute captured timings for unobserved capacity. Five controls at each rate precede five captured runs at each rate, so temporal host drift is also a confound.

| Offered/s | Unobserved median admissions/s | Captured median admissions/s | Admission destination drops by captured repeat |
|---|---|---|---|
| 200 | 186.866 | 179.850 | 0, 0, 0, 0, 0 |
| 250 | 122.781 | 68.564 | 862, 615, 815, 716, 761 |

MEASURED: 3,769 AFD datagram drops, all Reason=2; Windows FormatDescription renders this as "Insufficient local buffer space". DERIVED: every drop maps to the admission listener via process/endpoint identity, successful local bind, and run time window. Zero unmatched drops. No drops map to the established listener. 10,879 create and 10,512 bind events were exported.

This identifies actual admission-socket buffer loss under the diagnostic workload. INCONCLUSIVE: exact contribution to each unobserved handshake delay, observer equivalence, and whether a bounded socket-buffer change resolves the admission boundary. No host/hardware ceiling or production capacity is established.

DIAGNOSTIC configuration probe: three newly bound IPv4 loopback UDP sockets each report SO_RCVBUF=65,536 and SO_SNDBUF=65,536 bytes. This is not live NBSR socket introspection. Local pinned Quinn 0.11.11 Endpoint::server binds a standard UDP socket; quinn-udp 0.5.15 Windows initialization does not increase SO_RCVBUF. This motivates measuring and testing bounded receive buffering; no implementation optimization has been applied in this stage.

Reproduce role analysis with: python scripts/analyze_b4b_task4l_afd.py C:/NBSR-build/b4b-task4l-etw-20260905-152256 <new-output.json>. Input JSONL is an ordered Get-WinEvent export of event IDs 1000/1030/1033 from afd-drops.etl, with UTC, execution PID and named EventData values. The analyzer ignores execution PID for socket ownership, resets reused endpoint state, rejects overlapping run windows and retains unmatched drops. Raw files and exports remain external and are bound by external-inputs.json.

Validation: literal RED for new analyzer, then focused Python tests and Ruff. Protocol, wire, trust, security and main remain unchanged.
