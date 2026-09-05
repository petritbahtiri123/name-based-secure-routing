# Task 4l AFD diagnostic: admission socket receive-buffer drops

Status: DIAGNOSTIC. Matched comparison REJECTED for repository_sha mismatch. No accepted observer gate or new capacity claim.

The agent committed the nonpaged-memory profile correction during the running control block. Controls record 438d7e2d821b97d11f9fa629c761f84260b286f9; observed runs record 07ae7fd927a53636d1ee8f8df3cf2301dffc606e. Binary hashes and measured source hashes match exactly, but the strict comparator correctly refuses different repository revisions. That assertion remains unchanged. A repeat at one frozen SHA is required.

MEASURED: AFD trace contains 11,013 socket-create, 10,732 bind and 7,575 datagram-drop events; trace statistics report zero lost events and buffers. All 7,575 drops have Reason=2. Windows Get-WinEvent FormatDescription renders this as "Insufficient local buffer space". All drops map to the admission destination socket; no drops map to the established destination or an unknown cell. Both five-repeat control cells and both five-repeat observed cells have valid=true and cleanup.all_zero=true. Their complete manifests were verified.

DERIVED socket mapping: process-object plus endpoint-object identifies socket state in chronological AFD events. Reset state on create entry (1000, EnterExit=0); take local port from successful bind exit (1030, EnterExit=1, Status=0), decoding bytes 2:4 of the socket address in network byte order. Match each drop timestamp to the recorded run interval and the local port to its admission/established endpoint command. Do not use the event execution PID as socket ownership. No unmatched drop windows remain. analysis.json preserves per-repeat counts, sizes and unique remote socket addresses counted; addresses themselves stay external.

| Offered/s | Drops per observed repeat | Total |
|---|---|---|
| 200 | 1577, 0, 0, 1, 499 | 2077 |
| 250 | 1040, 1938, 1468, 528, 524 | 5498 |

INCONCLUSIVE: capture observer equivalence, full explanation of every handshake delay, and whether changing socket buffer configuration alone resolves the admission boundary. This proves admission-socket buffer drops during these diagnostic runs; it does not establish host/hardware saturation or production NBSR capacity. No production optimization has been made.

Reproduction: the trace can be exported using Get-WinEvent -FilterHashtable with Path pointing to afd-drops.etl and ProviderName Microsoft-Windows-Winsock-AFD, with -Oldest. Event XML provides Process, Endpoint, EnterExit, Status, Address, BufferLength and Reason; its System element provides UTC time. Render the first event 1033 with FormatDescription to verify the reason text. The exported JSONL and derived role summary remain external and are SHA-256 bound in external-inputs.json. Use xperf -i <trace> -tle -a tracestats for trace integrity. Do not rerun into this evidence directory.
