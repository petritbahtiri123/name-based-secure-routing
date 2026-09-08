# Linux receive-buffer sensitivity diagnostic

Three failure-only snapshots at132a3b82 identify10501/4605/6447 cumulative
receive drops on the single owned destination UDP socket; the retained source
sockets report zero drops. This localizes an observed receive-queue loss, not
all handshake failures or a hardware ceiling. Raw:
C:/NBSR-build/linux-udp-snapshots-132a3b82.

With benchmark-harness on Linux only, NBSR_BENCH_UDP_RECEIVE_BUFFER_BYTES=1048576
now requests a bounded1MiB destination receive buffer for a controlled sensitivity
comparison. Unset preserves the existing default. Other values fail. The OS may
clamp the request; existing actual-buffer stderr reports must be retained. A
request that lowers the prior buffer is rejected before the listener is returned.
The shared socket helper also covers Direct listeners. No production default,
QUIC/application credit, admission/authentication or wire behavior is changed.
B3 source metadata records the setting, including explicit null when unset, and
retains the socket helper source. Do not pool variants or call a diagnostic change
a measured capacity improvement before matched repeated execution.

Literal RED: missing Rust parser; Python metadata binding fails twice. GREEN:
two focused Linux Rust tests, release clippy with warnings denied for library and
Direct peer, default-feature library check,34 Python tests, fmt and Ruff.
The build image initially lacked clippy; it was installed in an ephemeral build
container for this validation. Shell line-ending and intermediate tooling failures
are preserved. Raw:C:/NBSR-build/b3-linux-buffer-098ea77a.

Next: three counterbalanced2048-bundle default/requested-buffer diagnostic pairs,
unchanged one-guest-core placement, keepalive, offered release schedule, hold,
cleanup and timeouts. Preserve every failure. No optimization claim yet.
