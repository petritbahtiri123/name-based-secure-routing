# Bounded native capture and explicit representation limit

ba9e844a adds a standalone owned native capture coordinator with separate UDP
start/end markers, 120-second/two-GiB capture bounds, thirty-second offline
export, exact stop token, zero-loss inventory and retained failure/cleanup.
It launches no NBSR peer, sends no protocol ACK and changes no NIC/security policy.

The first actual fixed-work Direct attempt finishes both release peers but
capture accounting fails on a harness KeyError: the existing adapter stores
flows in udp-flows.json, not in its report. The whole attempt is INVALID_PARTIAL
and retained without replacement. c4a4cd08 fixes the join and adds read-only
pre/post validation of declared MTU and Ethernet type against sysfs.

Independent retrospective TShark export of that original capture contains
14512 workload packets; 10855 captured IPv4 lengths exceed the declared 1500
MTU, with a maximum 14548 bytes. These are captured representations, not proven
physical packet lengths. The original attempt lacks the later sysfs MTU check;
offload mechanism and physical-wire expansion are not causally established.
Do not increase the analyzer MTU, silently segment aggregates or call this a
zero-loss physical-wire result. This remains an external/offload qualification gap.

Literal implementation RED: nine missing-module failures. Integration repair
RED: one missing-flow-contract failure, then three interface-contract failures.
Final packet/readiness/cancellation/marker scope: 86 tests PASS; scoped Ruff PASS.
The ba9e844a locked release build reproduces the three retained Linux hashes.

Actual corrected c4a4cd08 CLI validation uses synthetic UDP on isolated Docker
namespaces: three normal 200-workload-packet captures pass with observed native
MTU 1500, zero loss and bracketing markers. SIGTERM, SIGINT, SIGHUP and wrong
stop-token controls produce sealed INVALID_PARTIAL outputs with no result.json.
All observed controller/dumpcap PID epochs are absent after each control.
This proves controller lifecycle/accounting mechanics, not a successful NBSR
wire cohort. It does not establish process/socket ownership of a QUIC flow,
physical NIC/offload behavior, phase separation or stable performance.

Original failed traces, peer results, build provenance, all seven controls and
negative logs remain authoritative raw evidence. No production optimization,
protocol change, timeout extension or security-policy modification occurred.
