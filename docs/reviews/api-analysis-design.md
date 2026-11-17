# Manual, bounded API analysis

Owner intent: start a read-only OpenAI analysis workflow, with cost controls and
no automatic modifications. The owner delegated conservative implementation
choices; no API key creation, live call or spend is authorized in this change.

Approach: a manually dispatched workflow, default dry-run, with an explicit small
source allowlist. Prefer this over every-push API calls (unrequested cost and
data transfer) or an agent with tools (unnecessary execution authority). This is
selected-file analysis, not a complete project audit. Output is an untrusted
advisory JSON artifact, never code, a shell command, a commit, or a PR comment.

Use standard-library Python and the fixed Responses API endpoint. One request,
no redirects/retries/tools, store=false, 2,000 output tokens, 96 KiB source cap,
five-minute job timeout. Live mode requires a separately configured key, model,
current per-million token rates, and positive per-run budget. The preflight
estimate uses a deliberately conservative byte-based token allowance, not a
provider-enforced dollar cap. Stale prices and repeated manual runs remain
operator responsibilities. Do not claim zero data retention from store=false.

Only enumerated public project documents/CI source are eligible. Reject binary,
symlink, outside-root, oversize and obvious credential content. These checks
are defense in depth, not a guarantee that arbitrary source is non-sensitive.
The operator must review the chosen files before live dispatch. Do not include
raw inputs in dry-run artifacts. Reports may quote source; restrict access and
retain for one day. Model citations are requested, not independently verified.

API reference checked 2026-11-17:
https://developers.openai.com/api/reference/resources/responses/methods/create

## Implementation plan
- Add offline rejection, manifest, budget, payload, response and workflow tests.
- Observe failure before implementation. Implement collector and fixed client.
- Add manual workflow with safe defaults and existing pinned official actions.
- Preserve generic workflow gates; any analysis artifact exception must be exact
  and independently tested. Keep tests in tests/ci, selected by python-core.
- Run scoped tests, collection, Ruff and validator, then independent review.
- No live invocation or secret setup. Publish only after review and parent coordination.
