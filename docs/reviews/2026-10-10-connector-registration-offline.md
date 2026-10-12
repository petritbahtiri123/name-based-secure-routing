# CRP-1 offline implementation and vector checkpoint

Base: `c7abbc4423a9ad05cea9cdf6678c231a34cafd59`, branch
`codex/nbsr-v3-wp0-wp1`, uncommitted work. The user approved the exact CRP-1
recommendations for offline specification/executable vectors only. Existing
dirty transport/model/outreach work and historical manifests were preserved.

## Delivered scope

- `nbsr/connector_registration_offline.py`: strict candidate schemas for all six
  control bodies, shortest QUIC-length framing, exporter transcript, ACCEPT
  digest/validation, restrictive service pins, finite control ownership and
  correlation, registration/renewal, withdrawal, cleanup, explicit expiry polls,
  revision-guarded commit and a finite connection-attempt scheduler model.
- `tests/protocol/test_connector_registration_vectors.py`: 83 deterministic
  checks, including retained-byte execution, negative encodings, replay,
  deadlines, service isolation and all reproduced review defects.
- `scripts/generate_connector_registration_vectors.py` and
  `vectors/connector-registration-v1/`: 18 hashed byte artifacts plus a manifest
  mapping all 24 proposal scenarios to executable pytest nodes.
- `scripts/verify_connector_registration_vectors.mjs`: separate Node implementation
  checks byte integrity, transcript, TLS 1.3 SHA-256 exporter derivation, ACCEPT
  digest, framing and selected negative encodings. It does not independently
  execute all 24 stateful scenarios.

Full existing model/federation fixtures supply CRP-19/20/21/22 continuity,
deny/terminate, outage and event semantics. Their existing public deterministic
COSE checks were rerun; they do not establish the unallocated registration right.
The new authority receipt is synthetic, with explicit request/connection/session,
deadline profile, references and revision. The exporter master bytes are public
deterministic fixture input, not credentials. No sockets, real TLS handshake,
authority discovery, authenticated event delivery or application work is added.
No action/message/profile/ALPN identifier is assigned. Test-local body keys do
not imply an allocated carrier. No existing registry or pinned source changed.

## Reproductions and review

All bounded runs retain JSON, stdout and stderr under
`evidence/connector-registration-v1/2026-10-10/`:

| Run | Result | Meaning |
| --- | --- | --- |
| crp1-availability-red | 1 failed | Offline module absent before implementation |
| crp1-first-green | 44 passed, 1 failed | Proof incorrectly rechecked REQUEST sent_at against later time |
| crp1-core-green | 45 passed | Check sent_at at REQUEST; preserve original challenge deadline |
| crp1-review-red | 3 failed, 47 deselected | Unbounded terminal retention; missing candidate poll; missing revision guard |
| crp1-stale-operation-red | 2 failed, 48 deselected | Stale REQUEST/PROOF destroyed successor pending operation |
| crp1-review-green | 50 passed | Four independent review findings corrected |
| crp1-pending-event-red | 1 failed, 72 deselected | Candidate dependency denial failed to prevent commit |
| crp1-boundaries-green | 73 passed | Candidate dependencies invalidated; parser/resource boundaries pass |
| crp1-reject-red | 1 failed, 73 deselected | Missing REJECT codec before frozen-error reuse |
| crp1-neighbors-final | 337 passed | Initial complete scoped pass |
| crp1-commit-boundary-red | 1 failed, 82 deselected | Identifier callback could cross challenge deadline after time check |
| crp1-final | 338 passed | Final clock after allocation; no callback after serialized commit guard |

The withheld-proof test's initial failure was missing `poll`, not a measured
runtime timer failure. The first implementation was preceded by the availability
regression; the later behavior regressions above each reproduced their defect.
Generation and `--check` passed. Node verifier passed. Ruff check/format passed.
No failed attempts were discarded; no skip was used to obtain the final pass.

Independent reviewer identified the four retention/pending/revision defects,
then confirmed the corrections and precise scope. Final narrow review confirmed
the allocator/deadline fix. The revision source must be read-only and
non-reentrant under the explicitly serialized fixture boundary. Reviewer did
not rerun the reported suite. No remaining blocker in that narrow offline review.

## Final validation and resource limits

Final command (repo root, existing Python 3.14.6/pytest 8.4.2):

```text
python -m pytest -q -p no:cacheprovider tests/protocol/test_connector_registration_vectors.py tests/test_connector_federation_model.py tests/test_connector_control_model.py tests/federation/test_authorization.py tests/federation/test_outage.py tests/federation/test_revocation.py tests/protocol/test_states.py tests/protocol/test_cbor.py
```

**338 passed, zero failed/skipped** in 2.27s pytest / 3.65s supervisor:
83 new CRP tests + freshly rerun prior 187 + 68 CBOR neighbors. This is not a
repository-wide or Python-version-matrix result. No hosted CI run covers these
uncommitted changes. Historical seven-job CI at the base remains separate.

Every supervised run used the existing 95s work/120s cleanup bound, offline
dependency environment, maximum two jobs, >=8 GiB disk start, 6 GiB floor,
stricter 256 MiB disk-growth abort and 2 GiB free-RAM reserve. No abort fired;
all direct children were reaped. Final disk 12,213,010,432 bytes; free RAM
4,517,142,528 bytes. No containers or background workers were created.

Diagnostic follow-up: local commands/tests succeeded after the reported
17:59:49 UTC reconnect. At 18:04:47 UTC the latest app log was still empty,
with the prior nonempty log ending 17:28:29 UTC. No new causal diagnosis follows.

## Remaining gates and nonclaims

**Stage 1 partial; 0/10 stages complete.** Offline D1-D3 approval is recorded.
The 24 scenarios are executable mappings, not 24 independently validated wire
exchanges with a full authenticated registration chain. CRP-09 checks verifier
rejection/revision, not durable lineage; CRP-22 remains an explicit semantic
fixture, not authenticated event packaging or a production dispatcher.

Four cached results plus random request IDs and a sequence watermark do not
prove safe eviction. The model retains four operation slots and then rejects
additional operations; expired/failed operation slots also count. Safe
long-lived bounded replay retention needs a separate reviewed choice. This
limitation is exposed rather than silently allocating ordered request IDs,
unbounded tombstones or automatic reconnect/takeover behavior.

Production clock skew, transport deadline integration, authenticated registration
authority and event producer, registry/carrier allocation, independent stateful
conformance and final interface acceptance remain open. Explicit polling and
one extra candidate slot are offline fixture mechanics. Existing active-work
tests retain separately authorized finite grace; registration's 60s cap never
becomes a universal transfer lifetime. Two-service tests do not enable a live
multi-service deployment.

No commit, push, publication, credentials, dependency download or runtime
activation occurred. Exact current hashes/snapshots and all run metadata are
listed in the accompanying JSON manifest; historical evidence is unchanged.
