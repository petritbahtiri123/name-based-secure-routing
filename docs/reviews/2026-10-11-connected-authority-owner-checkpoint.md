# Connected authority owner: incomplete checkpoint

The approved local implementation is **not complete or approved for authority use**.
Work remains uncommitted on `codex/nbsr-v3-wp0-wp1`, based on
`c7abbc4423a9ad05cea9cdf6678c231a34cafd59`. Exact source snapshots, hashes,
binary hash, commands and retained outcomes are in the adjacent JSON manifest
and `evidence/connector-registration-development/2026-10-11-connected-authority-checkpoint/`.

The new Rust integration-test target verifies native signed normal-v2 fixture
bytes and applies negative effects to an explicitly synthetic existing owner.
Trust is explicitly `SuppliedTestTrust`, not authenticated bootstrap provenance.
Only DENY_NEW_USE and TERMINATE_ACTIVE_USE are supported; termination starts a
retained cleanup ticket and cannot release ownership before exact confirmation.
The supported local proof horizon is empty-to-one or one-to-two leaves. This
does not establish the full acceptance matrix, live authority or production trust.
There is no positive admission/provider integration; registration-ready remains
false. Stage 3 stays partial, with 2/10 stages complete.

## Measured results and regression

- Six native tests passed, including 11 case comparisons with the Python oracle.
- 77 Python tests passed: the connected vector test and existing inclusion-v2 suite.
- Eleven retained vector cases passed exact regeneration checking.
- Ruff passed for the two new Python files; scoped Rust formatting and tracked
  diff whitespace checks passed. Existing line-ending and Rust unused/dead-code
  warnings remain. No Clippy or full-crate formatting claim is made.
- The initial missing-module RED outcomes are retained. An early generated bundle
  used controller class 7; the generator was corrected to class 14 and regenerated.
  This highlighted the still-open internal configuration-validation gap.
- The focused freshness RED reproduced acceptance one second after witness
  expiry. The fix retains the minimum record, authorization, selected signer/log/
  witness key and witness statement expiry in the opaque event. Exact-boundary
  acceptance and expiry-plus-one rejection preserve the owner as expected.
  Independent source review cleared this scoped fix; it did not approve the bridge.

The passing native binary predates formatting-only changes. Exact post-format
source snapshots and binary hash are both retained; do not identify this binary
by the base commit alone.

## Open review findings

1. Bind the signed target to an explicitly pinned owner dependency inventory.
   Exact Binding equality and matching service/operator alone do not prove
   applicability of the revocation target.
2. Validate bundle log/witness membership, thresholds and policy consistency
   against the supplied keys and policy. Pinning inconsistent input is insufficient.
3. Restore record-schema parity with Python, including terminal maximum expiry
   and valid reason codes, using correctly signed malformed-record regressions.
4. For identical R under a fresh E, retain E-to-R without reapplying the owner effect.

Also inspect whether the prior anchor's maximum-staleness deadline must survive
verification through application; only the current checkpoint is rechecked there.
This is a follow-up question, not a reproduced finding.

## Resource stop and continuation

The affected Rust neighbor command (`connector_control`, `connector_registration`,
`connector_signature`) aborted after 4.22 seconds under the RAM guard. Its exit,
logs and cleanup are retained. It did not establish neighbor success. No costly
retry was attempted. Disk remained above 10 GiB; the guard's end-of-run RAM reading
after termination was approximately 2.27 GiB, not the minimum sampled during build.
Every supervised direct child was reaped, and the subsequent process inspection
found no visible Cargo/rustc/connector test workers. This task created no sockets
or containers.

Resume with a regression for each open finding, then minimal fixes and another
independent review. Rerun affected neighbors only with adequate headroom. CI
selection is deferred until this incomplete slice is corrected. AGENTS guidance
was reviewed and unchanged: this adds no accepted workflow or authority contract.
No commits, pushes, downloads, new keys, ACL changes or runtime enablement occurred.
