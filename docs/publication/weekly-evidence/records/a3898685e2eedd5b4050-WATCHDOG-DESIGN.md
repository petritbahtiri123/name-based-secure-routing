# Whole-trial watchdog acceptance — design only

One owner, one immutable monotonic deadline covering startup, management, collection
and cleanup. Under an authorized 120-second cap, begin cleanup by 95–105 seconds;
every subordinate operation receives remaining time, never a fresh whole timeout.
Inject clock/process interfaces for deterministic boundary tests. Retain cumulative
resource baselines; resource/timeout abort cannot become PASS.

Track exact child handles, readers/writers and run-bound remote ownership identities
from creation, including partial startup. Stop admission, attempt graceful cleanup,
then only authorized owned-resource escalation within the deadline. Blocking I/O and
collection must be cancellable or isolated behind a bounded supervised boundary.
Retain uncertain ownership at deadline. Parent death requires independent remote
run-scoped supervision/lease, whose identity/privileges need separate review.

SSH exit is not remote cleanup proof. Require fresh run-bound evidence per endpoint:
exact source/binary identity, owned process identity with anti-reuse binding, child
reap, released sockets and actual ownership counters. Missing/stale/replayed/wrong-run
or contradictory reports remain UNCONFIRMED. Define independent observer provenance;
this outline does not authorize new signatures, keys or trust mechanisms.

Acceptance cases: partial startup; stalled stdin/stdout/stderr or collection;
terminate/kill/wait failure; disconnect; repeated cancellation in every phase;
deadline exhaustion; resource abort; management-host loss; PID reuse; stale/wrong-run
cleanup evidence. Assert global bound, attempts for all owned resources, retained
uncertainty and no PASS. Deterministic checks precede separately authorized live
fault tests. No implementation, keys, sockets, settings or deployment here.
