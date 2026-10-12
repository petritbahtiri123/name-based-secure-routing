# Authorized local connector loopback checkpoint

Base `c7abbc4423a9ad05cea9cdf6678c231a34cafd59`, branch
`codex/nbsr-v3-wp0-wp1`. The user explicitly authorized this local test and isolated
temporary certificates. The new adapters compile only as tests: no production
connector, frozen transport, registry, dependency or authority overlay changed.
All work remains uncommitted; stages 1-2 remain 2/10 and Stage 3 remains partial.

## Implemented and measured

The existing Go coordinator and Rust gateway now exchange registration and renewal
over real quic-go/Quinn QUIC v1/TLS 1.3 with mutually verified one-hour Ed25519 test
certificates. Both endpoints bind UDP `127.0.0.1` ephemeral ports. The server public
key and client certificate/raw key are checked against the exact isolated fixture;
the registration pin uses SHA-256 of the actual client raw public key. No OS trust,
credential files, DNS, origin access, application traffic or external endpoint is
used. Child-needed keys traverse private stdin only; evidence contains public
certificate fingerprints, process IDs and endpoints, never keys/exporter values.

The dedicated development ALPN and exact connector exporter label/context remain
separate from frozen Core transport. There is one bidirectional control stream,
no application streams or 0-RTT. The positive case registers and renews on the same
connection/owner; final ACCEPT receipt is established by Go validating it before
sending FIN. Rust receives FIN before teardown, avoiding the initially reproduced
final-response loss. Go's close joins QUIC transport workers and closes/probes its
owned socket. Rust retains cleanup tickets through endpoint idle/drop, child reap
and observed socket release; only then confirms owner/quota release. Timeout/kill
would fail the trial, not satisfy cleanup.

**Fresh final live result: one Rust integration test containing 19 sequential cases,
all passed; zero failed/ignored.** The final evidence-bearing group took 19.67s
including compilation and cleanup (test body 16.52s). Two test processes run at a
time plus the supervisor/build runner. At most two connections are used in the
duplicate-owner and cross-session second-owner rejection cases; all others use one.

Cases: register/renew; untrusted server CA; wrong ALPN; wrong server key; wrong
client key under the same CA; wrong service/gateway/principal pin; missing authority;
authority revision changed before commit; wrong exporter context; repeated old
directional sequence; synthetic deny-new and terminate; duplicate owner; old proof
on a different session; withheld proof; injected close failure; cancelled read worker.
Duplicate-owner and cross-session tests assert exact rejection reasons so a separate
synthetic-authority rejection cannot mask a broken ownership/session gate.

The cancelled-read case proves worker join and retained ownership, not that the
worker had already blocked before cancellation. The failed-close result is injected
before actual shutdown; it proves no premature release, not a naturally occurring
backend failure. Previously implemented deterministic drop/late/duplicate/stale
cleanup tests remain distinct evidence and were rerun with their Rust neighbors.

## Validation, failures and review

- Rust neighbors: 19 passed; the opt-in live test is ignored by default (one ignore).
- Go connector: 19 top-level tests, 67 passing test/subtest events; the parent-only
  worker skips by default (one skip). Shared CBOR: 3 top-level tests, 10 pass events.
  These event counts include parent tests and are not independent scenario totals.
- Focused Rust Clippy `-D warnings`, rustfmt, Go vet/gofmt and diff checks passed.
- Independent review found and verified corrections for final-response teardown,
  default-live-test gating, endpoint/socket confirmation, and exact rejection
  assertions. Final review has no remaining blocking findings; reviewer did not
  independently rerun the matrix.
- Preserved failures: initial missing-support-module scaffold compile; private
  Quinn varint-size API compile; first live renewal response lost during teardown;
  public fingerprint formatting compile against sha2 0.11. All later fixes and
  successful trials remain separate records, with no failure overwritten.
- The first process/socket query used unavailable CIM access. A subsequent query
  accidentally read a failed-compile run with no PIDs; its empty inventory is
  retained as invalid, not cleanup proof. Final `netstat -ano -p udp`/process query
  uses all 20 recorded final PIDs and finds zero remaining processes/UDP endpoints.

Each supervised group retained its command, exit status, disk/RAM samples and direct
child reap. No resource abort occurred. Initial Go/Rust compile commands briefly
overlapped, each configured for two workers; this did not enforce a global two-worker
ceiling during that overlap. All subsequent builds ran sequentially. Future commands
must remain sequential as documented. Each group stayed within the 120s total bound,
8 GiB starting disk/6 GiB floor, stricter 256 MiB per-group growth guard and 2 GiB
available-RAM floor. No downloads, cold dependency build, containers, installed trust,
network/security settings, commit, push or unrelated deletion.

## Scope and remaining gates

Registration receipts are deliberately synthetic and exact-bound to live peer,
request, service, gateway, policy, dependency digest and revision. They do not verify
purpose-14 KeyAuthorizationRecords or purpose-6 registration delegation chains.
Purpose-11 bilateral authorization is not repurposed as startup authority. Revocation
is injected locally, not an authenticated event producer. Authority time remains the
explicit logical sample 100; real wall time governs TLS validity/I/O guards only.
No new active-work lifetime, forced-release rule or authority fallback was added.

Remaining Stage 3 work: compose reviewed real peer-purpose/registration-authority
producers, exact verified revocation provenance/dependency dispatch, and real
authority clocks/timers with the existing coordinator ownership rules. This test
does not settle freshness under real outages, durable identity, full autonomous
runtime scheduling, production allocation or deployment. Future/unrelated event
delivery and lease-expiry scheduling were not newly exercised over the live wire.
No application relay, full repository suite, race detector, WAN or capacity run.
Existing Python authority/config/vector results remain historical and were not rerun.

The smallest next slice is the registration-authority producer mapping, reviewed
against the existing purpose/ownership/delegation contracts before implementation.
TLS success and local allowlists must never create missing signed authority. This
checkpoint does not authorize real provider installation or customer traffic.

## Deliverables and reproduction

New source: `crates/nbsr-transport/tests/connector_loopback.rs`,
`crates/nbsr-transport/tests/support/connector_loopback.rs`, and
`interop/nbsr-go-peer/connector/loopback_test.go`. Shared guidance, README, status,
plan and overnight checkpoints describe the narrower verified scope. Prior dirty
implementation/unrelated files remain preserved. The JSON manifest identifies
exact current source/binary hashes, prior immutable manifests, all run logs,
public certificate fingerprints, process/socket results and supervisor sources.
See the connector README for the explicit opt-in build/run commands. Reuse existing
caches and the retained bounded supervisor; no standalone unbounded test run.
