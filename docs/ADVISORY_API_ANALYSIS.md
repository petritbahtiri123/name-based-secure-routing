# Manual advisory API analysis

This optional workflow analyzes a small, explicitly selected source slice. It
does not scan the entire project, certify security, run benchmarks, modify files,
open issues/PRs, or execute suggestions. Findings and path:line citations are
model output and require a human to verify them against the recorded source hashes.

## Safe default

Run locally with provisioned Python 3.13+ (no extra dependencies):

```sh
python -B scripts/ci/api_analysis.py --scope ci
```

The default performs **zero API calls**, reads only `docs/CI.md` and
`scripts/ci/check.py`, and writes a hash/size/line-count inventory into
`ci-results/api-analysis.json`, without copying source content. `--scope overview`
instead selects `README.md` and `docs/protocol/status.md`. Missing, binary,
oversized or linked files are rejected rather than silently omitted.

Live GitHub execution is manual-only. A development-branch push touching this
workflow, client or its tests runs a zero-API inventory bootstrap. It receives
no API key and cannot enter the live step. The workflow is five minutes,
contents:read, with SHA-pinned official actions and no persisted checkout token.
The dry-run default does not receive an API key. GitHub may require the workflow
file on the repository's default branch before exposing workflow_dispatch.
The dry-run push bootstrap attempts registration without changing main. Actual
manual dispatch must be verified after registration, not assumed. This change
does not merge to main or change the default branch to enable it.

## Live mode is a separate decision

### Windows local fallback

The GitHub UI currently does not expose manual dispatch on the development-only
workflow. A local PowerShell 7 runner avoids main/default-branch changes:

```powershell
pwsh -NoProfile -File scripts/ci/run_api_analysis.ps1 -Python C:\path\to\python.exe
```

This defaults to the same zero-API dry-run. After explicit owner approval, a
restricted NBSR-project key may be copied directly from the provider UI and
imported with `pwsh -NoProfile -File scripts/ci/import_api_key.ps1 -FromClipboard`.
The importer does not print the key, refuses to overwrite an existing credential,
and stores only Windows current-user DPAPI ciphertext at
`%LOCALAPPDATA%\NBSR\credentials\openai-api-key.dpapi`, outside the repository.
It clears the current clipboard, but cannot promise removal from OS clipboard
history, synchronized clipboards or managed-memory remnants. Review those
exposure risks before copying. No ACL or system-security settings are changed.

Only an explicitly requested `-Live` run decrypts that file. Supply `-Model`,
`-InputRate`, `-OutputRate` and `-MaxUsd` after separately approving the selected
source transfer and spending scope. The key is passed only in the child process
environment, never a command argument or plaintext file. Other processes running
as the same Windows user or an administrator may still access decrypted process
memory; DPAPI does not protect a compromised login. The runner removes its key
reference and child environment entry, suppresses child diagnostics, and enforces
a 90-second process-tree deadline. It neither retries nor creates credentials.
Live mode also requires an absolute trusted Python executable path and reviewed
`-ExpectedPythonSha256` / `-ExpectedClientSha256` pins. Pin mismatch rejects before
decryption. Python runs with `-I` to ignore inherited Python paths and user-site
customizations. Every exceptional path attempts bounded owned-child cleanup;
an incomplete-cleanup warning requires manual resolution before any retry.

Synthetic DPAPI roundtrip tests run on Windows in `tests/ci`; no real key is used.
Linux checks the static runner contract and skips the Windows-only roundtrip.

No key or paid call is provisioned by this change. Before an operator explicitly
selects live mode, review **the exact selected files on the selected commit** for
private content, approve sending them to OpenAI, and configure:

- A project-scoped `OPENAI_API_KEY` through GitHub Secrets, never source or chat.
- `NBSR_ANALYSIS_MODEL`: an explicitly chosen supported model identifier.
- `NBSR_INPUT_RATE` and `NBSR_OUTPUT_RATE`: current USD per million token prices
  for that model. They must be finite and positive.
- `NBSR_MAX_USD`: a positive per-invocation planning budget, at most 1 USD.

No prices or model are guessed. Missing configuration fails before any request.
Input is capped at 96 KiB and output at 2,000 tokens. Preflight uses serialized
request bytes plus a 1,024-unit margin as a conservative input allowance. This
is **not a provider-enforced dollar cap**, nor proof of exact tokenization.
Stale prices, a wrongly priced model, transport overhead and repeated manual
runs can invalidate a financial estimate. Set and verify independent provider
project controls; do not assume a dashboard budget is necessarily a hard stop.

The client makes at most one request to `https://api.openai.com/v1/responses`,
with no redirects, retries, model tools, remote URL inputs or previous responses.
Socket timeout is 60 seconds; the workflow's five-minute deadline is the outer
bound. A failed/timed-out call can still incur cost. Never automatically rerun it.
`store=false` disables response storage for retrieval; it does not promise zero
retention under all provider policies. The model cannot inspect omitted files.

Credential-pattern rejection is only defense in depth, not a complete secret
scanner or anonymizer. Source comments are treated as untrusted input, but prompt
injection can still corrupt the advisory answer. Nothing consumes the answer as
commands, permissions, evidence of real benchmark success or an approval.

Live artifacts may quote selected source. They are unverified advisory output,
not sanitized CI status records. Artifact access follows the repository/run's
access policy and retention is one day. Do not publish artifacts containing
confidential source to a public repository. Error bodies and API keys are never
logged. No raw prompt is saved in the report.

## Verification before publication

`tests/ci/test_api_analysis.py` is collected by the existing `python-core` profile
through its `tests/ci` entry. Tests use synthetic files and fake HTTP only. Check
collection, execute the tests, run Ruff on both new Python files and run
`python scripts/ci/check.py validate`. Actual API behavior, billing and GitHub
manual dispatch remain untested until separately authorized. The official API
schema reference is https://developers.openai.com/api/reference/resources/responses/methods/create.
