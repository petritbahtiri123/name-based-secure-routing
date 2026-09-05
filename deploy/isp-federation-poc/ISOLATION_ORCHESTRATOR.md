# Minimal live isolation evidence runner

Status: **SYNTHETIC_TESTS_PASS / LIVE_NOT_RUN**. Ten fake-backend/topology tests pass; Ruff checks pass. The `none` compatibility regression demonstrated a literal RED at the preflight gate before its narrow repair and GREEN afterward. The other initial runner tests were authored alongside implementation during a measurement hold, so they do not establish literal RED-first evidence. No Docker operation has occurred for this new runner. Existing deployment component test evidence is separate.

After a usable Docker engine, verified cached bases, clean accepted source and successful `prepare.py` build/configuration evidence exist, the exact CLI is:

```text
python deploy/isp-federation-poc/run_isolation.py --prepared <prepare-output>/manifest.json --output <fresh-evidence-directory>
```

The runner verifies current/prepared SHA, immutable image IDs, exact prepared environment, seven defined services, three internal networks, expected namespace memberships, non-root users and absence of host ports/privilege/socket mounts. It refuses to adopt an existing project. All Docker commands use argv and retain stdout/stderr/exit code before their results are used.

Startup runs admission preflight first, then origin, the two runtimes, and the adapters; the workload is not started during this phase. Live inspect must prove the expected six instantiated services (the seventh, client-workload, is deliberately absent), three internal bridges, healthy bounded components, fixed images and no published port/extra attachment. Original inspect evidence is retained before classification.

The origin's real three-field counter must be present and initially zero. The runner executes four direct-origin probes: client-access-only one-off and ISP-A, each by private-origin DNS name and inspected private IP. DNS probes require resolution and connection denial; IP probes require connection denial. A three-second in-container alarm bounds each probe. Any successful connection or unexpected counter change stops the success path. The one-off client container's actual access-only network ID is inspected before its exact ID is removed.

Only after these checks does the runner invoke the real client workload. The workload itself verifies the exact response body; the orchestrator requires its exact success marker and an origin delta of one connection, one accepted request and zero rejections. It then waits for the existing destination supervisor's successful process-exit result. This is deliberately **PASS_SCOPED_ISOLATION_AND_BODY**, not full PoC closure or proof of NBSR ownership-zero.

Federation preflight is separately revalidated against the current checked context and two attestation hashes, one admitted grant, zero active allocations and the authentic fixture's eight retained rate-limit buckets. Live runtime federation stays `NOT_CLAIMED`. NBSR runtime ownership counters stay `NOT_MEASURED`.

Teardown first inventories and validates exact project labels plus known service/network/volume labels, then stops/removes only those inspected container IDs, network IDs and named volumes. Unrelated/mismatched labels cause refusal rather than deletion. A final inventory must be empty. Failure to capture logs or clean resources makes the result FAIL. Images are retained. No filesystem deletion, Docker repair/reset, host firewall action or socket mount is used.

Evidence contains raw commands/stdout/stderr/logs, topology, preflight, counter snapshots, probe results, destination result, analysis, manifest, summary and SHA-256 checksums. Inspected private-origin IP is confined to topology and direct-probe raw evidence. No key-bearing runtime directory is exported. Missing counters, failed commands, invalid topology, reachable origin and leftover resources cannot become PASS.

Run these synthetic tests only after measurement clearance:

```text
python -m unittest discover -s deploy/isp-federation-poc -p test_isolation.py
python -m ruff check deploy/isp-federation-poc/run_isolation.py deploy/isp-federation-poc/test_isolation.py
```

Still outside this minimal runner: unauthorized federation/route cases, adapter/origin failure and new-session recovery scenarios, transport/runtime ownership counters, whole-feature acceptance and live Docker proof. Those remain work to complete; the current Docker startup failure is the external environment blocker.
# Docker inspect compatibility regression

The new synthetic topology tests are grounded in Moby v28.0.0 source, not a
recorded Docker execution. In
[container_operations.go](https://github.com/moby/moby/blob/v28.0.0/daemon/container_operations.go),
`updateContainerNetworkSettings` initializes the network-mode name, including
`none`; container namespace sharing returns early.
[inspect.go](https://github.com/moby/moby/blob/v28.0.0/daemon/inspect.go)
copies that endpoint map into the API result without copying a namespace
donor's networks. Docker's
[none driver documentation](https://docs.docker.com/engine/network/drivers/none/)
specifies that only loopback exists in this mode.

The preflight gate accepts only an empty map or an address-free `none` entry
with exact `NetworkMode=none`; namespace-shared adapters must still have an
empty map and the exact inspected runtime container ID. The built-in `none`
network is not a project-owned bridge and must never enter teardown inventory.
This source check establishes expected API shape, not local Docker proof.
