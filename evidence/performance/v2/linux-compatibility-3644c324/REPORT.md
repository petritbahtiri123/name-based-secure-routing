# Linux Docker VM compatibility control

**PASS_LOOPBACK_CONTROL** at exact committed source
`3644c324a535586e89af72a8c9796e8d58fadf48`. The release image built successfully;
six finite loopback repeats completed with zero binary validation errors and
successful process exits. This establishes Docker Desktop Linux VM software
compatibility for the recorded workload. External-server validation, a hardware
ceiling, strict stable capacity, and a stable NBSR speedup are **NOT_ESTABLISHED**.

| Path | Valid repeats | Median application Gbps | Repeat CV |
|---|---:|---:|---:|
| Direct | 3 | 1.599190 | 0.826729% |
| NBSR | 3 | 1.936772 | 2.114374% |

These are descriptive finite-run outcomes, not an optimization comparison.
Both paths used 1 KiB payloads, 64 streams, one outstanding request per stream,
three seconds of warmup, and twenty seconds of measurement. The runner selected
guest CPU 0 for both processes. The container had a one-CPU quota; guest topology
does not prove bare-metal physical-core placement. CPU accounting covers whole
process lifetime, including setup, warmup and drain; steady CPU ns/op remains
unmeasured. The original runner's `repeatable` flag is a repeat-CV result, not a
strict offered-rate/backlog stability gate.

The prior attempt at `6227fd86` is retained as a rejected run: Direct completed
its workload, but final `/proc/<pid>/fd` enumeration failed on an unreaped zombie.
The committed fix keeps terminal FD count explicitly `null`, labelled
`UNAVAILABLE_ZOMBIE`, while preserving final CPU and identity checks. All twelve
terminal client/server samples in this successful rerun have the same PID/start
identity as their earlier samples, nondecreasing CPU counters, and zombie state.
The runner then validates process exit and completion-ACK order. This is process
lifecycle evidence, **not eleven-counter runtime ownership cleanup proof**.

The container retained numeric UID/GID 65532, a read-only image filesystem,
network mode `none`, all capabilities dropped, `no-new-privileges`, one CPU
quota, 1 GiB RAM, a 128-PID limit, and bounded noexec/nosuid/nodev temporary
storage. Only the explicitly named evidence volume was mounted; no host Docker
socket or host ports were exposed. `security-settings.json` projects the actual
retained Docker inspection, rather than inferring settings from command text.

All **91** entries in the outer raw index and **61** entries in the nested runner
index were freshly verified. These overlap and must not be added as distinct
artifact counts. The outer index's actual-byte SHA-256 is
`0c237495fb33ee0a53af7dc938eea046dbfa3dc47d71b750c3e8dcbca201e55e`.
The six rows, medians/CVs and twelve terminal samples were independently checked
from retained records and resource streams. `package.py` records that bounded
validation. Compact JSON here is normalized; original-byte provenance remains
in `external-inputs.json` and the copied raw checksum indexes.

Authoritative raw root:
`C:/NBSR-build/linux-smoke-preparation-3644c324`.
The prior failure remains at
`C:/NBSR-build/linux-smoke-preparation-6227fd86`.
Source bundle, image, binaries, raw resource streams, and full build logs remain
external; this package does not duplicate them or authorize their deletion.

To reproduce, use a fresh external recipe/run identity with the retained pinned
base digests and exact source commit, run `prepare.ps1`, then run `run.ps1` only
in a clear measurement slot. The original recipe paths and build command are
retained in the manifests and raw root. Do not overwrite either prior attempt.
