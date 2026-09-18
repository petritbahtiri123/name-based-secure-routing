# B5 controller cancellation and finite smoke closure

MEASURED live RED: b5272672 standalone B5 controller SIGTERM left both
owned source/destination PID/start identities alive with PPid 1. The stopped
diagnostic container removed them; the incomplete run remains retained.

Implementation 978e200b propagates deferred cancellation through the Linux B5
backend, standalone campaign and placement controller. Checks occur only after
process ownership registration and during observation/completion. Existing
finally cleanup kills and reaps owned peers. Frozen security, Rust production,
workload semantics and total timeouts are unchanged.

Fresh locked release build at 6052fe9f reproduces all three previous ELF hashes.
LIVE GREEN: all six combinations of standalone/nested placement and
SIGTERM/SIGINT/SIGHUP reject and seal the interrupted run; every observed owned
PID/start identity is absent afterwards. These prove forced process cleanup,
not graceful eleven-counter cleanup. SIGKILL cannot be handled by this mechanism.

The normal placement cohort is a 15-second fixed-rate smoke diagnostic:
1000 offered operations/s, 16 KiB, eight streams, depth one, three-second warmup
and progress cadence. All attempts are retained, including failed performance
gates. Three pairs extend to five when metric CV exceeds five percent. Exact
counts, gate failures and remaining dispersion are in summary.json; this is
not a capacity, 60-minute soak, observer qualification or hardware-bound claim.

Literal RED tests, focused GREEN tests, Ruff and diff verification are retained.
The remaining finite-reference/B3/B4 controller cancellation paths require their
own evidence; this closure does not certify them.
