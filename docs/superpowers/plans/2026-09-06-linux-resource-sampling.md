# Linux resource sampling implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Supply a bounded, fail-closed Linux process sampler for the existing benchmark controllers' later platform ports.

**Architecture:** Reuse the accepted Linux process/affinity reader and add explicitly named Linux private-resident memory plus sampler lifecycle enforcement. Keep this primitive separate from Windows sampling and from workload/transport code. Integrating B3, B4 and B5 is a subsequent bounded stage; this primitive alone does not establish full external validation readiness.

**Tech Stack:** Python standard library, Linux `/proc`, existing `linux_loopback.py`, pytest; restricted Docker compatibility control where available.

**Spec:** `docs/superpowers/plans/2026-08-30-funding-grade-benchmark-v2.md`, Task8, and `docs/benchmarks/EXTERNAL_LINUX_SERVER_VALIDATION.md`.

## Global Constraints

- Existing Windows behavior and source/transport/security semantics remain unchanged.
- Linux private-resident bytes are not Windows private commit; RSS is not a substitute for private memory. Keep huge-page accounting separately named.
- Sampling must preserve PID/start-time identity, observed per-thread affinity and unexpected-child rejection from the existing Linux reader.
- Missing/malformed live telemetry fails. A verified same-identity zombie may have unavailable memory/FD metrics; do not emit a false zero.
- No new dependency, privileged container, security-policy change, host/network modification, raw-memory dump or remote execution.
- Raw failed attempts and partial sample prefixes remain retained. No benchmark performance claim from sampler diagnostics.
- No routine approval gate: execute RED/GREEN, one focused review, evidence verification and atomic commit under the campaign authorization.

---

### Task1: Explicit Linux memory sample

**Files:**
- Create: `scripts/performance/linux_resources.py`
- Test: `tests/performance/test_linux_resources.py`
- Reuse without modification: `scripts/performance/linux_loopback.py::sample_process` and `parse_proc_stat`.

**Interfaces:**
- `parse_smaps_rollup(text: str) -> dict`: produces `rss_bytes`, `pss_bytes`, `private_resident_bytes`, `private_hugetlb_bytes` and `memory_basis="linux_smaps_rollup"`.
- `sample_linux_process(pid, cpus, *, proc_root=Path("/proc"), ticks=None, page_size=None) -> dict`: extends the existing sample with those metrics and `memory_state`. Preserve original CPU/identity/FD/thread/affinity fields. `memory_state` is `MEASURED` or `UNAVAILABLE_ZOMBIE`; unavailable memory values are None.

- [x] Step1: Add RED tests with a real-shaped smaps rollup fixture:

```python
def test_private_memory_is_not_rss():
    sample = parse_smaps_rollup("Rss: 100 kB\nPss: 80 kB\nPrivate_Clean: 20 kB\nPrivate_Dirty: 30 kB\nPrivate_Hugetlb: 4 kB\n")
    assert sample["rss_bytes"] == 102400
    assert sample["pss_bytes"] == 81920
    assert sample["private_resident_bytes"] == 51200
    assert sample["private_hugetlb_bytes"] == 4096
```

Also exercise missing/duplicate required fields, invalid units, negative values, same-PID start-time changes, live permission/read failure, known zombie, live-to-zombie race and preserved affinity/child rejection using synthetic proc trees.

- [x] Step2: Run `python -m pytest tests/performance/test_linux_resources.py -q` before implementation; retain missing-module/API RED.
- [x] Step3: Parse only named required fields as nonnegative integer kB, multiplying by1024. Unknown kernel metrics may be ignored, but required-field duplicates or malformed fields fail. Read process identity before and after memory access; only a verified unchanged zombie permits unavailable memory. Keep the original exception for live failures.

```python
private_resident_bytes = fields["Private_Clean"] + fields["Private_Dirty"]
private_hugetlb_bytes = fields["Private_Hugetlb"]
```

