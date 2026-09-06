# Streaming and failure validation — in progress

Base 6227fd86. The streaming helper preserves supplied raw bytes before parsing,
bounds partial line and line count, rejects duplicate JSON keys and unknown B5
records, latches failures, and requires one final record and successful exit.
The caller must poll its fixed deadline and resource sampler during silence,
bound input queues/callback history, observe EOF and join owned processes.
Accounting success alone does not prove cleanup or stability.

Literal missing-module RED was observed before implementation in the tool output;
no independent RED log was retained. Fresh focused pytest: 17 PASS. Scoped Ruff
and one independent read-only review passed with no Important finding. Eighteen
retained real Direct/NBSR outputs also passed replay using 127-byte input chunks;
the replay's mock sampler provides no resource-liveness evidence.

The first failure diagnostic chose an unreachable UDP endpoint and a 20-second
controller bound. Direct's existing QUIC idle timeout is 30 seconds, so that
controller expiry does not establish a cancellation defect. Its partial raw
directory remains retained, including the empty result list; do not call it PASS.

A subsequent diagnostic used a syntactically valid but immediately rejected
127.0.0.1:0 endpoint for one of two groups. Direct exited 101 in 0.02184 seconds;
NBSR exited 101 in 0.01237 seconds. Sibling cancellation and absence of a grouped
success final were observed. All owned processes exited; destination processes
were explicitly terminated. Destination ownership and graceful internal publisher
joining on failure were NOT_MEASURED. These are failure diagnostics, not three-repeat
capacity cells. raw-index.json binds both directories (51 verified raw artifacts).

The live controller and long-soak qualification are still being implemented.
