# NBSR Demo Lab — development preview

This local dashboard runs six fixed scenarios and provides an independent offline
receipt verifier. It does not control benchmarks or the external Performance Lab.
**Windows demo: locally tested, including Petrit's personal base-demo test.**
The evidence-path UI passed focused frontend/HTTP checks and local Windows live
allow + stale-authority regression checks. Forced idle-server disconnect QA
confirmed disabled actions and retained historical evidence. This is not a
verified operating-system/toolchain matrix.
Preview identifier: **Demo Lab preview 2026-11**. Use the exact commit URL
supplied with the preview; this is not a production release.

**Mac: PREPARED BUT UNTESTED. We do not know whether it works on a real Mac; compatibility is not confirmed.**

The approved Mac adapter runs the dashboard on macOS and the entire NBSR scenario
in a local Linux Docker container, labeled **Mac host / Linux container**. It
preserves the existing Linux verified-executable mechanism. Native macOS backend
execution remains unsupported. The adapter and image recipes are implemented but
have not been built/run on a Mac. Official image digest metadata is recorded;
image compatibility/assembly and Intel/Apple Silicon acceptance remain prerequisites. Cross-platform path
tests and fake Docker tests on Windows are not native Mac evidence.

## Prerequisites and transparent setup

Use a full checkout of `codex/nbsr-v3-wp0-wp1`. The check command does not restore
sparse files. Install Git, Python >=3.12,<3.15, Go >=1.26.5, and an edition-2024
compatible Rust toolchain explicitly. Python 3.12/3.13 have historical repository
coverage; this runner's component checks used Python 3.14.6 on Windows. This is not
a verified version matrix. Build tools also require MSVC/Windows SDK on Windows,
or Apple Command Line Tools on Mac. No global installer, elevation, execution-policy
change, trust-store change, or automatic toolchain download is performed.

