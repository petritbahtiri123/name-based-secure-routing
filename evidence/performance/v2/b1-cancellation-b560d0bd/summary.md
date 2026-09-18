# Linux B1 cancellation closure and retained capture-loss regression

Live RED at b5272672: terminating the collector controller with SIGTERM left the
same dumpcap PID/start identity sleeping with PPid 1. The diagnostic container
was stopped to remove the orphan; its incomplete capture is preserved.

Fix b560d0bd adds deferred catchable-signal checks at capture-readiness/client
ownership safe points and within short client waits using the unchanged total
timeout. Direct and NBSR share the same adapter. LIVE GREEN: SIGTERM, SIGINT and
SIGHUP each reject the attempt, seal failure evidence and leave all observed
owned children absent. A final namespace scan finds no dumpcap or benchmark peer.
These are forced cancellation checks, not clean eleven-counter runtime exits.

Normal fixed-workload rerun: the first twelve captures complete, then the
thirteenth (NBSR 16 KiB/eight streams, repeat two) reports exactly two pcap drops:
135798 packets captured, 2 pcap drops, 0 dumpcap/flushed/interface drops. The
controller rejects the cohort as INVALID_PARTIAL without replacing the failed
repeat. All preceding records and raw capture/export files are retained. No
full-cohort acceptance, zero-loss 16 KiB recertification or causal attribution
of the loss is claimed. The prior complete 6b3d37e8 packet cohort retains its
own historical source scope; it has not been silently superseded by a success.

The complete 1 KiB/64-stream subset contains all five counterbalanced pairs,
with zero reported capture loss and workload errors. Its whole-capture paired
IP delta median is 1317600 bytes, range 1135495..1652512, or +1.005249% of useful
application bytes. Direct/NBSR IP medians are 143946328/145263928 bytes. This
subset includes every valid result for that shape; the two valid 16 KiB rows
and failed third row remain incomplete and are not reported as a repeatable
16 KiB result. Setup/untimed validation/teardown are included; this is not a
constant NBSR tax, physical-wire measurement or throughput claim.

The real loss also exposed a report inconsistency: the graceful-close flag could
remain valid=true after packet-accounting rejection, although the outer row and
cohort correctly failed. Literal RED then minimal fix a673a74c makes the Linux
capture report itself invalid on any accounting error. Offline revalidation of
the same retained drop log rejects it and records valid=false without rewriting
raw evidence or rerunning/replacing the capture. Windows capture behavior is
unchanged. The corrected flag does not excuse or reduce capture loss.

Focused cancellation/timeout/observer tests pass; the original 600-second client
bound remains tested, not extended. The final report regression has 18 focused
Python tests PASS. Ruff/diff checks and a fresh locked release build pass; all
three Rust binary hashes match the prior retained binaries. No production,
wire, authentication, trust, authority or security behavior changed. Remaining
capture-loss cause is UNRESOLVED_OBSERVER; no larger buffer or guessed production
optimization was introduced.
