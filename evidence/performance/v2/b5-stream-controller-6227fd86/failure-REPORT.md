# B5 immediate grouped setup-failure diagnostic

DIAGNOSTIC ONLY. Group 0 used its normally authenticated loopback endpoint; group 1 used 127.0.0.1:0. Direct rejected it as InvalidRemoteAddress; NBSR exposed ConnectFailed. No authority, transport, or timeout setting was modified.

Both two-group sources exited independently with code 101: Direct in 0.02184 s and NBSR in 0.01237 s. Each stderr records the setup failure and the sibling cancellation panic. Neither stdout contains a grouped success final. Source process exit terminates its peer group and publisher threads; this does not prove graceful publisher joining (the failure branch panics before publisher.join). Destination processes were explicitly terminated by the controller and are not claimed to have clean ownership.

The earlier 127.0.0.1:9 diagnostic had a 20 s controller bound. Direct uses a 30 s QUIC idle timeout and awaits connecting without the NBSR wrapper's separate 5 s handshake timeout. Therefore the earlier controller timeout did not establish a cancellation defect: it could precede the initiating connection failure.

Commands, source copies/patch, exact binary hashes, process exit statuses, stdout/stderr and this diagnostic script are retained. All six owned subprocesses have observed exit codes. No repository changes, builds, or commits were made for this diagnostic.
