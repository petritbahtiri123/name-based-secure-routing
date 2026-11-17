# Latest development snapshot for weekly analysis

## Intended weekly scope and authorization

The owner requested all code, documentation and configuration, excluding evidence
and archives. The standing weekly limit is now $10 from existing credits,
including synthesis, with no recharge or spending beyond available balance.
That supersedes the earlier $0.10 two-CI-file weekly plan. The one-time broad
analysis remains pinned to 81257cc and must not be rewritten or silently reused.

The preparation helpers make zero OpenAI calls and read no credential. The
opt-in weekly worker can read a credential and send API requests only through
its separately gated live mode; preparing a snapshot does not launch that mode.
Development and verification of this change made zero OpenAI calls. The GitHub advisory workflow still has manual
and dry-run push triggers, not a weekly GitHub schedule. The separate weekly dot
automation must use fresh preparation before executing its approved workflow.

## Full-scope preparation

Run the reviewed helper with an existing NBSR Git object store:

```
python -I -B scripts/ci/prepare_api_full_snapshot.py --repo <existing-repository> --output-root <new-snapshot-parent> --cache-root <optional-verified-blob-cache>
```

Omit cache-root when no cache is needed. The helper resolves the exact remote
codex/nbsr-v3-wp0-wp1 ref once, then reads its immutable tree and blob identities.
It never reads working-tree source or substitutes local HEAD. Git reads disable
lazy fetch and prompts; no checkout, branch or remote is modified. Missing Git
objects are explicitly unavailable, not replaced by older files. A supplied
blob cache is accepted only when the bytes verify against the exact Git identity.

Every tracked path receives a manifest status. Only affirmative source/docs/config
categories are candidates. Nested evidence, archives, historical snapshots,
credential-like paths, obvious credential content and binary/non-UTF8 inputs are
excluded with reasons. Four PDF documents are currently unsupported as binary;
this is supported-text coverage, not a claim that every document format is read.
The known extensionless demo Python entrypoint is explicitly included.

Source reads are bounded to 1 MiB per file and 32 MiB total unique blob bytes; oversized
inputs fail rather than silently truncate. Git children have 30-second bounds.
Only screened source is copied to sources/<GitSHA>. snapshot.json records the
exact commit, file SHA256, UTF8-safe chunk ranges, all exclusions/unavailable
entries, preparation_complete and a source-set hash. It contains no source text.
The output commit directory is exclusive and never overwrites an old snapshot
or receipt. Partial output without a manifest requires inspection, not a live run.

If preparation_complete is false, stop and acquire the missing exact objects via
the approved source route. Do not run on a partial or old laptop snapshot. If it
is true, that means supported inputs are prepared, not that analysis occurred.
Compare the source-set hash with the last completed weekly receipt to avoid
paying again for identical inputs; record a skip honestly, not as a new analysis.

## Execution remains a separate gate

Build a NEW plan and ledger from this snapshot, bind requests to its commit and
source hashes, and verify the full-plan input plus capped output/synthesis cost
fits $10 AND the current account-wide remaining allowance. Refuse incomplete
preparation or an uncertain prior paid request. Do not inherit the one-time
$17.27 budget. Preserve failed/unknown/completed receipts and no automatic retries.
The existing credential wrapper and billing safeguards remain separate reviewed
components. This helper neither installs them nor changes their approvals.

## Limited freshness primitive

prepare_api_snapshot.py --resolve-only prints the current remote SHA without
source download or OpenAI calls. Its --output-root option prepares ONLY docs/CI.md
and scripts/ci/check.py with unchanged pinned legacy controls. That two-file
option is useful for limited checks but does NOT fulfill the full weekly scope.
It refuses stale fallback and overwrite too. Fetched source is never executed.

## Verification and current limits

All new tests are under tests/ci and already selected by python-core. They cover
remote ref pinning, no local fallback, wrong refs, category/secret exclusions,
Git object identities/bounds, missing inputs, exclusive output and no credentials
in Git child environments. Tests make no network or API calls. The combined
preparation/client/runner suite passed 71 cases with one Windows-only skip; Ruff
passed. Supported GitHub connector reads verified the latest 78f442e ref and CI
source hashes. Direct cloud HTTP was DNS-blocked and failed closed. A real local
Git inventory correctly reported its missing objects as incomplete; full Windows
object-store verification was then completed using an exact Git-identity bridge: the later ecf3a6b snapshot prepared 1,846 supported files with zero unavailable blobs. Exclusions remain explicit. The combined snapshot/planner/adapter/worker suite now collects and passes 83 cases, with Ruff passing. The mini adapter and separate Sol asynchronous execution are not interchangeable; no paid execution is part of this repository change.
