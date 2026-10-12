# Paused owned-send peer-close characterization

Base: `fb587d76fe2cf691a9caa9c278f4db4da46298b4`. One test-only addition, still uncommitted; no runtime or authority change.

A64-byte-window authenticated loopback stream starts a4096-byte owned send, proves pending mutex ownership and delivery of a payload byte, then drops only its drive future. The test closes the peer and waits for ApplicationClosed on the owning connection. Without any further drive, quota remains4096bytes, as documented. Both explicit abort and ownerDrop release quota to0; final fixture cleanup releases the shared stream (Weak cannot upgrade). This closes a coverage gap, not a verified bug.

The first attempt failed to compile because abort consumes the owner and the test also tried to drop it. Mutually exclusive abort/drop branches corrected that test-only error. Corrected test passed. Independent review found no remaining blocker and suggested removing a redundant assertion before cleanup; the final test passed again:1 test, two variants,0.26s test/4.42s supervisor. Failures, exact commands, logs, source and patch hashes are retained in the adjacent JSON. Formatting and whitespace passed. No broad suite or hosted run is claimed.

The approved additive authority is committed locally as `fb587d76fe2cf691a9caa9c278f4db4da46298b4`, on source fix `2cc01bede62b43535ef5f69e241e8d9e79bc9b26`. Nothing has been pushed. A separate read-only repository cleanup proposal is in task temp; no deletion or cache purge occurred.
