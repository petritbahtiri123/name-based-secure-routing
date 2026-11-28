# P1: live local cross-gateway telemetry

## Scope and topology

This is a **live loopback Python ISP-profile relay fixture**, implemented on
`codex/p1-cross-gateway-telemetry` from base
`840fef10d601f28336afde92f730b539eaf9154f`. It supersedes the initial
[missing-composition inspection](nbsr-end-to-end-demo-limitations.md#p1-cross-gateway-telemetry-inspection-2026-11-28)
only at the scope described here.

```text
client --TLS 1.3--> gateway A --opaque TCP tunnel--> gateway B --> TCP service
       \---------------- nested TLS 1.3 to B ------------/
```

Both gateways are separate OS processes running `NameRelay`, with real ephemeral
IPv4 loopback listeners, independent registries/verification keys and signed
binding/session-proof checks. The service receives actual bytes over a socket.
No connection, admission decision or service receipt is mocked. Existing
`NameRelay`, `RouteRegistry`, `DestinationPolicy`, `issue_name_binding` and
`sign_relay_proof` are reused unchanged. The client authenticates to B through
A's admitted opaque tunnel; it never directly dials B or the service.

The client/service supervisor owns two gateway subprocesses and verifies that
their actual process IDs differ from each other and from its own. Each worker
creates its own TLS material and local trace ID. Configuration/readiness travel
only over private stdin/stdout pipes; issuer private keys are not provisioned to
gateways. Ports, certificates, process IDs and private configuration are not
published in the public report. Distinct processes are not an OS sandbox claim.
The source of trust, registered names and logical-port-443 to ephemeral-loopback-port mapping
are explicit fixtures, using the existing injected resolver boundary. Certificate
and name checks are enforced; neither TLS verification nor policy is disabled.
The B-to-service hop is local TCP. The service's loopback listener is not a claim
of host-level origin isolation. This is not the Go/Rust Core/Federation path,
multi-host deployment, production source-edge packaging or production readiness.

## Reproduce

Use the already provisioned Python environment (measured on Windows/Python 3.14).
No package installation, Cargo build, Docker, VM, Lab or benchmark controller is
required. From PowerShell:

```powershell
Set-Location <NBSR-repository-root>
python scripts/demo/cross_gateway_telemetry.py
```

### Readable terminal presentation

```powershell
python scripts/demo/cross_gateway_telemetry.py --format terminal --color always
```

The terminal view displays English labels and uses vertical boxed diagrams and green/red/gray ANSI colors.
Interactive consoles select this view automatically without arguments. On Windows,
the command enables VT processing for its console output and restores the prior
mode on exit. Boxes fit an 80-column console and remain visible without color.
Each case appears only after its live measurements and cleanup finish. Green
marks completed steps; red marks a rejected/failed connection or policy decision;
gray marks an unreached component. A red **expected** policy rejection can still
produce a green `[PASS]`: the test succeeded by enforcing the intended boundary.
Unexpected trial/cleanup failure prints red `[FAIL]`, keeps cleanup unconfirmed
and returns nonzero. This is a presentation of the same measured results, not an
animation that invents stages or changes gateway behavior.

Use `--color always` to explicitly enable ANSI output or `--color never` for
plain text. Auto mode omits ANSI when redirected, when `NO_COLOR` is set, or
when `TERM=dumb`. The diagrams use ASCII for Windows terminal compatibility.

Redirected/piped output remains raw JSON. Select JSON explicitly in any console:

```powershell
python scripts/demo/cross_gateway_telemetry.py --format json
```

JSON never contains color codes, even with `--color always`. Each command starts
a new live trial; different views from different invocations have different local
IDs. The terminal view omits IDs/private diagnostics and shows only public stage
labels and measured counts. The raw report retains the complete local traces.

The initial terminal follow-up passed **111 focused/neighbor tests** and Ruff, including
seven presentation checks for the three outcomes, color selection, safe failure
output, the live terminal CLI and unchanged explicit JSON. A live colored run
also completed all three cases with 1/0/0 service requests and clean process exits.

The boxed-view/Windows-console correction then passed **25 focused tests** and
Ruff, including live cases, interactive/redirected selection and a mocked Windows
console mode restoration check. The user's actual console appearance has not been
visually inspected.

The command runs all three cases sequentially, prints only public results and exits
zero only when all pass. Repeating it creates new local trace identifiers, keys and
ephemeral ports. Do not compare those random values byte-for-byte. It uses a
45-second supervisor cancellation deadline, a 15-second per-case operation budget
and at most 8 seconds of cleanup after cancellation (53 seconds total). Each
gateway starts no subprocesses. The supervisor requests graceful stop over its
owned pipe, then kills and waits for an unresponsive worker; forced termination
does not produce a successful cleanup receipt. Failure returns nonzero
and a public `FAIL / UNCONFIRMED` receipt, not private exception text.

Certificates and encrypted private-key files exist only in a fresh task-owned
temporary directory and are deleted after TLS contexts load. Signing/proof keys
remain in memory. No global trust store, ACL, firewall, network or Git settings
are changed. Cleanup closes listeners and connections, joins owned handlers and
relay copy tasks, waits for Windows IOCP accept completion, and checks no new
asyncio task remains before reporting zero. Both process exits must be observed
with exit code zero and verified local resource counts for a passing trial.

## Measured three-case result

The [retained JSON receipt](p1-cross-gateway-telemetry-example.json) is from the
2026-11-28 separate-process local run, not a synthetic expected-output file.
Every case reports two distinct gateway processes started, two clean exits and
zero remaining processes/listeners/tasks/connections. The service counts come
from the supervisor's real TCP service, independently of gateway receipts.

| Case | Service connections / requests | Client observation | Decisive trace stage |
| --- | --- | --- | --- |
| Allowed | 1 / 1 | Exact correlated service response verified | `gateway_b.admission_allowed`, then `service.request_received`, then `client.response_received` |
| B policy denied | 0 / 0 | Explicit rejection | `gateway_b.policy_denied`; no B connect or service event |
| B unavailable | 0 / 0 | Explicit rejection from A | `gateway_a.connect_failed`; no invented event from B |

For denial, B's real local registry disables the route after the otherwise-valid
binding is issued. The client pipelines the application request behind B's
handshake, so zero service connections/requests proves the rejected payload was
not forwarded. This is not a source-authority refusal. For unavailability, B's
process owns a bound but non-listening TCP socket: the actual connect
fails, with no free-port selection race and no simulated transport exception.
This scenario tests listener unavailability/refusal, not packet blackholing or
crash recovery. A separate negative test actually kills B unexpectedly and
requires failure plus reaping of both owned workers.

Example from the measured denial, joined only inside the test report:

```text
component-local IDs:
client    24af063b80df43c9b9c25c6e8097848e
gateway_a 10c6c9a44fd44fabb97af294e519fa93
gateway_b f136f15fb4934edebae24eee8be2bd7d

local sequence (not a global time order):
1 client     request_started
2 client     rejection_received
1 gateway_a  admission_allowed
2 gateway_a  connect_started
3 gateway_a  connected
1 gateway_b  policy_denied
service_connections=0 service_requests=0
gateways_started=2 distinct=true gateways_exited=2
cleanup: listeners=0 tasks=0 connections=0 processes=0
```

Each component generates its own local trace ID. **No trace ID is sent to
another gateway or carried in an application request.** Local observations are
exported only to the private test collector, not to a peer. The test
collector joins observations using its private knowledge of the exact per-hop
handshakes and the owned single-request topology. A separate private random
application challenge and its response digest establish service delivery;
neither is exported. No wire field is added to NBSR. `correlation=HARNESS_ONLY`
identifies this bounded test correlation, not a distributed tracing protocol.
Sequence is component-local; `ordering=PER_COMPONENT` explicitly avoids a global
time/causal-order claim across independent processes. Gateway-local write checks
reject their own trace ID in any network write; the client test also checks
that its writes contain none of the collected trace IDs.
Events originate at executed method boundaries, not a scenario-name template.
Trace fields are limited to local trace ID, sequence, component and stage;
handshakes, nonces, credentials, endpoint addresses, payloads and raw exceptions
are never serialized into the public result.

## Tests and review

```powershell
python -m pytest -q -p no:cacheprovider tests/demo/test_cross_gateway_telemetry.py tests/test_name_relay.py tests/demo/test_nbsr_end_to_end.py tests/demo/test_nbsr_final_evidence.py
python -m ruff check --no-cache scripts/demo/cross_gateway_telemetry.py tests/demo/test_cross_gateway_telemetry.py
git diff --check
```

Observed after the focused review: **104 passed**; Ruff passed.
Fourteen focused cases cover real three-case
traffic, CLI repetition, exact private-value exclusion, distinct gateway-local
IDs and absence of every trace ID from wire writes, closed event vocabulary,
handshake correlation without bypassing proof verification, wrong TLS identity/
trust rejection, cancellation cleanup, bounded supervisor cancellation, sanitized
failure output, unexpected gateway death, and kill/reap of an actual unresponsive
test-owned process. The three live cases inspect the actual spawned process IDs
and exit codes in addition to the public counts.
Existing relay tests and historical evidence/privacy tests remain unchanged.
The failure-output test injects an exception, and the deadline test uses a short
test deadline. Traffic and process-lifecycle tests use real sockets/processes.
No full suite, Rust/Go build or hosted CI run was performed.

Retained failed development checks: initial missing-harness RED; a cleanup-order
failure caused by cancelling relay handlers before closing the TLS client; then
a rejected fixture binding because the required HTTP Host claim was null.
The fixture now supplies the required claim, and client closure precedes handler
cancellation. Admission validation was not relaxed to resolve either failure.
The first successful run used a shared trace ID, before the user's clarification.
Its [initial receipt](p1-cross-gateway-telemetry-initial-receipt.json) is retained
as superseded historical evidence, **not** acceptance of the current local-ID
contract. The amended local-ID test first failed on the missing `correlation`
field, then passed after implementation. The current linked example uses only
local IDs and preserves the 1/0/0 service outcomes.

The subsequent [single-process local-ID receipt](p1-cross-gateway-telemetry-single-process-receipt.json)
is also retained as historical evidence. It had 99 combined tests and 9 focused
tests after the cleanup-counter adjustment. The separate-process regression first
failed on the absent process counter, then exposed a pending Windows IOCP accept
task at shutdown. Waiting for actual completion (bounded to 0.5 seconds), rather
than ignoring that task, resolved the latter failure.

The scoped review follows client framing -> original relay admission -> local
policy -> socket connection -> service receipt -> public output -> cleanup,
including private worker IPC, cancellation-safe process ownership, worker exit
verification and forced termination on a bounded stop failure.
It assumes exactly one request per case and does not claim hostile-local-process
isolation or multi-request concurrency coverage.

## Focused review correction (2026-11-28)

One concrete lifecycle defect was reproduced: cancellation while awaiting the
client's TLS close skipped gateway shutdown entirely, leaving both real gateway
processes alive. The regression failed on the process-exit assertion; its finalizer
killed/reaped those test-owned processes so the RED attempt left no orphan.

The harness now bounds client close to one second and puts gateway shutdown/reap
in `finally`. Failed client close aborts that owned transport and retains the
failure; it never turns uncertain cleanup into PASS. Remaining owned service
transports/tasks are closed after gateway shutdown. Both cancellation and timeout
regressions pass, along with the three live cases and existing neighbors. No
production relay, admission rule, wire field or policy was changed.

The scoped re-review found no remaining important issue in that corrected path.
The retained example below is the unchanged **pre-review** receipt; the reviewed
source was exercised by the live regression/CLI tests in the 104-test run and
committed as `b0cdad9f3`, before adding the terminal presentation.
Source hashes at that reviewed boundary:

| File | SHA-256 |
| --- | --- |
| `scripts/demo/cross_gateway_telemetry.py` | `594a520740d55d3a60eb6e07505a5ba225929e1ebe0fff61693d1f1dcbde5f95` |
| `tests/demo/test_cross_gateway_telemetry.py` | `a8f711b676bba71f483128e76aa26a34ad251e1d1bca91d576971bd9ed38d4e9` |

## Source identity for the retained pre-review run

The base commit alone does not identify this uncommitted implementation.
SHA-256 of the exact local file bytes used for the retained run:

| File | SHA-256 |
| --- | --- |
| `scripts/demo/cross_gateway_telemetry.py` | `477d3e4b2688d41491b2d8dc1e7ebe9f4d5957d2887d8f86c36e35972852220f` |
| `tests/demo/test_cross_gateway_telemetry.py` | `59f7cd310ce672ee16de1087a7a6bd08540a00a21f34404d767b99bef9708395` |
| `docs/demo/p1-cross-gateway-telemetry-example.json` | `004cea00bc28193afab67c8114238e2c8a5d09c89d9d188e841944bdae153893` |

The superseded single-process/local-ID run hashes were: harness
`8255abefd01ecb09f18d1b96f25d6a31f61ae2bdfa3e947a18a03dd6f0993074`, tests
`cebc68b3041a791dc9f3dd9f6454d7f312156fd44655aa58afe8ffea016d920c`, receipt
`f622e76bc2e29dd23446b92770e95df036174a174ac74590e3a4306e7285a9f3`.

The superseded first run retained these historical hashes: harness
`b5956d8eb37d8c0e583cee6eea402ae235ca4487ecd6b25db09e3cbff2307865`, tests
`8731621985887338c5287fce1628b78f543d12b25c3e6c7fe8576e9f054c0400`, initial receipt
`a88b9ee1523d19cb420fd0132aaa3ba2043da68c7f0a8b714125b04942ab61bb`.

The reused production sources are unchanged from the base. Historical demo
evidence, frozen contracts, source overlays and production readiness flags are
unchanged. No commit or push was made.
