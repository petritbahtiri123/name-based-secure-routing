# Performance Lab automatic source checks

`.github/workflows/performance-lab.yml` adds a separate Ubuntu 24.04 job on pushes
to `codex/nbsr-v3-wp0-wp1`, pull requests, and manual dispatch. It preserves existing
project and Demo Lab jobs. Checkout is shallow and sparse to this package (plus
Git cone-mode root files), so repository evidence archives are not fetched into
the working tree. The workflow uses the repository's existing SHA-pinned
checkout/setup actions, Python 3.13.14 and Node 24.19.0. Hosted execution remains a
separate verification step; local contract checks do not prove a hosted pass.

The job runs from `tools/performance-lab`:

1. Install its existing `requirements-dev.txt` pins in the isolated job environment.
   Do not combine these with the root project's different FastAPI constraints.
   The direct Python dependencies are pinned; this is not a full transitive lock.
2. Install the existing npm lockfile with `npm ci --ignore-scripts --no-audit --no-fund`.
   Package lifecycle scripts are disabled; dependency versions/manifests are unchanged.
3. Run `python -B -m pytest -q -p no:cacheprovider tests`.
4. Run `node --experimental-strip-types --test tests/frontend.test.mjs`.
5. Run `npm run typecheck`, then `npm run build` as separate failure-reporting steps.
6. Check that both npm manifests and both requirements files remain unchanged.

The job has a 15-minute limit and each shell step has its own 1-5 minute limit.
Those hosted limits do not override the laptop's 120-second experiment/cleanup
budget. Permissions remain `contents: read`, checkout does not persist credentials,
and superseded runs are cancelled. No secrets, cache writes, deployment, or artifact
uploads are configured. Generated JavaScript and installed dependencies stay on
the disposable runner; they are not publication artifacts.

Tests create synthetic temporary fixtures. Some invoke a bounded regular-file
reader against those test-owned files; this is not an SSH connection or a live
source collector. No Uvicorn/QA server launcher, real data import, SPHERE command,
load generator, Go/Rust build, or benchmark is selected. Frontend tests check source
logic; a successful build is not browser acceptance, campaign validity, capacity,
Mac support, or production readiness.

For structural verification with an already provisioned environment, run from the
repository root:

```text
python -B -m pytest -q -p no:cacheprovider tests/ci/test_performance_lab_ci.py
python scripts/ci/check.py validate
```

These checks validate selection and the repository's workflow security contracts;
GitHub schema/execution and Linux dependency resolution still require a hosted run.
Local testing may use existing pinned packages/caches only. Do not install or
fetch dependencies locally merely because the hosted job installs them. Report
socket/filesystem permission failures separately; never weaken the application to
make restricted-environment tests pass.
