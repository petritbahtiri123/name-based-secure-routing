# Native observer/reference gate validation

Implementation: 9ed3c5a28230c081d87448cfa147b239af5af9ea.
Measured release peers: ac40740c73c70c3661140ed613f61b693abbf1a9.
This is retrospective read-only validation, not a new benchmark run.

COMPLETE: reusable observer and finite-reference integrity/qualification gates.
Literal RED: 12 observer cases, seven reference cases, then one review-found
fractional-operation counter regression. Existing finish_record rejects the
fractional counter. Initial 65 affected tests and final 24 gate tests PASS;
Ruff PASS; one independent review and scoped re-review have no Important/Critical
findings. Raw logs and manifests are retained under raw-evidence.json.

MEASURED, historical input: all six observer pairs remain included, including
the declared interruption. Median paired goodput change -3.359207%, p99 change
+40.842789%; throughput CV off/on 23.204663% / 29.063231%.
REJECTED_OBSERVER_GATE: effects, dispersion and interruption prevent qualification.
These all-six metrics differ from the earlier five-uninterrupted subset; neither
qualifies. High variance does not establish a causal production bottleneck.

Finite reference: five Direct and five NBSR repetitions, 16 KiB, eight streams,
depth one, observed WSL guest CPU placement. Both ladders UNRESOLVED.
Direct median 2.395090 Gbit/s, CV 16.120682%, p99 median 2161256 ns.
NBSR median 2.496439 Gbit/s, CV 12.173760%, p99 median 2124653 ns.
Both CLI gates return exit 2 for valid unqualified evidence. Strict-stable
reference remains NOT_ESTABLISHED. Peaks are diagnostic, not hardware ceilings.

Reproduce from repository root using the retained manifests:

```powershell
python -m scripts.performance.linux_native_observer --manifest C:/NBSR-build/native-reference-gates-validation-20260924/observer.json --source-sha ac40740c73c70c3661140ed613f61b693abbf1a9
python -m scripts.performance.linux_native_reference --manifest C:/NBSR-build/native-reference-gates-validation-20260924/reference.json --source-sha ac40740c73c70c3661140ed613f61b693abbf1a9
```

No production/security/protocol changes. Checksums are not host attestation.
Synthetic loader tests are not performance results. Full native live resource
and phase guards, reference-bound long-run orchestration and genuine near-ceiling
60/120-minute soak remain open; these read-only gates do not complete B5.
