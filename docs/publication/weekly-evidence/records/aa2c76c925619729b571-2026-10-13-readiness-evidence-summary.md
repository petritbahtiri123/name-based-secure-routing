# Readiness evidence reconciliation - October 13, 2026

This documentation update grants no execution, publication or runtime activation
authority. Published comparison baseline:
`ad77d59754651fee449bb1d9c14a946f9f3b2d15`. Newer local work remains unpublished;
historical evidence and frozen registries remain preserved.

## Published behavior and architectural direction

The baseline already includes Rust/Quinn and Go/quic-go Core v0.2/F75 route/stream
interoperability. The [federation decision](../protocol/wp8-federation-v0.1-decision.md)
records the independent peer and bounded safe-fixture exchange. The earlier same-
Rust test alone was not independent proof. This establishes no Internet-scale
federation, production governance, standardization or performance result.

The [explicit-proxy demo](../demo/nbsr-end-to-end-demo.md) composes deterministic
resolution, canonical service correlation, immutable Mapping and single-use
FlowContext, fixture-backed verified ACP authority, QUIC transport, separately
admitted channel/stream and one destination-private backend response. Its topology
is loopback and its backend is a destination-owned process. It does not establish
transparent capture, arbitrary origins or production resolver/enrollment services.

Resolution supplies a scoped synthetic handle; identity and authority do not come
from that address. Service authority is independent of transport authentication.
The full public/private federation vision uses the existing IP Internet as underlay;
the current edge-to-edge path does not establish general multi-hop NBSR transit.
See [terminology](../protocol/terminology.md) and
[architecture](../architecture/NBSR_Protocol_Vision_V3.6.md).

## Newer local evidence

- KAR: one approved public-test-key purpose-3 signature enabled composed native
  positive/negative checks. The selected native run recorded 12 KAR, 6 signature
  and 1 control passes. This is fixture evidence, not live provider authority,
  normal-roster authorization, signer provenance or READY.
- SPHERE preparation: a synthetic two-stream configuration passed offline checks.
  Placeholder targets are not an allocation or trust grant.
- Cleanup/watchdog: **91 offline tests passed** (25 watchdog cases plus 66 existing
  neighbors). Earlier partial runs overlap and must not be added again. The wrapper
  is opt-in; raw coordinator APIs and long profiles are outside its supervision.
  See [watchdog scope](../benchmarks/LOCAL_TRIAL_WATCHDOG.md).
- Linux process validation: **six scenario checks passed with a 10x injected clock**:
  normal completion, blocked pipe, injected nonzero worker exit, cancellation
  callback, partial startup and exited leader with a surviving descendant. The
  five injected failures correctly remained INVALID_PARTIAL. Each tested leader
  was reaped and its group observed absent; the exact disposable container was
  removed and subsequently reported absent. Total observed outer elapsed time was
  24.27 seconds including cleanup. This was not SSH disconnect or network work.

The outer helper returned exit 1 because its case-sensitive missing-object check
rejected Docker's lowercase response. Raw failure metadata was retained; successful
exact-container removal and subsequent absence supported the separately reviewed
cleanup conclusion. No rerun erased that reporting defect.

The 91 offline tests and six process scenarios are separate evidence categories,
not a new combined unique-test total. Python 3.14 results establish neither the
whole supported-version matrix nor hosted CI. The watchdog source used in the
process trial had SHA-256
`f0984f91159c51f9914680067fbe20f68c97391084ff3708980f6608a58b7353`.
Detailed private operational logs remain retained separately; this summary contains
no host/account identifiers, credentials or private filesystem locations.

## Remaining gates

Watchdog local_cleanup and remote_cleanup result fields remain UNCONFIRMED. Six observed
groups are narrower evidence, not general local/remote shutdown proof. Proc scans
are non-atomic; escaped sessions, parent death, kernel/filesystem stalls and
scheduling starvation remain limitations. Accelerated clocks do not establish an
unconditional real 120-second deadline guarantee.

Operator-package progress remains 2/10 within contract/offline scope, Stage 3 partial.
The [current roadmap](../superpowers/plans/2026-10-10-single-instance-operator-package.md)
separates a conditional next-week diagnostic trial from full plug-and-play delivery.
Live endpoint cleanup/provenance, resource/fault validation and exact allocation/
traffic authorization remain prerequisites. Applicable governance, revocation/timers,
restart protection, composed readiness, packaging, rollback and pilot security review
remain package gates. No publication protection or approval rule changes.
