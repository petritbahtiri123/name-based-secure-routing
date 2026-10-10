# Published authority baseline: hosted CI failure

User authorization covered publication through exactly
`d4ca54eb438df3a9f5ff1c7259059382bdf50ba0` to
`origin/codex/nbsr-v3-wp0-wp1`, using the existing update/signature bypass.
The non-force push advanced `8e548588c6ff636bb7a29a8202adb9a37e5110c1` through
four approved commits (`f6400959`, `99ac954e`, `8afe21f2`, `d4ca54eb`). GitHub
reported the protected-ref and four unsigned-commit violations as bypassed.
An independent `git ls-remote` afterward returned the exact approved SHA.
No branch rules, main branch, signing configuration, or extra commits changed.

## Terminal hosted results

| Workflow | Run | Status | Jobs created |
| --- | --- | --- | ---: |
| CI | [38052988121](https://github.com/petritbahtiri123/name-based-secure-routing/actions/runs/38052988121) | completed / failure | 0 |
| Extended | [38052988879](https://github.com/petritbahtiri123/name-based-secure-routing/actions/runs/38052988879) | completed / failure | 0 |

Both runs identify exact head SHA `d4ca54eb`; attempt 1, push event, at
12:43:08/09 UTC on 2026-10-10. GitHub's jobs APIs returned empty job lists and
the commit check-runs API returned zero checks. The seven intended CI instances
(Python Ubuntu/Windows, Rust Ubuntu/Windows, Go Ubuntu/Windows, Node/policy
Ubuntu) **never started**. No hosted tests passed. The extended workflow's push
record is an invalid-workflow failure, not execution of its manual suite.

The run-page annotations reject `runner.temp` in job-level `env`: CI lines
100, 179 and 263; extended line 84. GitHub resolves that field before a runner
exists. Its [context availability reference](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability)
permits runner context at step level but not job environment level. This is a
workflow validation failure, not a language-test, packet-evidence, or transport
failure. Existing local JSON/security checks had not detected this schema error.

## Prepared local correction, not published

Both workflow files now initialize the four affected cache/build path variables
in an early PowerShell step through `GITHUB_ENV`, expanding `RUNNER_TEMP` at run
time. Checkout remains first. Existing destinations, pinned dependencies,
permissions, events, cache conditions and job limits are preserved. A targeted
validator check rejects runner expressions in job environment and four focused
regressions cover the rejected locations. It is not a complete GitHub schema
validator. No ACK source or pinned authority file changed.

Measured local checks:

- Literal RED: 4 expected failures before the validator change, 0.78 s.
- First full CI group: 15 passed / 1 failed, 2.95 s. The existing timeout test
  returned cleanup code 125 under sandbox process restrictions, not expected 124.
- Justified bounded retry with process-tree permissions: **16 passed**, 2.61 s;
  supervisor 3.62 s, no resource abort, direct child reaped.
- Ruff, workflow contract validation and whitespace checks passed.
- Executed all four exact workflow initializer snippets locally; each wrote
  the expected environment value with spaces in the temporary path.

Independent review found no blocking issue in this correction and confirmed the
scope preservation. Reviewer did not execute tests. All attempts and source
hashes are retained in the adjacent JSON. No additional commit or push was made.
The correction needs separate publication authorization and a fresh hosted run;
these local results do not change either failed hosted result. ACK work remains
deferred until the hosted baseline is established.
