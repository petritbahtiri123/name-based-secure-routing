# Linux September 8 requalification

Source 40b277fb, release Docker/WSL loopback with one selected guest CPU.
No verified host physical-core, dedicated server, WAN or unobserved-throughput
claim is made. The finite resource observer remains unqualified separately.

## Finite forwarding

The 16 KiB/eight-stream depth ladder has 22 valid records. NBSR depth one
classifies STABLE at median 3.235685 Gbit/s (three repeats, CV 0.766%); depths
two/four classify SATURATED at 3.155740/2.944799 Gbit/s. Direct depth one is
UNRESOLVED at 3.024711 Gbit/s because its latency dispersion does not meet the
stable rules; depths two/four are SATURATED. These are short finite results.

The 1 KiB/64-stream ladder has 26 valid records. NBSR depth one is UNRESOLVED
at 1.742994 Gbit/s, depth two DEGRADED at 2.140004 and depth four SATURATED at
2.025291. No strict-stable reference was obtained for that shape.

Raw commands, all records and classifier outputs:
C:/NBSR-build/linux-requalification-40b277fb/reference-16k8 and reference-1k64.

## Matched idle controls

Three materialized 1024-bundle idle controls use the same 40b277fb source and
binaries as the separately accepted active-keepalive workload. All three fail;
801, 811 and 609 source failures respectively have complete matching close
diagnostics, all timed_out (2,221 total). The accepted pinned Quinn attribution
identifies this as idle expiry. This strengthens the idle-workload explanation;
it does not turn those failures into passes or pool idle and active workloads.

## Admission observer failure

The admission ladder retained completed lower-rate cells, then failed at
100/s during /proc FD observation of an exiting child. B4_LINUX_EXIT_TRANSITION.md
records the measured error, minimal repair and RED/GREEN verification. This
failed source-stage is not a production admission limit; a post-fix rerun is
required. Raw: C:/NBSR-build/linux-requalification-40b277fb/admission-1core.

## Paced preflight

A separate reference-bound 16 KiB/eight-stream 70% NBSR ten-minute preflight
failed at 150 seconds on the unchanged live p99-drift gate. The first steady
window p99 was 1,273,873 ns; the last retained window was 1,639,991 ns, up about
28.7%. All five retained windows reported zero errors/timeouts. This is a
failed prefix, not a completed ten-minute soak; no higher stage was launched.
Raw: C:/NBSR-build/linux-b5-16k8-40b277fb. Near-ceiling sustained capacity remains
NOT_PROVEN, and the latency cause is unassigned.

## Larger active scale

At source 07096c08, the initial 2048 live-bundle attempt failed before all
active markers appeared: 601 source HandshakeTimeout outcomes and 601
destination HandshakeFailed messages. 4096 was not attempted. Cgroup peak
memory was 1,712,123,904 bytes, no OOM events/kills and no accumulated memory
pressure were recorded. These observations do not establish a CPU/network or
hardware ceiling. Raw: C:/NBSR-build/linux-b3-large-07096c08. Predeclared
1024/2048 follow-up diagnostics will compare before/after namespace network
counters; no buffer or transport optimization follows from this failure alone.
