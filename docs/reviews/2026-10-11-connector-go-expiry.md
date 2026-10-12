<!-- Publication derivative; original SHA-256 ca56b79f5b8122407aedeefef2ce51dfec3707a202483af952c4c00accae1575. Personal identifiers removed. Historical hashes, results and commands refer to original local inputs; placeholder commands were not executed. Originals retained locally. -->

# Go observed-expiry latch — overnight 2026-10-11

Owner() returned an ineligible copy at expiry but left its retained state eligible.
A backward fixture-clock step then restored eligibility. Initial regression failed;
the owner-view fix exposed the same omission in renewal Begin/Retry. Both additional
subcases failed and are retained. A shared observeOwnerExpiry helper now latches
ineligibility at these three observation paths. It never releases the peer/owner
or starts new cleanup, and introduces no application-work lifetime policy.

Final affected Go packages: connector21 top-level passes/71 pass events; CBOR3
top-level passes/10 pass events; zero failures. Parent-only loopback worker remains
one explicit default skip. Two new top-level tests include two renewal subtests.
Vet, gofmt and scoped diff checks pass; independent review clear (not rerun).
Six supervised runs retained, two red runs. Exact logs/commands and final/preimage
sources plus incremental patches are in the manifest. No standalone new binary
retained: Go test used its existing host build cache.

Verified Go1.26.5 at C:/Program Files/Go/bin/go.exe, host cache
@LOCAL_USER_ROOT@/AppData/Local/go-build and modules @LOCAL_USER_ROOT@/go/pkg/mod.
Sandbox default pointed at a different cache; read-only host inspection verified
the warm cache before bounded offline host tests. No cold build or downloads.
All trials used the existing95s/120s supervisor, two jobs,8GiB disk start/6GiB
floor, stricter256MiB growth and2GiB RAM reserve. No abort; every child reaped.
Final read-only process check found no Python/Cargo/rustc/Go workers.

README records this narrow no-resurrection result and limits: no general clock
monotonicity claim, real authority, registry change, key generation, sockets,
containers or live loopback rerun. Historical loopback source/binary evidence
remains historical after this Go change. Stage3 partial, stages1-2 2/10.
Local uncommitted work only; no staging/commit/push. Prior sources preserved.
