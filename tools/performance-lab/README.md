# NBSR Performance Lab

Local, loopback-only inspection of retained evidence and passively delivered source snapshots. This source-only package starts empty. It contains no VM credentials, benchmark results, captured traffic, database, or bundled JavaScript.

## Install and start

Run from `tools/performance-lab` (not System32). Use a supported Python installation and Node.js 22.18+ with npm; the verified development environment used Python 3.14 on Windows. macOS has not been tested.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm ci --ignore-scripts
npm run build
python -m uvicorn lab.app:create_app --factory --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765. Keep this service on loopback: it has no user authentication. `start-lab.ps1` is an optional Windows hidden launcher after installation/build, using the selected Python environment. It creates local logs and a passive inbox; it does not launch a workload or SSH reader. On Unix-like systems activate the venv with `source .venv/bin/activate`, then use the foreground command above.

## Retained and live source evidence

Import reviewed JSON/NDJSON in the UI or with `python -m lab.cli PATH`. Supported schemas include controlled-load summaries, repeat summaries, and grouped progress/final records. Original bytes are retained by SHA-256; malformed supported data is quarantined. Missing counters remain unknown, not zero. Downloads verify the stored hash. Defaults are local `data/` and optional `inbox/`; override through `NBSR_LAB_DATA` and `NBSR_LAB_INBOX` before starting, not during an active run.

Summary and repeat latency values must satisfy p50 <= p95 <= p99 for the percentiles present. Contradictory values quarantine the artifact rather than display misleading latency; missing values remain unknown and equal percentiles are allowed. Existing imports are re-evaluated when explicitly re-imported under a newer adapter version; starting the app alone does not rebuild old normalized views.

Actual diagnostic source updates have been delivered and plotted in the development deployment. That does NOT mean every installation is connected. An independently supervised acquisition owner must choose the exact source/run identity, pin SSH host identity, preserve byte zero and origin records, and bound the reader lifetime. `lab.remote_reader` is a bounded read-only regular-file reader; `lab.bridge.PrefixBridge` accepts growing byte prefixes and publishes validated snapshots. Neither importing a module nor starting this web app establishes a remote connection. The deployment-specific supervisor and VM configuration are not included here.

See [bridge contract](docs/prefix-bridge-integration.md), [extractor](docs/local-extractor.md), [capture](docs/local-capture.md), and [snapshot format](docs/export-contract.json). Inbox observation is every five seconds and browser refresh every ten seconds; producer interval timestamps, not polling cadence, define metric windows. A separate reader has measurable resource overhead and must be disclosed and qualified before comparative performance claims.

## Qualification is separate

Source final, complete counters, and a graph do not establish whole-campaign validity, calibration, cleanup, or capacity. The exact historical fresh30 identity has an explicit UI owner-review overlay `INVALID_PARTIAL` because post-calibration validation failed; it does not alter raw evidence. Unknown campaign identities are unqualified, not accepted. This overlay is not a general authenticated acceptance service. No real fresh30 data is distributed in this package.

No causal speedup is claimed without matched, reproducible ABBA evidence. Source-relative clocks must not be aligned across hosts without evidence. Retained data must not be replayed as live updates.

Automatic source checks are described in [CI coverage](docs/ci.md); they use only
synthetic temporary inputs and do not run a benchmark or connect to SPHERE.

## Verify independently

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --experimental-strip-types --test tests/frontend.test.mjs
npm run build
```

Tests generate synthetic temporary fixtures; those are not benchmark results. Windows restricted sandboxes may block socketpair or hard-link operations required by tests. Use a supported local execution environment; do not weaken the production server. The QA fixture server is isolated and must never use real data.

## Packaging and license

Commit only source/config/tests and selected documentation. Exclude generated `static/app.js`, node_modules, caches, inbox, data, SQLite files, captures, logs, and verification artifacts. Build the frontend locally. This directory is intended under the repository's existing Apache-2.0 license; no new ownership claim is made. Dependency notices are in THIRD_PARTY_NOTICES.md.

### Repository dependency gate

The repository safety checker registers this isolated package's two npm manifests
and pins their normalized-text hashes together with both requirements files.
Dependency changes require an explicit review and updated pins/regressions; do not
remove the closed-inventory check. Generated node_modules is not publication source.
Run repository-wide inventory checks against a complete clean source checkout,
without generated dependency trees. Focused synthetic contract checks are:

```powershell
python -B -m pytest -q -p no:cacheprovider tests/federation/test_repository_safety.py -k "demo_ or performance_lab"
```

Run that command from the repository root. Sparse checkouts cannot establish the
complete repository inventory result.
