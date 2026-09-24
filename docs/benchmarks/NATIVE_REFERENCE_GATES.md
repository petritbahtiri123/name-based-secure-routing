# Native observer and finite-reference gates

These read-only gates validate retained native peer packages. They do not launch
a soak, prove dedicated hardware, authenticate remote machines or attest that
unlisted attempts do not exist. Use the full SHA of the measured release peers.

## Observer manifest

Use schema `nbsr-native-observer-v1`, an `attempts` array and an `interruptions`
array. Every attempt has exactly `repeat`, `observer`, `source`, `destination`.
Peer directories may be absolute or relative to the manifest. For five to ten
complete NBSR pairs, order odd repeats off/on and even repeats on/off. Example row:

```json
{"repeat": 1, "observer": "off", "source": "off-r1/source/peer", "destination": "off-r1/destination/peer"}
```

Use the same unpaced single-core workload, release SHA/binaries, observed Linux
placement, bind addresses and within-pair certificate bytes. Only the existing
post-close counter mode may differ. Record interruptions as nonempty descriptive
strings; any interruption disqualifies this conservative reusable gate. Retain
every valid result, including interrupted trials and unfavorable measurements.
The earlier experiment-specific six-pair report additionally shows its five
uninterrupted subset; this gate reports all listed pairs without selecting a subset.

```sh
python -m scripts.performance.linux_native_observer --manifest /evidence/observer.json --source-sha FULL_PEER_SHA
```

Qualification requires both absolute median paired goodput/p99 changes at most
5%, both throughput CVs at most 5%, five or more complete distinct pairs, exact
integer workload counters, valid cleanup reports when requested and no other
enabled observer. Direct's report option does not enable NBSR ownership counters.

## Finite depth-ladder manifest

Use schema `nbsr-native-reference-v1`, `depths`, `attempts` and `observers`.
Depths must be ordered, unique, begin at one, and belong to 1/2/4/8/16.
Each depth needs three or five complete counterbalanced Direct/NBSR pairs; use
five if either first-three throughput CV exceeds 5%. Choosing five in advance
is also accepted. Each attempt has exactly `path`, `depth`, `repeat`, `source`,
`destination`. Every depth maps to a matching observer manifest:

```json
{
  "schema": "nbsr-native-reference-v1",
  "depths": [1],
  "attempts": [
    {"path":"direct","depth":1,"repeat":1,"source":"direct-r1/source/peer","destination":"direct-r1/destination/peer"},
    {"path":"nbsr","depth":1,"repeat":1,"source":"nbsr-r1/source/peer","destination":"nbsr-r1/destination/peer"}
  ],
  "observers": {"1":"observer.json"}
}
```

The abbreviated attempts above are a schema illustration, not an acceptable
two-run reference: include all three/five repeats. Keep post-close mode enabled
on both paths, one core per role, one group and a fixed payload/stream shape.
Both peers' observed placement/build identities must match the observer cohort.
Certificates must match within each Direct/NBSR pair. Reusing a validated observer
ON cell as its corresponding NBSR reference measurement is allowed; reusing the
same evidence bytes as multiple repeats is rejected.

```sh
python -m scripts.performance.linux_native_reference --manifest /evidence/reference.json --source-sha FULL_PEER_SHA
```

Both CLIs print JSON: exit 0 means their qualification gate passes, exit 2 means
valid evidence is unqualified, and malformed/incompatible evidence raises an
error. The reference uses existing `finish_record` and `classify_ladder`, preserving
degraded/saturated/unresolved rows. A positive finite classification is still not
an offered-rate or sustained hardware-capacity claim.

The Python `load_reference` API additionally requires current SHA, current shape,
both observed placement/build identities, path, selected depth and an integer
70–80 percentage. It rejects any unqualified reference or non-STABLE selected
depth and derives an exact rational operations/s target from retained op/time
records. Its output is a prerequisite only: full native live resource/phase
guards and long-run orchestration are not implemented by these read-only gates.

Current ac40740c retained evidence is correctly rejected: observer effects/CV
fail, an interruption is declared, and both finite ladders are UNRESOLVED. No
current native strict-stable reference is thereby established.

## Reference-bound diagnostic execution

`linux_native_reference_run` connects a qualified native finite reference to the
duration-capable coordinator. Use a complete ordinary native finite configuration
with no caller-supplied `diagnostic_rate` or `diagnostic_seconds`. Both endpoints
must deploy a clean matching source/build that includes long-duration support.
Existing observer flags, if present, must be true. The wrapper derives the exact
rational rate at an explicit integer 70–80 percent and enables both live guards
and post-close reports.

```bash
python3 -m scripts.performance.linux_native_reference_run \
  --config /evidence/native-config.json \
  --reference /evidence/reference.json \
  --percent 75 --seconds 60 --output /evidence/reference-preflight
```

The 60-second mode is a functional preflight. Explicit 3600/7200-second durations
are supported, but **REFERENCE_BOUND_DIAGNOSTIC is not B5 acceptance**. The live
observer remains unqualified and the wrapper always reports sustained capacity
NOT_ESTABLISHED. Do not launch a long unqualified run merely to obtain a soak label.

Reference validation and source/shape/depth/bind gates precede child launch.
One verified in-memory analysis supplies both the retained reference and exact
rate. Actual build/placement is checked after peer collection; this adapter has
no independent prelaunch remote-placement attestation. A changed placement or
reference fails publication and retains failure evidence. The reference is
revalidated after execution. The original manifest location is recorded because
its relative paths do not resolve from the retained manifest copy.

No real successful reference-bound execution is claimed: the retained ac40740c
reference is rejected before any child output is created. Synthetic fixtures test
the successful branch, mismatch/rejection paths, changed-reference detection and
deferred CLI signal cancellation. Qualified actual native timing and genuine
near-ceiling 60/120-minute stability remain open.
