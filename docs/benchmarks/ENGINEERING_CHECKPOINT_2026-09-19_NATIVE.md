# September 19 native packet and reliability continuation

**MORE ENGINEERING REQUIRED. No final funding freeze or new stable ceiling.**

Subsequent bounded continuation at `11677eca` completes live socket-binding
validation: ten Direct/NBSR cells, twenty exact captured-endpoint/PID/start-epoch/
binary/FD joins and eighty rejected wrong-identity/port controls. Both peers run
without root. Ninety focused tests and the five-pair cohort gate pass. This closes
point-in-time local binding attribution for the tested 1 KiB/64-stream workload;
exclusive/continuous whole-flow ownership, phase separation and physical hardware
remain unproven. See [the observer runbook and evidence](EXTERNAL_NATIVE_SOCKET_OWNERSHIP.md).

The final bounded follow-up, checker `206244b6`, adds automatic observation-time
and retained-history validation. Ten negative fixture variants now reject; all
ten existing `11677eca` measurement cells and twenty peer histories revalidate
without rerunning or modifying raw evidence. See
[the source-separated reanalysis](../../evidence/performance/v2/socket-history-206244b6/summary.md).
The subsequent checker `b74bb2b5` closes the destination readiness-port join:
two previously accepted wrong-port fixtures now reject, and all ten original
destination endpoints revalidate read-only. No measurements are replaced or
relabeled. [Port-join evidence](../../evidence/performance/v2/socket-port-b74bb2b5/summary.md).
The next campaign step after the usage reset is packet-phase separation; admission
attribution, memory retention, qualified soak, deferred admin validation and
external physical-host work remain on the larger closure list.
Continuation starts at 7682846ecb1bbbadc382b8331af7c4072b531c6f. All changes
are on codex/nbsr-v3-wp0-wp1; protected main/origin-main remain
1938154d498b32d81a3564319969430644e8a688. No push or merge.

## Completed scoped engineering

- Strict bounded native Ethernet/IPv4/UDP pcapng accounting rejects capture
  loss, truncation, fragments, ambiguous endpoints, unsupported records and
  IP lengths beyond declared MTU. Three synthetic native captures reconcile
  exactly with independent TShark. Measured frame/IP/UDP bytes remain distinct
  from unproven physical-wire estimates.
- Native peers support equal fixed work without changing existing timed mode:
  1000 operations/stream, depth one, zero warmup. Twenty release cells form five
  Direct/NBSR pairs for each of two shapes. Peer/cohort checks pass; timing is
  diagnostic, including NBSR 16 KiB CV 10.411%. No stable capacity follows.
- Capture cleanup now kills/reaps an owned child after ignored interrupt and
  termination signals. A retained live RED and three live GREEN controls prove
  cleanup; forcibly closed capture remains invalid. Protocol timeouts unchanged.
- Separate UDP markers bracket retained traffic. Three live synthetic marker
  controls pass. The bounded native capture CLI passes three normal controls
  and four negative controls: SIGTERM, SIGINT, SIGHUP and wrong stop token.
- Integration failures are preserved: missing persisted-flow join, then
  oversized captured representations, then a partially published readiness
  JSON. The join and actual-interface MTU checks are repaired; readiness now
  uses atomic publication. Latest focused regression group: 68 tests PASS.
- Three controlled Direct on/off pairs isolate the UDP segmentation effect on
  private Docker veth capture representation. On-state aggregate IP lengths
  exceed MTU and are rejected; all off-state captures pass unchanged accounting.
  This is capture attribution, not the admission-handshake bottleneck or a
  physical NIC/production speedup. Scoped NET_ADMIN applies only to disposable
  private test containers; host networking/security policy remain unchanged.

All three Linux release binary hashes remain identical. No Rust/Go production,
cryptographic, wire, trust, dependency or mandatory-check optimization occurred.
Previous accepted security and private-origin results keep their original scope;
no full new-source adversarial recertification is asserted.

## Retained failures and remaining work

The db7edb19 diagnostic attempt retains its sixth-cell readiness failure. The
corrected ec255c18 attempt completes all six attribution cells, then three formal
cells before the fourth fails the unchanged five-GiB disk reserve. The formal
cohort is INVALID_PARTIAL, not a repeat-qualified Direct/NBSR result. Every raw
trace, error and complete unfavorable result remains in the checksum indexes.

After storage maintenance, a separately predeclared ec255c18 cohort completes
twenty of twenty release cells: five counterbalanced Direct/NBSR pairs per shape.
All peer/cohort gates, bracketing markers, zero-loss inventories and independent
TShark packet-count/IP-byte sums pass. Median incremental whole-flow IP bytes
divided by useful request/response bytes are +0.006705% for 1 KiB/64 streams
(range +0.003522% to +0.013945%) and -0.000544% for 16 KiB/eight streams
(range -0.019291% to +0.009332%). These are scoped captured-veth results including
setup, untimed validation, ACK and teardown; they are not pure protocol overhead,
physical wire cost or performance gains. Negative deltas do not prove compression.
See [all paired measurements](../../evidence/performance/v2/native-wire-ec255c18/paired-accounting.json).

Native phase separation and continuous/exclusive whole-flow ownership remain unproven.
Physical server/NIC validation is EXTERNAL_HARDWARE_REQUIRED. External admission,
memory and sustained-soak matrix porting still needs work. No qualified 60/120
minute near-ceiling soak, final current-source capacity or hardware ceiling is
established. The prior admission and timing uncertainty remains unchanged.

The existing single Administrator command remains in
[the deferred ledger](ADMIN_REQUIRED_FINAL_VALIDATION.md). The existing federation
manifest/trust-anchor incompatibility remains BLOCKED_ARCHITECTURAL and fail-closed;
live runtime federation is NOT_PROVEN. No destructive operation was required.

Earlier measured/historical scoreboard and security limitations are in the
[previous checkpoint](ENGINEERING_CHECKPOINT_2026-09-19.md). This continuation
must not be read as replacing those source-scoped measurements with new claims.

## Storage and reproducibility

Lossless NTFS compression of six retained ETLs and four decoded text traces
recovers 15,301,320,960 allocated bytes (14.25 GiB). Every original SHA-256,
logical length and path remains unchanged. Six stopped campaign containers
also release 2,691,866,624 disposable writable-layer bytes; no equivalent host
SSD recovery is asserted for that Docker cleanup. No source, authoritative
evidence, image, volume, Git work or unrelated user data was deleted.

The new formal campaign started only after compression/hash verification and
an eleven-GiB free-space check; its existing per-cell reserve remained unchanged.
Raw controllers, release provenance, complete packet captures, failed attempts,
per-cell offload state, peer outputs and checksums are retained. A native capture
cohort is still PARTIAL with respect to the full B1/external validation program.

No benchmark remains intentionally running at this checkpoint. The next bounded
native-wire tasks are phase separation and any further justified whole-flow attribution, followed by external
physical-host validation. Admission, memory retention and sustained-soak gaps
remain separate work; completing this cohort does not close the whole mission.

[Canonical evidence/checksum index](../../evidence/performance/v2/engineering-native-checkpoint-20260919/evidence-index.json),
[commit sequence](../../evidence/performance/v2/engineering-native-checkpoint-20260919/commit-sequence.txt), and
[scoped verification](../../evidence/performance/v2/engineering-native-checkpoint-20260919/verification.json).
The sequence ends before this checkpoint commit to avoid a self-referential hash.
