# Placement failure attribution correction

The source 2da82de2 cohort remains shared 2/5 PASS versus split 5/5 PASS.
No raw evidence, result or denominator changed. The previous summary incorrectly
grouped shared repeats 2 and 3 as failures after activation. Retained events show:

- Shared r2: both active and released; 35 source close diagnostics report timed_out.
  Prepared-to-release spans are 10.116160071–10.375428778 seconds. Destination
  has 35 diagnostics (timed_out/other_closed), spans 10.005626532–10.243708718.
  This supports idle exposure in this held fixture, not a universal root cause.
- Shared r3: source emits only prepared/readiness_transferred. No active event;
  destination logs HandshakeFailed. No close-diagnostic JSON from either role.
  This remains an unresolved handshake-stage failure, not a measured close timeout.
- Shared r5: destination cardinality mismatch; two destination timed_out close
  diagnostics, prepared-to-release spans 6.335931172–6.346595899 seconds. Those
  intervals alone do not explain a ten-second idle timeout: last transport activity
  and scheduler progress are not measured by these timestamps.

Raw root: C:/NBSR-build/native-placement-2da82de2, unchanged index SHA-256:
cd7ce6891593b75f86efed11e27e57d38c9ded3691f0eec93454969b890ea1e0

The canonical summary was corrected and its summary checksum refreshed. Prior
wording remains in Git history. No timeout, keepalive, workload or production
code was changed. Continue to classify the wider handshake-progress cause as
UNRESOLVED / PLATFORM_DIAGNOSTIC_LIMIT rather than assigning all failures to idle.


The namespace absence scan also skipped PermissionError on /proc executable
links. Its empty result is not independent absence proof on a UID-restricted
host. Retained owned-child terminal/reap and forced group-cleanup evidence still
exists, but the earlier broad independent-scan wording is withdrawn. New EOF
controls must use the peer UID, observe the exact live PID/executable, then verify
that exact PID is absent after cancellation. No live process leak was observed
or inferred from this observer limitation.