Official installation sources: [Python](https://www.python.org/downloads/),
[Go](https://go.dev/dl/), [Rust](https://rust-lang.org/tools/install/),
[Windows native toolchain](https://rust-lang.github.io/rustup/installation/windows-msvc.html),
[Apple tools](https://developer.apple.com/documentation/xcode/installing-the-command-line-tools).
These are installation references, not a claim that their current latest versions
have passed this demo. Project Go modules and Cargo.lock remain the dependency pins.

## Obtain the reviewed source (Windows)

This preview is distributed on the development branch. Its exact version is the
Git commit SHA in the accompanying commit link, not the moving branch name.
Historical local receipts also include dirty-source and binary hashes; their base
HEAD alone does not identify the tested code. See [preview scope](PREVIEW.md).

From a chosen parent directory, after the preview commit is available:

```powershell
git clone --branch codex/nbsr-v3-wp0-wp1 https://github.com/petritbahtiri123/name-based-secure-routing.git
cd name-based-secure-routing
git rev-parse HEAD
git status --short
```

Compare HEAD with the exact approved SHA in the delivery note. If it differs or
there are unexpected local changes, stop and obtain the correct reviewed source;
do not build an arbitrary newer branch tip. The commit link is the version identifier.
The check expects this development branch and a full checkout.

Recorded Windows environment: Python 3.14.6, Go 1.26.5, rustc/Cargo 1.97.1,
MSVC 14.44.35207 and Windows SDK 10.0.26100.0. These are observed test versions,
not automatically installed tools or a guarantee for every permitted version.
A clean-machine setup has not been tested; no VM testing was performed.

From repository root on Windows:

```powershell
python tools/demo-lab/demo.py check
python tools/demo-lab/demo.py prepare
# Only if dependency downloads are wanted after reviewing the plan:
python tools/demo-lab/demo.py prepare --allow-downloads
python tools/demo-lab/demo.py build
python tools/demo-lab/demo.py serve
```

Equivalent wrappers are `scripts/demo/setup-demo.ps1 -Action check|prepare|build`
and `scripts/demo/start-demo-lab.ps1`. `-AllowDownloads` is valid only for prepare.
If local script execution policy blocks a wrapper, use the Python command; do not
bypass or change the policy.

On Mac, install Python, Git and Docker Desktop explicitly; host Go/Rust and Apple
compiler tools are not needed for the container execution path. Start with
`python3 tools/demo-lab/demo.py check` or `sh scripts/demo/setup-demo.sh --check`.
Follow [reviewed image preparation](container/README.md) before selecting an image:

```text
python3 tools/demo-lab/demo.py configure-image --image-id sha256:<reviewed-local-image-id>
python3 tools/demo-lab/demo.py serve
```

The `sha256:` value is a required real 64-hex image identity, not the placeholder.
The launcher rejects Rosetta-translated Python rather than labeling emulated
execution native; detection follows Apple's `sysctl.proc_translated` mechanism
([Apple documentation](https://developer.apple.com/documentation/apple-silicon/about-the-rosetta-translation-environment)).
Its OS query still requires native Mac acceptance testing.
Configuration does not pull or run anything and does not certify the image.
`sh scripts/demo/start-demo-lab.sh` also opens the browser. Mac `prepare`/`build`
refer callers to the container workflow; they do not build host Go/Rust binaries.
The current image recipe still needs compatibility checks and supervised image-build
orchestration before it is a turnkey Mac setup. No native acceptance is claimed.

`prepare` without its explicit flag prints a plan. With the flag it downloads
locked Go/Cargo dependencies into tool caches, using temporary source mirrors so
the working manifests are not rewritten. It does not install OS toolchains.
`build` is offline, uses at most two jobs, retains stage logs and rejects missing
caches. Each subprocess stage has a 95-second work deadline with owned cleanup.
Do not silently extend a failed stage. Each stage requires 8 GiB free, aborting
below 6 GiB or after 2 GiB growth. A cold build may exceed these limits and fail;
that is an incomplete preparation, never a successful demo.

Build artifacts and receipts live under `tools/demo-lab/.state`, ignored by Git.
Live runs also create fresh private fixtures under
`client/nbsr-go-client/demo/test-results/nbsr-demo/runtime/<run-id>` and binaries
under `C:\NBSR-build\nbsr-demo\<run-id>` on Windows. Keep credentials and raw
private runtime files local. The browser session token is one-use bootstrapped
through a URL fragment and remains in memory; do not share its URL.

## Presenter playbook / Playbook për prezantim

1. **Përgatitja:** ndalni benchmark-et dhe collector-ët; konfirmoni pronësinë dhe
   pastrimin e punëve të mëparshme. Kryeni `check`, përgatitjen dhe build-in. Mos
   filloni prezantimin nëse njëra dështon. Hapni `serve`; browser-i hapet vetë.
2. **Shpjegimi:** "Po demonstrojmë sjellje lokale me fixture. Nuk po provojmë
   kapacitet, WAN, multi-host ose gatishmëri për prodhim." Në Mac tregoni qartë
   "Mac host / Linux container"; backend-i nuk është native Mac. Shpjegoni dallimin
   ndërmjet `LIVE_ATTEMPT`, `REGRESSION` dhe evidencës historike.
3. **Service A allowed, Windows:** nisni skenarin. Rruga Go/Rust duhet të prodhojë
   payload-in `hello from service-a through NBSR`, rezultatin e destination
   `status=PASS`, `backend_requests=1`, exit code 0 dhe pastrim `CLEAN`.
   CONNECT HTTP 200 vetëm nuk dëshmon autorizim. Nëse mungon ndonjë provë,
   rezultati nuk pranohet si PASS.
4. **Rastet negative:** nisni një nga një unknown service, stale authority,
   service digest mismatch dhe expired Mapping. Këto ekzekutojnë testet reale të
   regresionit me fixture/mock; nuk janë sulme live ndaj infrastrukturës.
   PASS do të thotë se refuzimi i pritur u vërtetua nga testi i emërtuar.
5. **Izolimi:** shared-IP regression kontrollon lidhjen e shërbimit për adresa
   sintetike të përbashkëta. Nuk është rezultat performance.
6. **Verifikimi i pavarur:** kopjoni komandën nga dashboard-i dhe ekzekutojeni në
   terminal nga repo root, p.sh. `python tools/demo-lab/demo.py verify --run-id
   demo-<32-hex>`. Verifikuesi lexon receipt-in dhe hash-et e artefakteve, pa
   dashboard, server apo rrjet. Exit code 0 kërkon PASS dhe CLEAN. Ai provon
   konsistencën lokale, jo nënshkrim/attestation nga palë e tretë.
7. **Mbyllja:** përdorni Stop Demo Lab. Cancel ndalon punën e zotëruar. Mbyllja e
   tab-it nuk është cancel; deadline i supervisor-it mbetet aktiv. Ruani edhe
   dështimet. Në `UNCONFIRMED` mos fshini lock-et e mos provoni përsëri pa
   verifikuar identitetet e proceseve dhe pastrimin.

## Exact scenario sources

| Scenario | Evidence type | Source assertion |
| --- | --- | --- |
| allowed_service_a | live attempt | Go demo client + `crates/nbsr-transport/src/bin/wp8_interop_server.rs`; body and backend count |
| unknown_service | fixture regression | `demo/internal/client`: `TestTask6UnknownServiceDeniedBeforeSecureRoute` |
| stale_authority | fixture regression | `demo/internal/client`: `TestTask6AuthorityDeniedBeforeTransportOrApplication` |
| digest_mismatch | fixture regression | `demo/internal/client`: `TestTask6ServiceDigestMismatchBeforeTransportOrApplication` |
| expired_mapping | fixture regression | `internal/corestate`: `TestMappingExactExpiryCannotBeReturnedOrAcquired` |
| shared_ip_isolation | fixture regression | `internal/resolution`: `TestSharedSyntheticIPCorrelatesSamePortServicesEndToEnd` |

Go paths are relative to `client/nbsr-go-client`. Build precompiles the exact
packages; execution uses anchored test names, disables test caching, and rejects
skipped/missing tests. Receipts retain source hashes, toolchain, platform and binary
hashes; a commit alone does not identify an uncommitted build. A build manifest
change during the run fails verification.

Historical Task7 documentation under `docs/demo/nbsr-end-to-end-demo*.md` records
source `19f6468f77175adcb7ad410c2016aa889b964dc0`, run
`task7-final-20260828-a`. The original `scripts/demo/verify-nbsr-demo.py` and its
historical source pins are unchanged. Historical success does not certify this
new launcher or current source. See also `docs/protocol/status.md` for scope.

## Safety, tests and remaining acceptance

The API binds only 127.0.0.1, requires exact Host/Origin for actions, rejects
arbitrary commands/paths, and exposes fixed scenarios. Windows children are
assigned suspended to an owned Job. The Mac adapter pins a local Unix Docker
socket, rejects remote contexts, runs only a reviewed local image without pulls,
and owns an exact container ID through a detached deadline helper. Host lifecycle
controls are disjoint from writable container artifacts. Container work is bounded
to 70 seconds, reserving cleanup within a total 119-second adapter budget; Docker
CLI termination alone never counts as container cleanup. Process groups used for
host CLI helpers are not equivalent containment against hostile descendants.
This is a trusted local development
tool, not a hostile-code sandbox. The standard-library HTTP server avoids a new
runtime Python dependency chain. No public deployment is supported.

Run component tests with an existing pytest installation:

```text
python -m pytest -q -p no:cacheprovider tools/demo-lab/tests
```

The HTTP test uses real loopback sockets with a fake coordinator; sandbox socket
restrictions can block it. It does not execute NBSR. The Windows integration build, base live/regression runs, cancellation/restart
and personal base-demo test have recorded local evidence. Updated package review,
clean-machine recipient setup, verified container image preparation and native
Mac Intel/Apple Silicon host coverage remain outstanding.
Do not present this preview as ready for Credo before those applicable gates.
Container receipts use schema v2 with host/runtime, native architecture pairing,
image ID and container ID. Schema v1 remains accepted for Windows receipts. Missing
inner evidence produces a separate attempt record; it can never verify as PASS.

## Evidence path and disconnected sessions

The diagram explains the current run's evidence, not timed per-hop telemetry.
Only PASS + scenario PASS + CLEAN + no verification errors highlights assertions.
LIVE RESULT shows the exact application body/destination backend count; its
authority and transport hops are schematic, not individually measured. FIXTURE
ASSERTION shows the exact named test's rejection/isolation boundary and source.
Running, failed and cancelled attempts show expected paths as unverified.

After connection loss all remote actions are disabled, the last result is labeled
historical, and POST is never automatically retried. A 15-second HTTP timeout
means the request's execution status is unknown, not that the run was cancelled.
Reconcile the recorded UI PID and active run before launching a fresh session;
never delete locks blindly. Keep the launch terminal open. Normal session lifetime
is at most one hour (15 minutes without authenticated requests when idle).
Clipboard failure displays manual-copy guidance; it does not affect verification.

Frontend regression checks use an already installed Node.js (development only):
`node tools/demo-lab/tests/test_ui.cjs tools/demo-lab/static/app.js`.
No npm install is needed; production/demo runtime remains Python plus compiled
Go/Rust artifacts. Native Mac acceptance and image assembly remain pending.

## What prerequisite checks do and do not establish

Windows `check` inspects the installed x64 MSVC compiler, linker, runtime header
and library, and matching Windows SDK headers/libraries. A missing inventory
blocks preliminary build admission. This read-only inventory does not compile or
link a program. `ready_for_build` means these preliminary checks passed, not that
build/run will succeed. It explicitly reports staging write access as NOT_PROBED.

Before compiling, Windows `build` creates the fixed `C:/NBSR-build/nbsr-demo`
parent if absent, creates one uniquely named private probe directory, writes and
reads a small marker, then deletes only that probe file/directory. Existing files
are untouched; the parent remains. Failure stops the build before compiler work.
This proves file access for the current user only, not executable-launch policy.
The live scenario still validates and stages its own executable hashes.

Dependency fetch is NOT a warm compile cache. `prepare --allow-downloads` downloads
locked source dependencies; a first Rust release build can exceed the unchanged
95-second work limit and fail. The developer's cold attempt did fail and later
explicit attempts reused partial compilation safely. Do not call the first failed
attempt successful or silently extend limits. Preserve logs, verify owned cleanup
and disk budget, then review any explicit retry. Setup on a fresh recipient machine
is not yet verified, so this is not promised as a one-command guaranteed install.

On Mac `check` reports host prerequisites separately and keeps ready_for_build
false: image preparation/assembly is not turnkey and native acceptance is missing.
See container/README.md. Mac functionality remains UNKNOWN until real testing.
