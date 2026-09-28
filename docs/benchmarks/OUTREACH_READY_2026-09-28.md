# NBSR outreach kit

Prepared 28 September 2026. Drafts only; nothing sent or published.
Technical basis: [consolidated report](TECHNICAL_REPORT_2026-09-28.md),
with [source and evidence hashes](TECHNICAL_REPORT_2026-09-28.evidence.json).
Status: **READY FOR TECHNICAL OUTREACH WITH EXPLICIT LIMITATIONS**.

## Thirty-second introduction

NBSR is a security-focused transport and admission prototype for controlled
access to isolated private origins. We have reproducible local performance,
cleanup, adversarial and network-isolation evidence. We are looking for an
independent technical partner to reproduce the results on dedicated Linux
hardware and help evaluate a narrowly scoped pilot. Server/WAN capacity and
live independent-operator federation are not yet proven.

## First email — engineering or infrastructure partner

**Subject:** NBSR: independent Linux/server evaluation partner

Hello,

I'm developing NBSR, a security-focused transport and admission prototype for
controlled access to isolated private origins. I'm looking for an engineering
partner to independently evaluate it on dedicated Linux hardware.

Local evidence includes a historical four-core Windows loopback result of
2.306 Gbit/s strict-stable throughput, separate successful 2048-connection
trials, and three recent one-hour runs with zero errors/timeouts and verified
final cleanup. These are different source-bound workloads, not server or WAN
capacity claims. Continuous ownership qualification and live independent
federation remain open.

Would your team be open to a 30-minute technical discussion about a small,
isolated evaluation? The initial request is an engineer's review and access
to a dedicated test host, with scope and success criteria agreed first.

I can share the technical report, reproducibility guidance, and indexed
evidence, including failed runs and limitations.

Best regards,
[Your name]

## Short message — LinkedIn or introduction

Hi, I'm developing NBSR, a secure transport/admission prototype for isolated
private origins. We have source-bound local benchmark and security evidence
and are seeking an independent Linux/server evaluation partner. This is a
request for technical review and pilot scoping; production readiness and live
federation are not claimed. Would this fit your infrastructure/security team,
or could you point me to the right person? I can send a concise technical report.

## Follow-up — if the recipient has not replied

Hello,

Following up on my note about an independent NBSR evaluation. The proposed first
step is a short technical review, followed by an isolated host evaluation only
if the scope is useful to your team. We will preserve failed results as well as
successful ones. Would you prefer the technical report, or is another colleague
better placed to assess this?

Best regards,
[Your name]

## Concrete request to a technical partner

Start with one otherwise idle dedicated bare-metal Linux host for reproducible
local controls and a named engineer to review workload and security assumptions.
For a later physical-network comparison, request two dedicated hosts and a
documented 10 GbE-or-faster path. Record actual CPU topology, RAM, NIC, kernel,
toolchains and available telemetry before agreeing on runnable cells; missing
hardware capabilities remain NOT_RUN. Do not treat a VM as bare-metal evidence.

Offer source-bound build instructions, accepted local evidence and its
limitations, matched secure Direct/NBSR workloads, and joint analysis of every
valid outcome. Raw evidence is stored locally and is not automatically included
in a repository clone. Agree on a transfer scope and verify the supplied hashes.
Do not include fixture credentials or unrelated local files in an outreach bundle.

Use the [external validation definition](EXTERNAL_LINUX_SERVER_VALIDATION.md)
for commands, inventory and gates. It explicitly identifies incomplete portable
matrix coverage; it is not a claim that the entire campaign is a one-command
server test. Resolve the selected workload's prerequisites before reserving
measurement time. This proposal does not request production traffic, deployment
authority, a trust-anchor change or a live federation commitment.

## Suggested first-call agenda — 30 minutes

| Minutes | Topic | Desired outcome |
| --- | --- | --- |
| 0–5 | Partner's use case and threat assumptions | Decide whether the prototype addresses a relevant problem |
| 5–12 | Architecture and source-bound evidence | Review what passed and what remains unproven |
| 12–22 | Available hardware and executable workload subset | Select one isolated evaluation and its prerequisites |
| 22–30 | Acceptance, ownership and evidence sharing | Agree on responsible people, deliverables and next decision |

The evaluation deliverable is a source/binary-bound report with raw hashes,
environment, matched controls, at least three valid repeats per cell (five when
CV exceeds 5%), latency, errors and cleanup results. Observer qualification and
all unsuccessful attempts remain visible. Throughput gains alone do not justify
progression if security, reproducibility or cleanup fails. Pilot deployment
requires its own threat/deployment review and acceptance decision.

## Funding conversation wording

We are seeking support for independent validation and the remaining engineering
closure, rather than presenting an already production-qualified system. Proposed
milestones are reproducible server controls, explained performance boundaries,
qualified resource/soak measurements, and a reviewed isolated pilot scope.
Budget, staffing, schedule and commercial terms would be defined against that
scope; no amount, delivery date or production capacity is promised here.

## Material to share

1. Start with the [short overview](TECHNICAL_OUTREACH_2026-09-26.md).
2. Provide the [technical report](TECHNICAL_REPORT_2026-09-28.md) and
   [evidence index](TECHNICAL_REPORT_2026-09-28.evidence.json) for engineering review.
3. For interested evaluators, provide the [external validation definition](EXTERNAL_LINUX_SERVER_VALIDATION.md)
   and the selected raw artifacts through an agreed channel.

Before copying a message, replace the signature and personalize the opening
for the actual recipient. Do not remove the local/source-bound qualifications.
Do not advertise diagnostic peaks as stable throughput, finite admissions as
sustainable capacity, final cleanup as continuous ownership proof, preflight as
live federation, or this kit as production/security certification. Evidence
packaging and outreach preparation are complete; the open engineering gates
remain those in the technical report.
