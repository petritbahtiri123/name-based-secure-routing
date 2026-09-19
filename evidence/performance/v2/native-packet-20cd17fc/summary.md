# Native packet accounting subset

Source 20cd17fc adds read-only single-interface exact IPv4/UDP pcapng analysis.
Literal first RED: 21 missing-module failures. Focused review RED: two embedded
loss counter cases wrongly accepted; both now reject. Final combined native/B1
suite: 42 PASS; matrix contract: 2 PASS; scoped Ruff/diff checks PASS.

Three real synthetic UDP echo captures on two Docker network namespaces retain
200 packets each (100 per direction), zero dumpcap/pcap/interface/flushed drops.
Each capture has 14,200 captured frame bytes, 11,400 IPv4 bytes, 7,400 UDP bytes,
and 5,800 UDP payload bytes. All five totals exactly match independent TShark
exports. Truncated-file and wrong-port variants reject for every retained capture.
Dumpcap capability warnings remain in stderr; these are not proof of unrestricted
privileges. No physical NIC, NBSR workload, performance, phase/readiness or actual
incremental overhead acceptance is claimed. Status: DIAGNOSTIC_PACKET_ACCOUNTING_ONLY.

The first orchestration attempt exited because the image's inherited sh entrypoint
received incorrect arguments. Its command logs/source/controller remain retained;
no capture ran. A separate attempt used an explicit entrypoint and completed all
three captures. The owned containers were stopped and only the newly created
temporary network removed. No source/evidence or unrelated Docker objects deleted.

This closes only an external wire-analysis building block. Capture lifecycle,
socket ownership, marker coverage, phases, equivalent work, offload/native-host
qualification and the complete paired matrix remain outstanding.