- [x] Step4: Run focused tests and Ruff. Confirm Windows importability of parser/synthetic-proc tests without calling Linux-only sysconf defaults.

### Task2: Bounded sampler lifecycle and compatibility evidence

**Files:**
- Extend: `scripts/performance/linux_resources.py`
- Extend: `tests/performance/test_linux_resources.py`
- Create: `docs/benchmarks/LINUX_RESOURCE_SAMPLING.md`

**Interfaces:**
- `LinuxResourceSampler(processes: dict[str,int], cpus, *, interval_seconds, max_records, record_sink=None, sample_fn=sample_linux_process)`.
- `start()`, `check_health(require_running=False)`, `stop() -> list[dict]`, `records_snapshot() -> list[dict]`.
- Every retained/sink record contains a role and the original sample fields, with explicit Linux memory names. No Windows handle/private aliases. Stop joins its owned thread with a fixed bounded wait; empty sampling, overflow, sink failure, identity change or lost live sampling raises. A failure retains already captured records through `records_snapshot()` and the original sink.

- [x] Step1: Add RED tests for start-once, positive finite interval, exact positive integer cap, nonempty valid PIDs/CPU set, prefix preservation on cap/sink failure, identity/CPU/time monotonicity, require-running health, no samples, and deterministic stop. Inject `sample_fn` for deterministic lifecycle tests.

```python
def test_invalid_bounds_fail():
    with pytest.raises(ValueError):
        LinuxResourceSampler({"source": 123}, [0], interval_seconds=1, max_records=0)
    with pytest.raises(ValueError):
        LinuxResourceSampler({"source": 123}, [0], interval_seconds=float("nan"), max_records=4)
```

- [x] Step2: Run the focused tests before adding the class and retain the second RED stage.
- [x] Step3: Use an owned thread plus Event, a copied process mapping, strict per-role PID/start-time and CPU/time continuity, a hard record count, and a latched exception. Invoke the sink only with captured records. Stop cannot silently convert a failed/empty sampler into successful evidence. A live controller must still call health checks while the workload is silent.
- [x] Step4: Run `python -m pytest tests/performance/test_linux_resources.py tests/performance/test_linux_sampler_zombie.py -q` and `python -m ruff check scripts/performance/linux_resources.py tests/performance/test_linux_resources.py`.
- [x] Step5: If the existing restricted Linux image is usable, stage only needed Python files outside the repository and run a same-UID owned-child diagnostic under network-none, read-only, cap-drop, no-new-privileges, bounded RAM/PIDs/CPU. Observe a real private-memory sample and final same-identity zombie; preserve failures and image/source hashes. Do not build a new image or claim external/physical-core performance.
- [x] Step6: Document units, unavailable states, proc permissions, sampler limits and caller obligations. Perform one focused review, verify raw/canonical checksums and staged diff, then commit explicit paths with `bench: add bounded Linux resource sampling`.

## Follow-on boundary

B3 needs executable-name/platform capture integration and Linux memory classification.
B4 needs host/thread/resource replacements without altering rate/shard semantics.
B5 needs Linux placement/ceiling identity, Linux-specific memory guards and the existing live drift/ownership/failure-tail enforcement. Those integrations are not claimed by this plan and must keep their own RED/GREEN/live validation stages. Dedicated external hardware and native two-host/NIC results remain unavailable.

## Completed verification

Reader missing-module RED retained; lifecycle missing-class RED retained (25 failed,18 passed).
Fresh focused pytest:49 PASS; Ruff PASS. Restricted same-UID Linux child/private-memory/zombie
control PASS with owned-process/container cleanup. Parent reviewed the three implementation
files and their immediate reader dependency: no Important/Critical findings. Canonical evidence:
`evidence/performance/v2/linux-resource-sampling-bf53b8d4/`. No controller integration or
external-server qualification is claimed. Explicit paths are committed together for atomic closure.
