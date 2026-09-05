# Runtime topology implementation status

**FOCUSED_TESTS_PASS / FULL_RUNTIME_NOT_RUN.** These files implement the approved logical Option A plumbing, not live-validation evidence. Four supervisor tests, three fixture tests, the connector Go tests/vet, adapter race tests/vet, Python compilation and Ruff checks pass on Windows. The authentic federation preflight test selection also passes 37 tests in the pinned Linux Python dependency container. Docker is available and the dependency-only image stage has built; full runtime/adapter builds and live topology remain separate unexecuted gates. See [BOOTSTRAP.md](BOOTSTRAP.md).

## Real entrypoints

- `supervisor.py preflight` runs the current repository federation interoperability and authorization tests, performs an actual `LiveFederationAdmission` fixture admission/drain, and publishes a closed result binding source SHA, the checked context/two attestation files and measured state. The current fixture retains exactly eight rate-limit buckets after drain, with one admitted grant and zero active allocations; the gate checks those actual values. Retained rate-limit buckets are not active allocations and are not reset to manufacture zero-state evidence. This is **federation admission preflight**; it is not distributed live-runtime federation. Test failure prevents the result file and downstream startup.
- `supervisor.py isp-a` launches the unchanged loopback Go authority, waits for its real bootstrap artifact, then starts the unchanged Go client using validated per-run config/root/hash/readiness interfaces. The only platform change is the separately verified demo build-parent portability repair.
- `supervisor.py isp-b` generates ephemeral transport fixtures with the existing helper, writes the existing four-line hashed backend map, launches the unchanged Rust destination on loopback UDP/45979, retains original readiness, and copies only its endpoint to `isp-b-adapter:45980`. Every other transport-readiness field is preserved. Rust's compile-time `/src/crates/nbsr-transport` source path is preserved in the image so its checked local-attestation reads still use `/src/vectors/...`.
- `supervisor.py adapter-a|adapter-b` waits for secret-free endpoint projection and binds the corresponding existing adapter executable to the one private IPv4 resolved from its own network-specific alias. It never mounts the shared key-bearing runtime volume. The Go adapter itself validates exact literal listener/upstream configuration and bounded capacity/deadlines.
- `supervisor.py workload` sends one explicit CONNECT and one bounded request through ISP-A. A separate control volume coordinates the unchanged destination start gate and completion ACK without exposing runtime secrets to the client. A correct body produces `PASS_BODY_ONLY`, never an overall isolation/cleanup PASS.

The Origin Connector is a new PoC-only stdlib command at `origin-connector/main.go`, outside the opaque adapter source tree. It is built by explicit Go source filename and introduces no dependency manifest. The actual Rust backend contract clears its environment, sets cwd to the verified executable parent, bounds response to 4096 bytes and requires exactly `NBSR_DEMO_BACKEND_COMPLETE requests=1 status=ok\n` on stderr. Therefore the connector reads a fixed sibling `origin-config.json` containing only a private subnet and emits the existing exact completion marker. It does not use the historical plan's environment CIDR or alternate stderr marker. The name `private-origin` and port `8080` are compile-time constants. It validates one complete stdin request, resolves once, requires one IPv4 within the configured private subnet, dials once, bounds response and outputs nothing successful on failure. The orchestrator obtains the subnet from the explicit Compose IPAM configuration and must correlate it with live inspect before acceptance.

## Build inputs and command

`Dockerfile` has actual Go/Rust release stages and separate runtime/adapter targets. All three official base-image references must be supplied as locally available immutable repository digests. The `python-deps` stage installs the complete hash-pinned Linux wheel lock and checks dependency compatibility; no prebuilt custom Python dependency image or push is needed. See [BOOTSTRAP.md](BOOTSTRAP.md) for verified base references, dependency provenance and exact commands. No floating base default is used.

From a clean accepted checkout, once measurement and Docker environment holds are cleared:

```text
python deploy/isp-federation-poc/prepare.py --go-image <verified-go-reference@sha256:digest> --rust-image <verified-rust-reference@sha256:digest> --python-image <verified-python-dependencies-reference@sha256:digest> --private-cidr <dedicated-RFC1918-prefix> --run-id nbsr-isp-poc-<unique-id> --output <fresh-external-directory>
```

The bracketed values are explicit missing inputs, not runnable defaults or claimed existing images. `prepare.py` validates the fixed forms, clean source state, cached base digests and absence of Docker subnet overlap; builds the two targets with direct argv; records raw stdout/stderr/exit codes; resolves built image IDs; writes `compose.env`; and validates Compose configuration. It does not start containers. Its manifest records exact startup/cleanup argv with immutable local image IDs. `compose.yaml` sets `pull_policy: never`, so runtime has no image-fetch fallback. Build-time Cargo/Go dependency retrieval follows the checked manifests/locks; retain those logs.

The complete Compose topology has exactly seven services and three project-owned internal bridges. Client only joins access; ISP-A joins access/transit; ISP-B joins transit/private; origin only joins private; preflight has no network; adapters share their associated runtime namespace. No host port, host network, privilege, socket mount, host firewall change or legacy Compose reference exists. Named volumes and networks carry project ownership plus PoC labels. Runtime writable areas are bounded and non-root; the backend build directory is executable because the unchanged backend launcher must execute the verified connector.

## Verification after clearance

```text
python -m unittest discover -s deploy/isp-federation-poc -p test_supervisor.py
python -m unittest discover -s deploy/isp-federation-poc/private-origin -p test_main.py
```

From the adapter module:

```text
go test ./internal/entry ./internal/forward -count=1
go test -race ./... -count=1
go vet ./...
```

From `deploy/isp-federation-poc/origin-connector`, run `go test main.go main_test.go` and `go vet main.go` separately. This keeps application parsing outside the opaque adapter module.

New tests and source were initially authored during the execution hold; no blanket literal RED/GREEN claim is made for that subset. The concrete preflight retained-bucket mismatch was subsequently demonstrated RED and corrected GREEN against the real fixture output. Focused tests above now pass; container execution still requires separate verification. Add live positive/negative scenario evidence only after the environment is usable: direct name/IP denial from client and ISP-A, unauthorized preflight rejection, adapter/origin failure, restart on a fresh one-shot lifecycle, and complete owned-resource cleanup.

## Remaining acceptance work

The supervisor validates process readiness/exit and preflight fixture counters. It explicitly does **not** report all NBSR runtime ownership counters as zero; those still require instrumentation/evidence from the unchanged runtime interfaces or a separately reviewed demo-only observation path. It also does not turn an exact response into network-isolation proof. A full scenario/evidence orchestrator must capture topology, counter baselines/deltas, failure/recovery cases, raw evidence, checksums and exact-project teardown. Fresh run IDs/volumes are required because destination/backend state is one-shot. These are implementation/acceptance tasks; the genuinely unavailable external requirement is a working Docker engine and verified compatible cached base images.
