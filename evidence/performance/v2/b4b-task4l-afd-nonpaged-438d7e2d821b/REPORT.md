# Task 4l AFD nonpaged-memory correction

MEASURED: GUID-only AFD preflight failed with WPR error 0xc5580612 in both preserved runs 150050 and 150200. Neither started benchmark controls. Changing the identifier alone did not resolve capture startup.

The profile lacked NonPagedMemory=true. Microsoft requires this for kernel providers and explicitly uses it for Winsock-AFD in its MsQuic profile:
- https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/capture-and-view-tracelogging-data
- https://github.com/microsoft/msquic/blob/main/src/manifest/MsQuic.wprp

Only the nonpaged-memory attribute changed. Literal RED: missing attribute assertion failed (1 failed, 3 passed). GREEN: 9 focused tests passed; Ruff passed. A focused independent review found no Important issues.

MEASURED: elevated preflight in external run C:/NBSR-build/b4b-task4l-etw-20260905-150353 then passed, capturing socket-create (1000) and bind (1030) events. Its copied profile and completed preflight trace/log/JSON are bound by external-inputs.json. The user launched this run before the correction commit; the copied profile hash is the exact configuration authority. Benchmark controls were running at this checkpoint. This is capture-startup evidence, not a capacity result or handshake bottleneck attribution.

Both failed runs remain intact. No production code, workload semantics, event selection, protocol, security, main branch or remote state changed.
