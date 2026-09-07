# B3 expected-source exit ordering

The current-source Linux ladder at1c16b03d completed35 stream cells through2048
streams,23 bundle cells through the third256-bundle repeat, and five3-cycle
smokes. The fourth256-bundle attempt failed reading `/proc/342/fd` during
post-close capture. Its failure.json retains all connection release/ACK markers
and the destination report-ready marker. It is not a256-client capacity limit.

For the explicit Linux bundle path, sources are allowed to exit after their
connection ACKs. Sampling while their process is exiting races FD teardown;
the earlier500-process diagnostic already demonstrated that kernel transition.
The fix moves the existing30second source join before the final cooldown sample.
It does not add a timeout or retry. The later duplicate wait is skipped only for
this already-joined path. Nonzero exit and timeout still fail before destination
report release. Ordinary active-process sampling remains strict.

Source cooldown metrics are explicitly unavailable after verified successful
exit, as already defined by the analyzer; they are never fabricated as zero.
Destination cooldown remains live and its report-release gate is unchanged.
Windows and same-process cycles retain their original ordering.

RED: missing join-before-capture ordering and two failed-join gate tests fail.
GREEN:44 focused Linux B3 tests plus73 affected tests pass (one existing skip);
Ruff passes. Actual matched256/512+ bundle
reruns remain required before this stage is considered experimentally closed.
Raw regression logs are retained at `C:/NBSR-build/b3-final-join-6660a04d`.
