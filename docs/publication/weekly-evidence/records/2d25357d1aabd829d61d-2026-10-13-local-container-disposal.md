# Offline local-container disposal contract

Approved local scope: a surviving controller owns two disposable endpoint
containers. This implementation provides deterministic producer/validator and
three-cell orchestration contracts only. No live engine adapter, CLI, Docker
execution, sockets, keys, signatures, build, dependency download or publication.

## Producer and validator

`scripts/performance/local_container_disposal.py` owns creation and exact-ID
removal through a trusted injected management engine. Each immutable binding
contains the invocation run, source/destination role, full 64-hex container ID,
and the engine's isolated-container assertion. Initial presence must match that
binding. Both initial and post-removal observations must carry the exact newly
issued probe object; a cached observation cannot answer a new probe.

The engine contract requires no host/shared namespace or untracked external
descendant. Removal must target only the supplied immutable ID and raise on
failure. A fresh engine absence observation after removal produces an
instance-owned receipt. Workload output is not accepted by this producer.
The controller consumes both exact current receipts together; copied, forged,
other-controller, missing and reused receipts cannot release ownership.

Failed cleanup keeps both logical owners visible and blocks replacement. A caller
may explicitly retry disposal of the failed exact owner; the sequence itself
stops rather than retrying automatically. Unknown creation outcome permanently
latches this controller off, because an unreturned resource identity cannot be
assumed absent. Known owners are still available for cleanup. Reentrancy is
rejected across engine callbacks. Run and container IDs never reuse within the
surviving instance.

These object identities are accidental-misuse guards inside one trusted process,
not cryptographic receipts or a hostile-process trust boundary. There is no
controller restart recovery, durable receipt storage or independent measurement
of real namespace teardown. A future trusted engine adapter must perform those
live observations; the deterministic engine fixtures merely specify the contract.

## Three-cell composition

`scripts/performance/local_container_sequence.py` validates all three configs
before creating anything. It reuses the existing finite config validator and
watchdog/worker command contracts, including the watchdog's `/worker` child output
and rejection of long diagnostic profiles. Config paths and every output root
are fresh and mutually disjoint in the plan. Two streams, NBSR and post-close
reports are required; source, workload, fixtures and other configuration remain
identical across cells except endpoint output paths.

The trusted injected workload adapter returns a typed outcome. Expected statuses
are PASS_CONTROLLED_FINITE_PAIR, INVALID_PARTIAL, PASS_CONTROLLED_FINITE_PAIR.
The interrupted result also names the exact two owners whose readiness preceded
the deliberate interruption. Readiness is simulated here. Exceptions or unrelated
INVALID_PARTIAL outcomes cannot stand in for that step. All outcomes and cleanup
errors remain inspectable. Cleanup is attempted for each known endpoint even if
the other fails; a new cell cannot begin until both disposal receipts are consumed.

Command tuples are recipes, not executions. Synthetic `.invalid` hosts and
documentation addresses remain offline inputs. No config files are materialized
and no path existence, binaries, fixture validity, cardinality, payload integrity
or real readiness is established by these tests. The future workload adapter must
bind the exact serialized config to the exact containers, use the existing finite
endpoint/result validators, and perform the readiness-triggered interruption.
No management EOF or workload self-report substitutes for engine disposal.

## Verification and review

Retained RED runs establish missing contracts (17 and 12 assertion failures),
missing readiness binding (3 failures), watchdog recipe/profile mismatch (2),
and config/output overlap (2). All failures and succeeding runs are retained.
Independent review identified the latter three plan-consistency issues and no
blocking ownership/disposal defect within the trusted synchronous fake-adapter
scope. Each issue has a focused regression and correction.

Focused command (plus existing finite-run, watchdog and cleanup-failure neighbors):

```sh
python -B -m pytest -q -p no:cacheprovider \
  tests/performance/test_local_container_disposal.py \
  tests/performance/test_local_container_sequence.py \
  tests/performance/test_linux_native_finite_run.py \
  tests/performance/test_linux_native_watchdog.py \
  tests/performance/test_linux_native_cleanup_failures.py
```

Final scoped result:103 passed (35 new plus68 existing neighbors) in2.32s,
3.62s supervised, no abort, direct child reaped. Windows used a fresh test-owned
writable `--basetemp`; raw logs are retained in the dated local-handoff evidence
bundle. Ending disk13954932736 bytes and available RAM7059787776 bytes remained
above guards. Python 3.14.6
is within metadata but does not establish the broader tested version matrix.

## Remaining bounded live gate

Implement/review the concrete local engine and workload adapters, then obtain
one exact local topology/TLS/traffic/interruption/cleanup rehearsal authorization.
Reuse verified Linux binaries, clean source/build agreement and existing approved
TLS fixtures; do not generate or substitute missing inputs. Independently supervise
controller and both endpoint containers with the existing cleanup-inclusive 120s
per-cell deadline and resource guards, including engine calls and final removal.
The offline synchronous adapters have no wall-clock enforcement of their own.
Preserve normal evidence, interrupted INVALID_PARTIAL and fresh-rerun evidence
separately; prove final exact container absence and no retained ownership.

This local-container contract does not cover SPHERE bare hosts, remote SSH cleanup,
protocol authority, live registration, transparent resumption, controller loss,
power loss, production readiness or performance capacity. Those gates are unchanged.
