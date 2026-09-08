# B3 polling and marker-location diagnostics

An offline Linux test isolates the existing lifecycle-start polling function
against pending tasks, with five counterbalanced repetitions at each of 512,
1024 and 2048 waiters. On guest-native temporary storage, median measured CPU
is 7.49%, 14.49% and 26.47% of one allocated guest CPU. Windows bind storage
measures approximately 6.95% at all three counts. Lower CPU does not establish
lower wall-clock cost; this diagnostic does not measure poll count or I/O waits.
CPU resolution is 10ms; zero control readings mean below that resolution.
No QUIC traffic runs in this microbenchmark. Its temporary patch and complete
build/test logs are retained; it is not merged into production source.

The actual 0124f8ad release workload then compares only output/lifecycle-marker
location: Windows bind mount versus guest-native storage, three counterbalanced
pairs, 2048 materialized active bundles on one allocated guest CPU. All six
attempts fail. Every failure and socket snapshot is retained. Guest output was
copied after completion and verified against its original checksum index.
Thus this experiment does not establish a reliable filesystem-location fix or
production capacity improvement. No deadlines, workload or buffer defaults changed.

An initial wrapper lacked its required setup UID and failed before workload
execution. That setup failure is retained separately; the corrected wrapper
sets up as UID0 then drops to UID65532 before benchmark execution, matching
previous runs. No host security policy changed. No hardware ceiling is proven.
