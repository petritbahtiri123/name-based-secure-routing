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

The GitHub workflow is manual-only, development-branch-only, five minutes,
contents:read, with SHA-pinned official actions and no persisted checkout token.
The dry-run default does not receive an API key. GitHub may require the workflow
file on the repository's default branch before exposing workflow_dispatch.
This change does not merge to main or change the default branch to enable it.

## Live mode is a separate decision

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
