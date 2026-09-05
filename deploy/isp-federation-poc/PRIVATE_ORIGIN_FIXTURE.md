# Private-origin fixture handoff

Status: **UNIT_TESTS_PASS / LIVE_NOT_RUN**. Three fixture unit tests pass on Windows after measurement clearance. Source and tests were authored together during the prior execution hold; no literal fixture RED is claimed. Adapter tests are separately verified. Docker startup is externally blocked by the existing `Docker/run/dockerInference` reparse-point unlink error; no deletion, reset, installation, image pull or Docker command was attempted here.

## Executable subset

`private-origin/main.py` is a stdlib-only single-threaded TCP fixture on port 8080. It handles one bounded request per connection, with at most 4096 request bytes, two seconds to finish headers, a two-second response deadline and a listen backlog of 16. It accepts only `GET / HTTP/1.1` for `Host: service-a.nbsr.test:8080`; rejects duplicate Host, body framing, NUL, malformed headers and trailing bytes already received; and returns exactly `hello from isolated private origin through NBSR` with computed Content-Length. The Origin Connector remains responsible for validating the complete stdin request before connecting; this fixture is not an authorization component or general HTTP server.

`/state/counter.json` holds only `connections`, `accepted_requests`, and `rejected_requests`. Every accepted TCP connection increments `connections` before parsing, so rejected traffic cannot disappear from isolation evidence. Counter writes are atomic. A fresh state directory is required; unexpected counter/storage failure terminates the fixture instead of serving with missing accounting. Collect the counter **before** teardown: `/state` is a bounded ephemeral tmpfs, not durable evidence. No client IP, identifier, path, request body, key or certificate is logged. The authoritative orchestrator must preserve counter snapshots and exact container identities in raw evidence.

`Dockerfile.fixture` requires an externally verified immutable Python base reference via `PYTHON_IMAGE`; it has no default, invented hash or package installation. Build context is the repository root. The runtime uses UID/GID 65532. `fixture.compose.yaml` is intentionally an **origin-only** definition: one private internal network, no published ports, no outside network membership, read-only root filesystem, dropped capabilities, no-new-privileges, resource limits and no image pulling. It is not the complete seven-service PoC and cannot demonstrate secure-route success or client isolation by itself.

## Commands after measurement and environment clearance

First validate the fixture tests and syntax from the repository root:

```text
python -m unittest discover -s deploy/isp-federation-poc/private-origin -p test_main.py
python -m py_compile deploy/isp-federation-poc/private-origin/main.py
```

No fixture RED/GREEN closure is claimed from a passing test run alone. No Docker tests should run until the existing Docker startup error is resolved through an authorized supported path.

For a future build, set `PYTHON_IMAGE` to a verified Python slim image reference ending in `@sha256:` followed by 64 lowercase hexadecimal digits, then record the exact reference and its provenance. Do not use a floating tag. The exact build argv is:

```text
docker build --network=none --pull=false --build-arg PYTHON_IMAGE=<verified-reference> --file deploy/isp-federation-poc/Dockerfile.fixture --tag nbsr-isp-origin-fixture:<source-sha> .
docker image inspect nbsr-isp-origin-fixture:<source-sha>
```

Angle-bracket values are required operator-resolved inputs, not executable defaults or existing results. Retain build output and image inspection; set `NBSR_ISP_FIXTURE_IMAGE` to the inspected immutable `sha256:<image-id>` (or an actual verified repository digest). Validate its exact 64-hex form before Compose. The local image must exist; `pull_policy: never` forbids fetching it as a fallback. Then validate:

```text
docker compose --project-name nbsr-isp-origin-<unique-run-id> --file deploy/isp-federation-poc/fixture.compose.yaml config --quiet
```

Do not start this fragment alongside a separate full PoC project and assume their private networks are shared. Integrate the same origin service under the full project's `isp_b_private` network and verify live membership first. No host port should be added to make tests convenient. Counter inspection can use the container's existing Python executable through exact-project `docker compose exec`; it must not mount the Docker socket into any container.

## Full topology boundary still open

The unchanged Go demo-client readiness has capitalized fields `Schema`, `Proxy`, `SyntheticIP`, `State`, with schema `nbsr-demo-client-ready-v1`. Its endpoint-only TCP adapter projection must be derived from `Proxy` after validating `State=ready`. The Go runtime CLI supports `--config`, `--bootstrap`, `--ready`, `--runtime-root`, `--build-root`; it enforces existing root-containment validation, so arbitrary container paths must not be guessed. The authority supports `--listen`, `--runtime`, `--client-bootstrap`, `--runtime-admission` and remains loopback-only.

Remaining integration code must produce valid contained runtime artifacts, the exact hashed Origin Connector backend map, federation admission preflight and digest correlation, and an endpoint-only Rust readiness copy. It must enforce ordered startup before adapters/workload, all seven services' exact network membership, four direct-origin denial probes, failure/recovery scenarios, and full cleanup. These are implementation work, not external blockers. The demo-only build parent now selects fixed `/opt/nbsr-build/nbsr-demo` on Linux while retaining the existing Windows hierarchy and containment/hash guards; Windows config tests pass, Linux-only tests still require actual Linux execution. No frozen runtime or authority change is implied by this handoff.
