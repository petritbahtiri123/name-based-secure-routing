# Reader handoff race: offline correction candidate

The retained native receipts fixture06 failed closed. Its actual supervisor
reported a clean local worker exit, but settlement rejected the retained owner
binding: the supervisor had reaped handles while the lifecycle remained OPEN.
This is not a protocol performance result or a qualified campaign.

## Source and minimal change

`tests/performance/fixtures/reader_watchdog.py.snapshot` derives from the frozen
fixture04 `watchdog-source.py`, SHA-256
`4a60249bb041b001d4f2043196cc4553ac2925a05d13c6353df4be4e0438f175`.
Its only behavioral change is in `supervise`: successful empty-group observation
with an enabled closure handoff returns to the bounded loop before raw reap.
That loop repeats cancellation, resource guard and handoff proof. Failure paths
retain cleanup and invalidity. No handle state or capture proof is fabricated.
The snapshot is not an importable production launcher. Tests extract only the
actual function, with deterministic clock/owner and the real ReaderHandoff and
BoundReaderOwner. No native process, transport or capture correctness is claimed.

The regression failed before correction (three failures, two passes), then
passed. Cases cover the checkpoint-live/observe-exit interleaving, exactly one
capture/reap, late cancellation/resource failure, nonzero exit, and unchanged
no-handoff behavior. CI's reader-lifecycle command selects this file explicitly.

## Concrete integration still required

1. Preserve fixture04/05/06 and their hashes. A fresh execution-disabled fixture
   must copy this corrected snapshot as its own pinned watchdog source, rather
   than reuse or overwrite fixture04's old source. Account its exact additional
   bytes in the existing qualification reservation and manifest before admission.
2. Reuse the unchanged claim-bound producer, ReaderLauncher and native owner from
   fixture06. Bind the new source hash, fresh identity, request and immutable frame
   bytes. Test that the configured native harness extracts this corrected function
   and that the original retained snapshot still reproduces the regression.
3. Independently review the complete source-plan delta; recompute source,
   qualification, external and global accounting. Only after separate notice and
   authorization perform one bounded local native reader/receipt attempt. Success
   must include real handoff consumption, sealed receipts, independently verified
   acquisition/supervision agreement and empty owner trees within original bounds.
4. This does not repair the campaign by itself. The actual bounded wrapper,
   cross-process POST cancellation/receipts, receiver/SQLite writer accounting and
   campaign admission must be composed and qualified before workload activation.
   The existing visible dashboard remains 8765. No snapshot-only pass closes those
   gates, and the existing Linux watchdog without closure handoff is unchanged.

No full repository suite, native retry, SSH, network operation or publication was
performed for this candidate. Only the selected lifecycle suite and focused lint
were run under the existing 30-second process supervisor.
