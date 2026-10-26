---
name: nbsr-benchmark-triage
description: Use when diagnosing an NBSR benchmark shortfall, unissued requests, or suspected benchmark packet loss. Do not activate for unrelated documentation edits or general connectivity work without a benchmark claim.
---

# NBSR benchmark triage

Localize the first evidenced shortfall before proposing a change. Application
request accounting is not packet-loss accounting.

## Establish the evidence boundary

Use [HANDOFF.md](../../../docs/agents/HANDOFF.md) for verified checkout, ownership
and provenance. Read only the relevant benchmark requirements in
[AREA_GUIDANCE.md](../../../docs/agents/AREA_GUIDANCE.md) and its linked methodology;
root [AGENTS.md](../../../AGENTS.md) supplies current authority and resource caps.
This skill grants no additional execution authority.

Identify exact source commit plus dirty source/patch identity, build/binary hash,
configuration, endpoint roles, run ID, workload units and observation boundaries.
Record warmup, measurement and drain separately, including clock origin and
coverage. Different source/configurations or unmatched windows cannot be silently
pooled. Missing identity or counters stay unknown.

Inspect existing manifest/index, summary and selected logs first. Preserve failed
attempts and original evidence. Use the smallest retained artifact that can settle
the uncertainty; do not bulk-load archives or unrelated session history.

## Reconcile one comparable cohort

| Stage | Required distinction |
| --- | --- |
| Planned admission slots | Intended request opportunities, not packets sent |
| Issued requests | Defined issuance event; retries/attempts must not inflate unique requests |
| Transport evidence | Packet/byte/ACK/retransmission observations with their own units, endpoints and coverage |
| Unique completions | Deduplicated request identities from the same issued cohort, with drain status |

Only for comparable, complete counts: unissued = planned - issued; completion
deficit = issued - unique completions after the stated drain. Negative results
signal inconsistent definitions or coverage, not useful loss estimates. A deficit
before drain can include in-flight work. Final missing completions do not by
themselves locate a network fault. Successful application delivery can coexist
with packet loss recovered by transport. Missing counters are not zero.

Laptop-to-SPHERE SSH failure concerns the management path. It does not establish
failure on the inter-VM benchmark dataplane; compare each path's own evidence.

## Choose one next check

Report the justified counts, provenance/window gaps, first evidenced divergence,
and the cheapest single discriminating check. State what each possible result
would distinguish. Prefer an existing-artifact read; if a new run or probe is
necessary, specify its scope, required authority, caps and stop condition first.
Do not automatically benchmark, tune transport, enable BPF, access VMs or change
network/security settings. Unknown cleanup ownership or denied access remains a
blocker for dependent actions, not a reason to bypass controls.

## Interpretation examples

- Same cohort: 10,000 planned, 4,000 issued, 4,000 unique completions after drain
  means 6,000 unissued and zero observed completion deficit; underlying packet
  loss remains unproven.
- Missing issued counter: unissued and issued-to-completed deficit are unknown.
- Unmatched runs/windows or warmup populations: incomparable; no derived ratio.
- README spelling-only request: do not activate this workflow.
