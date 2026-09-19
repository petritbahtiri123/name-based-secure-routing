# Native boundary marker accounting

98484de8 extends the existing live pcapng prefix reader with explicit native
IPv4 probe addresses, preserving its loopback defaults. The offline native
analyzer excludes only declared, distinct, exact 32-byte start/end probes,
counts their bytes separately and rejects missing, reversed, interleaved or
unexpected markers. Workload frames must all lie between the retained markers.

Literal RED: twelve failures. Native packet/marker and existing loopback
readiness/capture regression scope: 64 PASS; Ruff PASS. Three real synthetic
UDP echo captures each retain 200 workload frames plus separately reconciled
probe frames. The live controller observes the start token in the open pcapng
before echo traffic and the terminal token afterwards. All losses are zero;
workload byte totals exactly match independent TShark filtered exports.
Wrong-port and truncated variants reject. Raw captures, tokens, commands,
counts and logs remain retained.

This proves marker mechanics in two Docker namespaces. It is not NBSR traffic,
dedicated physical-interface measurement, phase separation, endpoint process
ownership or observer-neutral timing. Overall packet status remains diagnostic.
The remote probe socket is a fixture, not a protocol or security-authority change;
observing its outgoing datagrams does not prove remote receipt.
