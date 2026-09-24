# Short native source live observer

Integrate the host-local guard into the existing short paced native source before
introducing cross-host progress forwarding. This deliberately remains a diagnostic
20-second workload with unchanged 120-second controller deadline. Destination
memory is not measured by this stage; no full B5/soak acceptance is possible.

Use existing LinuxResourceSampler at 0.5 seconds for the exclusively owned source
PID and CPU set, and existing B5Stream to frame/validate a bounded tail of source
stdout. Keep raw stdout, a copied observed stream and ordered local receipt/resource
events. Feed queued samples before progress, stop/join the sampler before reaping
the owned child, and retain failures. Cancellation/deadline/malformed input fails
the run; numerical drift/growth remains explicitly diagnostic and preserved.

Expose one opt-in source observer mode, bound it through endpoint/coordinator
configuration and evidence identity, and prohibit it outside paced diagnostics.
Unobserved historical cells remain unchanged. Independently replay the retained
ordered local events and compare the result; verify observed stdout equals source
stdout. Observer overhead is NOT_QUALIFIED until matched measurement.

Tasks: literal RED unit/integration tests; minimal observer and native plumbing;
focused tests and one review; atomic commit; release five-pair diagnostic observer
exercise with all results retained, raw integrity and checkpoint. Actual endpoint
relay/destination guards and reference-bound long-duration execution remain open.
Do not widen this stage into production optimization or timeout changes.

Implementation checks: nine initial literal RED cases; four replay resource
identity/counter RED cases; one source-only reporting RED case. Final 138 affected
tests and Ruff PASS. Focused review and scoped re-review have no Important/Critical
findings. Real diagnostic exercise and observer-effect interpretation follow.
