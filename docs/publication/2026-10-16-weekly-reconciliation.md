# Weekly source, test and evidence reconciliation

This completes the source reconciliation begun in commit
`d1ac1116c2f0d4a033a919b407a248d81d79e243` on
`codex/nbsr-v3-wp0-wp1`. That commit's hosted CI passed in
[run 38976515130](https://github.com/petritbahtiri123/name-based-secure-routing/actions/runs/38976515130).
The earlier candidate manifest describes that first batch, not the final scope.
The accompanying weekly publication manifest binds this batch's exact Git blobs.

## Included fixes and verification

| Area | Implementation and evidence | Fresh validation |
| --- | --- | --- |
| Windows lifecycle and provisioning | `windows_native_management.py`, `windows_docker_provisioning.py`: bounded cell/cleanup budgets, bounded launch trace, Windows argv limit, preserved original failure, guarded cold-probe ceiling | 152 tests passed; one unchanged MSYS shell fixture failed under the sandbox and passed on the explicit host retry. These are separate runs, not a single green aggregate. |
| Offline Rust cache inspection | `rust_cache_metadata.py` and its tests; restricted metadata-only lockfile probe | Included in the Windows/cache suite above; no builds or downloads performed by the probe. |
| Composed KAR verification | Retained `connector-kar-genesis-positive.json`, Rust support cases, `check_connector_kar_positive.py`, CI registration | Checker: 4 positive and 18 rejection cases. Recovery/model/CI/key-authorization selection: 173 passed. No new signatures; fixture remains runtime unauthorized. |
| Recovery ownership | `inclusion_recovery_harness.py`, federation tests, connector replacement-permission cases | Included in the 173-pass selection. Tests cover disposal before restoration, stale tickets, retries and reentrant guard reset; no real process crash or durable-controller claim. |
| SPHERE support | 29 supplied Python candidates preserved with portable imports, synthetic infrastructure labels, explicit operation inputs and a guarded offline runner | 59 passed with process creation and sockets forbidden. See [task-2 mapping](task2-fixes/README.md) and its provenance/validation JSON. |
| Diagnostic support | Five active helpers and tests; all 111 supplied Python files represented by 108 deduplicated historical snapshots | 31 active tests passed; 15 additional archived fake-volume/mocked metadata cases passed during source review. Historical supervisors were not executed live. See [diagnostic mapping](diagnostic-fixes/README.md). |

The first batch separately recorded 320 focused tests. An early fixture-write race
produced one failure before the stable rerun; it remains documented. The second
batch's initial Windows invocation used the wrong working directory/temp setup
and produced 57 failures and 46 errors. Its corrected invocation and single
MSYS host retry are reported above; no historical failure is converted into a pass.

Fresh Rust compilation was not performed for this batch. Historical native KAR
evidence recorded 19 passes with a temporary `autobins=false` manifest, not an
unmodified full Cargo build. The production Cargo manifest is unchanged. Hosted
CI for this new commit must be assessed separately from the first batch's success.

## Source and exclusion accounting

`weekly-fix-provenance.json` maps the Windows and KAR/recovery source digests to
their integrated paths. `task2-fixes/provenance.json` accounts for 47 explicit
task-2 candidates: 29 source files and 18 summarized supporting documents.
`diagnostic-fixes/source-map.json` accounts for 168 top-level diagnostic artifacts
and all 111 Python source/dependency files, including nested plans.

`weekly-evidence/manifest.json` accounts for 2,304 original pending repository
entries: 927 already published, 146 published/historical baseline entries,
87 sanitized narratives, 68 historical source entries, 181 compact historical
outcomes, and 895 exclusions. Exclusions comprise 60 previously private entries,
5 local publication/privacy records, 177 raw patches/logs, 650 operational
inventories/duplicate details and 3 non-UTF-8 files. Unique originals remain local.
`weekly-evidence/repository-variants.json` additionally maps 19 dirty source
variants from the portable, KAR and runtime workspaces. Current implementations
remain authoritative; distinct older variants are retained as inert snapshots.

The twelve inspected repository statuses were reconciled: the original repository
and its local handoff evidence are mapped above; CI-clean residue contained raw
sampler logs; the CI-import regression is superseded by the stronger current
module-invocation test (the documentation command is corrected here); sparse and
clean runtime checkpoints supplied no additional dirty source; the publication
validation workspace's 389 differences were line-ending-only; Windows/cache and
KAR/recovery dirty fixes are integrated; remaining portable/runtime variants are
archived. Missing historical status paths were not reconstructed or represented
as recovered evidence. This is an inventory of the supplied workspaces, not a
claim to have recovered every file ever created during the week.

Historical snapshots are sanitized derivatives, not runnable release workflows.
Embedded historical pins remain unchanged; do not refresh them to make a snapshot
execute. Personal machine names, accounts and private addresses are replaced by
synthetic labels. Credentials, private keys, authentication files, raw operational
inventory and private infrastructure access data are excluded.

## Benchmark limits

Run07 is closed debug correctness evidence only: 55,896 operations over
20.00068049 seconds, one QUIC connection, two streams, 1,024-byte payloads and
depth one; zero integrity errors, successful endpoints and independently verified
cleanup. Both VMs shared one physical host. It is not a throughput baseline.
Harness revision `47d2ae41` and Rust source revision `b09a8518` are distinct.
No higher-load run, VM action, Docker cleanup or TLS signing was performed during
this publication. Future benchmark planning and execution remain separate.
