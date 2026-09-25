# Native2048 failure-only IPv4 UDP MIB diagnostic

MEASURED release8945c77a:3/3 pair trials FAIL_RETAINED. Same2048livebundles,
100offered/s,two source shards,sourceCPU0/destinationCPU2,private observerOFF,
existing1skeepalive and unchanged timeouts. Only diagnostic change: bounded
namespace MIB read after failure, inside owned PID epoch guards. Rust release
binary hashes unchanged. No production/security or wire change.

Trial1: source independently passes2048 recorded roundtrips and final eleven
ownership counters zero. Destination server report advertises2048 connections
but contains2029 samples; strict harness cardinality gate correctly REJECTS it.
Its legacy status:PASS field is not authoritative. Destination stderr retains
ApplicationStreamFailed panics and timed_out close diagnostics. Process exited
before failure capture; UDP/MIB and accepted destination final ownership remain
NOT_MEASURED. This is not a successful pair or admitted-capacity claim.

Trials2/3 fail before full active gate:2011/1505 materialized source observations,
2/34 HandshakeTimeout outcomes and0 completed source roundtrips. Both owned
groups cancelled/killed; final ownership unmeasured. Destination cumulative
live-socket drops1492/26 equal namespace InErrors and RcvbufErrors1492/26;
other recorded UDP error fields zero. Source measured socket drops and namespace
UDP errors zero. Linux reports receive-buffer errors in these snapshots; no
baseline/event timestamps/per-packet attribution, and no proof every timeout is
caused by drops. Prior zero-drop failed trial remains relevant. Buffer enlargement
is not justified as a sustainable-capacity fix by these counters alone.

All6ownedPIDs absent before container shutdown. CPU windows, all partial outcomes,
failed cleanup and raw close diagnostics preserved. Diagnostic guest/VM scope;
no physical host ceiling, production bottleneck, stable2048 or throughput claim.
Host checksum replay overlapped some runtime; no observer qualification.

Validation:8literalRED->16GREEN;33affectedtests/Ruff;actualLinux ownedUDP socket
smoke and PIDabsence PASS. Scoped code review clean. Evidence review required
independent check_peer replay for a passed role within failed pair:2RED->17GREEN,
Ruff PASS. Analyzer now checks exact source/config/binary/placement/epochs,
independent successful-role payload/ownership and every failed trial.

Replay: `python -B evidence/performance/v2/native-live2048-mib-8945c77a/analyze.py C:/NBSR-build/native-live2048-mib-8945c77a`.
Next isolated allocation diagnostic gives the existing two source shardsCPU0+4,
keeps destinationCPU2 and all workload/binary/timeout settings unchanged.
