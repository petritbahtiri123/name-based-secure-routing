# CRP-1 proposal consistency review

Deliverables: CRP-1 appended to docs/protocol/connector-outbound-profile.md;
docs/protocol/connector-registration-v1-vector-proposal.json (24 finite design
cases); synchronized ten-stage operator plan. Earlier prose and evidence remain
historical. No source/test, registry, authority pin or runtime change.

Concrete proposal: separately versioned, dedicated-ALPN connector control profile;
all action/carrier/message/ALPN allocations remain UNALLOCATED. Exact candidate
REQUEST/CHALLENGE/PROOF/ACCEPT/REJECT/WITHDRAW bodies, bounded CBOR/framing, dedicated
TLS exporter domain/context, explicit ACCEPT digest, live owner/correlation,
renewal, failure outcomes, verified-event boundary and future files/interfaces
are specified. Existing TLS/CBOR/authority mechanisms are reused; no new roots,
credentials or cryptographic primitive. New exporter usage still needs versioned
conformance approval.

User-requested extensibility is explicit: service-keyed config/owners/quotas/
dependencies, one enabled entry in the first slice, second-service pure fixture
isolation criterion, no hardcoded service identity or generic plugin framework.
Wire-semantic changes need a new reviewed version; adding capacity cannot weaken
per-service authorization or change service A's bytes.

Independent design review identified three issues: old lease included in the
verifier ceiling prevented extension; retries could return superseded/ineligible
acceptance; ACCEPT digest domain/bytes were undefined. All were corrected and
narrowly rereviewed with no remaining blocker. Vector variants cover old request
after renewal/deny, pending retry expiry, and exact body/digest correlation.
The dedicated-carrier recommendation is explicit; its allocation remains pending.

Local structural validation: JSON parses; exactly 24 unique sequential case IDs;
all executable-artifact statuses remain PENDING; required corrected constraints
are present; source/test hashes still match the 187-pass checkpoint. Scoped diff
check passed with existing CRLF warnings. Runtime tests were not repeated for
this documentation-only change. No generated wire vectors or conformance pass
are claimed. Historical seven-job CI for c7abbc44 is separate.

D1-D3 exact profile review, allocations, executable vector generation plus an
independent verifier, and final profile/interface acceptance remain open. Stage 1
partial, 0/10 complete. No commit/push, credentials, network or next runtime task.
