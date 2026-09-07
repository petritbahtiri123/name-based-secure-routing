# B3 held-bundle idle expiry: diagnosis and logging repair

Status: diagnostic defect FIXED; dominant 1024-bundle failure ATTRIBUTED.
This is not a 1024-bundle PASS or a production capacity claim.

Start: `0e4b5cf683e21b87c116f5fdd912263f1043e642`.
Changes: `f732ac94` extends failure-only close diagnostics to held bundles;
`befccf5f` buffers each diagnostic before a single write. Both changes are in
the benchmark binary. Production transport, policy, wire and security are
unchanged. Source/destination idle settings remain 30/10 seconds; launch rate
remains 100/s; active hold, release, ACK and cleanup gates are unchanged.

## Measured results at befccf5f

| Cell | Repeats | Result |
| --- | --- | --- |
| 512 bundles | 3 | All valid, final ownership zero; source/destination active private-resident CV 1.248% / 0.563% |
| 1024 attempt A | 1 | 781 successful application rows, 243 failures: 238 idle expiry, 5 other closed |
| 1024 attempt B | 1 | 778 successful application rows, 246 failures: 240 idle expiry, 6 other closed |
| 1024 attempt C | 1 | 782 successful application rows, 242 failures: 235 idle expiry, 7 other closed |

The three independent 1024 attempts have identical workload/source and each
retain one outcome for every client ID. They remain diagnostic failures, not
valid capacity cells. Every failed client has exactly one complete close
diagnostic: 731 total, zero malformed lines. All 713 `timed_out` clients held
for 10.0048–12.3553 seconds between ready and release. The 18 `other_closed`
cases remain unattributed; do not claim the same cause for each of them.

## Attribution

The pinned `quinn-proto 0.11.16` source maps `Timer::Idle` to
`ConnectionError::TimedOut`; the error explicitly means negotiated idle
expiry. Negotiation takes the smaller nonzero idle limit, here 10 seconds.
The local source was compared byte-for-byte with its crate archive, whose
SHA-256 matches Cargo.lock:
`2f4bfc015262b9df63c8845072ce59068853ff5872180c2ce2f13038b970e560`.
Relevant excerpts and source hash are retained in `quinn-idle-attribution.json`.

Thus idle expiry is MEASURED for those 713 connections, rather than inferred
from a generic timeout string. Holding early admitted connections while
scheduling 1024 clients at 100/s (10.23-second launch span), then completing
the active sampling interval, exceeds the negotiated idle lifetime. The
controller's later ACK-file timeout is a downstream symptom. This is not an
NBSR wire-ACK bottleneck or a measured host/hardware ceiling.

The historical d0792699 failure did not retain close reasons. These new
repeats support the hold/idle explanation but do not retroactively prove the
cause of every connection in that historical attempt.

## What was repaired, and what was not

Initial f732ac94 diagnostics exposed interleaving between multi-part formatted
stderr output and sibling panic output. That cohort's 512 control failed, and
its three 1024 attempts contained 14/16/13 malformed diagnostic lines. All are
retained. Some host fmt/clippy work overlapped that initial cohort; it is not
observer-qualified for timing or causal performance comparisons.

The buffered-write repair has a concrete RED/GREEN result: the same verifier
rejects the initial malformed output and accepts all three final attempts,
matching every failure ID to its diagnostic. The final 512 control also passes
three repeats. No build/test workload overlapped the final rerun; only light
status reads occurred. This establishes diagnostic completeness, not a formal
throughput observer bound or a new speedup.

Making this unchanged idle-hold workload pass at 1024 by increasing timeout,
adding keepalive, shortening the hold or changing launch rate would change
the tested condition. None was done. There is no demonstrated production bug
to optimize here. Report 512 as demonstrated scale, not maximum capacity.
A future larger-scale active-liveness workload must be explicitly defined and
reported separately; it must not silently replace this failed workload.

## Verification and evidence

- Release builds on Windows (scoped checks) and Linux (benchmark binaries).
- Transport close-category regression: PASS. Release source-binary clippy
  with `-D warnings`, fmt and verifier Ruff: PASS.
- Real diagnostic RED/GREEN and three replicated final failure checks: PASS.
- Three final 512 cleanup checks: PASS. No security semantics changed; no new
  full adversarial/security claim is made from these harness-only changes.

```powershell
python scripts/verify_b3_close_evidence.py C:/NBSR-build/linux-b3-close-befccf5f/failure-1024-a
python scripts/verify_b3_close_evidence.py C:/NBSR-build/linux-b3-close-befccf5f/failure-1024-b
python scripts/verify_b3_close_evidence.py C:/NBSR-build/linux-b3-close-befccf5f/failure-1024-c
```

Canonical: `evidence/performance/v2/b3-idle-attribution-befccf5f`.
`raw-evidence.json` binds five complete raw/build/test roots and their indexes.
The raw runner scripts, build manifests, failed attempts and source diff are
retained. No authoritative evidence was deleted. About 7.9 GB remained free;
no cleanup was required.

Remaining campaign work: memory-retention attribution and qualified long
soak; the existing deferred Administrator and external-server validations.
No need to repeat unchanged 1024 idle-hold failures merely to seek a PASS.
