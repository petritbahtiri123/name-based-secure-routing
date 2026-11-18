"""OFFLINE candidate, not connected to RUN1709 or a transport.

The trusted adapter must call checkpoint from the existing cancellable scan,
route EVERY reserved write through write(), and enforce the exact clock-probe
argv for a post permit. This contract does not replace resource reconciliation,
endpoint cleanup, frame validation, or the scientific calibration validator.
"""

import math


class Lifecycle:
    SCHEMA = "nbsr-reader-lifecycle-v1"

    def __init__(self, *, run, source, owner, anchor, deadline, caps, clock):
        if not all(type(v) is str and v for v in (run, source, owner)):
            raise ValueError("explicit immutable identity")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (anchor, deadline)) or not 0 <= anchor < deadline:
            raise ValueError("original finite interval")
        if set(caps) != {"capture", "receipts"} or any(type(k) is not str or not k or type(v) is not int or v < 0 for k, v in caps.items()):
            raise ValueError("fixed reservations")
        self.identity = dict(run=run, source=source, owner=owner)
        self.anchor, self.deadline, self.clock = anchor, deadline, clock
        self.previous = anchor
        self.caps, self.used = dict(caps), dict.fromkeys(caps, 0)
        self.state = "OPEN"
        self.timings = {}
        self._permit = None
        self._post = self._settled = False
        self._capture_sha = self._receipt_sha = None
        self._owner = None

    def _fail(self, why, kind=ValueError):
        self.state = "INVALID"
        raise kind(why)

    def _check(self):
        try:
            if self.state in ("INVALID", "ACCEPTED"):
                self._fail("terminal lifecycle")
            if self._owner is not None:
                owner = self._owner
                if owner.identity != self.identity["owner"] or owner.cancelled or owner.killed or owner.drain_failure is not None:
                    self._fail("owner changed/cancelled after binding")
                if self.state == "CLOSED_UNSETTLED" and owner.owned is not False:
                    self._fail("ownership returned after closure")
            now = self.clock()
            if type(now) not in (int, float) or not math.isfinite(now) or now < self.previous:
                self._fail("monotonic clock uncertainty")
            self.previous = now
            if now >= self.deadline:
                self._fail("original deadline expired", TimeoutError)
            return now
        except BaseException:
            self.state = "INVALID"
            raise

    def _sha(self, value):
        if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            self._fail("SHA256 receipt identity required")
        return value

    def checkpoint(self, owner, capture):
        """Called DURING scanning: observe/reap before remaining scan work.

        Single owner thread only. Capture must validate final framing and writer
        quiescence, not merely return the last observed data. No I/O is hidden here.
        """
        if self._owner is not None and owner is not self._owner:
            self._fail("different owner object")
        self._owner = owner
        self._check()
        if self.state != "OPEN":
            return
        try:
            if owner.identity != self.identity["owner"] or owner.drain_failure is not None or owner.cancelled or owner.killed:
                self._fail("owner identity/drain/cancellation")
            code, live = owner.observe()
            self._check()
            if type(live) is not bool or (code is not None and type(code) is not int):
                self._fail("uncertain ownership observation")
            if code is None:
                return
            if code != 0:
                self._fail("reader failed")
            if live:
                return
            owner.reap()
            self._check()
            if owner.owned is not False or owner.drain_failure is not None:
                self._fail("closure retains handles or drain failure")
            proof = capture()
            self._check()
            expected = dict(self.identity, quiescent=True, final_valid=True, sha256=proof.get("sha256") if type(proof) is dict else None)
            if proof != expected or proof.get("quiescent") is not True or proof.get("final_valid") is not True:
                self._fail("capture identity/finality/quiescence")
            self._capture_sha = self._sha(proof["sha256"])
            self.state = "CLOSED_UNSETTLED"
            self.timings["closed"] = self.previous
        except BaseException:
            self.state = "INVALID"
            raise

    def write(self, partition, data, sink):
        """Reserve before writing; partial/failed writes never reclaim credit."""
        self._check()
        if self._settled or (partition == "capture" and self.state != "OPEN"):
            self._fail("sealed output cannot change")
        if type(data) is not bytes or partition not in self.caps:
            self._fail("unallocated output")
        if len(data) > self.caps[partition] - self.used[partition]:
            self._fail("output reservation exceeded")
        self.used[partition] += len(data)
        try:
            count = sink(data)
            if type(count) is not int or count != len(data):
                self._fail("short output write")
            self._check()
        except BaseException:
            self.state = "INVALID"
            raise

    def begin_post(self):
        self._check()
        if self.state != "CLOSED_UNSETTLED" or self._permit is not None:
            self._fail("one post after proven closure only")
        self._permit = dict(
            schema=self.SCHEMA,
            **self.identity,
            operation="clock-probes-only",
            anchor=self.anchor,
            deadline=self.deadline,
            capture_sha256=self._capture_sha,
        )
        self.timings["post_started"] = self.previous
        return dict(self._permit)

    def finish_post(self, permit, *, span_ns, probes_valid):
        self._check()
        if self._permit is None or permit != self._permit or self._post:
            self._fail("post permit mismatch/reuse")
        if probes_valid is not True or type(span_ns) is not int or not 0 <= span_ns <= 90_000_000_000:
            self._fail("calibration coverage/span or probe failure")
        self._post = True
        self.timings["post_finished"] = self.previous

    def finish_settlement(self, *, valid, receipt_sha256):
        self._check()
        if self.state != "CLOSED_UNSETTLED" or self._settled or valid is not True:
            self._fail("resource settlement failed/missing/duplicate")
        self._receipt_sha = self._sha(receipt_sha256)
        self._settled = True
        self.timings["settled"] = self.previous

    def accept(self):
        self._check()
        if self.state != "CLOSED_UNSETTLED" or not self._post or not self._settled:
            self._fail("closure plus post plus settlement required")
        self.state = "ACCEPTED"
        return dict(
            schema=self.SCHEMA,
            **self.identity,
            lifecycle_complete=True,
            campaign_validity="REQUIRES_OTHER_GATES",
            capture_sha256=self._capture_sha,
            settlement_sha256=self._receipt_sha,
            timings=dict(self.timings),
            bytes_reserved_used=dict(self.used),
        )

    def reconcile(self, scan, owner, capture, clock_probe):
        """Trusted integration seam, not a live adapter.

        scan must invoke checkpoints during its original full traversal and return
        a persisted bounded settlement receipt. clock_probe must enforce exact
        authorized probe argv (never workload) and all scientific probe checks.
        No scan early return or successful-result caching is permitted.
        """

        def tick():
            self.checkpoint(owner, capture)
            if self.state == "CLOSED_UNSETTLED" and self._permit is None:
                permit = self.begin_post()
                result = clock_probe(permit)
                if type(result) is not dict or set(result) != {"span_ns", "probes_valid"}:
                    self._fail("post probe receipt missing")
                self.finish_post(permit, **result)

        try:
            tick()
            receipt = scan(tick)
            self._check()
            if type(receipt) is not dict or set(receipt) != {"valid", "receipt_sha256"}:
                self._fail("settlement receipt missing")
            self.finish_settlement(**receipt)
        except BaseException:
            self.state = "INVALID"
            raise


class BoundReaderOwner:
    """Bind an already-started owner; never starts a process or grants authority.

    The caller must pin the request file and exact reader argv before construction.
    Retains native owner for caller cleanup even when this binding fails.
    """

    def __init__(self, native, *, run, source, request_sha256, argv, deadline):
        import hashlib
        import json

        if not all(type(v) is str and v for v in (run, source)):
            raise ValueError("explicit run/source")
        if type(request_sha256) is not str or len(request_sha256) != 64 or any(c not in "0123456789abcdef" for c in request_sha256):
            raise ValueError("request hash")
        if type(argv) is not tuple or not argv or any(type(v) is not str or not v for v in argv):
            raise ValueError("exact argv tuple")
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise ValueError("original finite deadline")
        self.native = native
        self._argv = argv
        self._deadline = deadline
        self._handles = (native.job, native.process, native.thread)
        self._closed = False
        self._failed = False
        self._observed = False
        if not native.started or not native.assigned or not native.owned or any(h is None for h in self._handles):
            raise ValueError("started assigned retained owner required")
        self._identity = hashlib.sha256(
            json.dumps(
                dict(run=run, source=source, request_sha256=request_sha256, argv=argv, deadline=deadline),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        self._verify()

    def _verify(self):
        try:
            if self._failed:
                raise ValueError("owner binding failure already latched")
            n = self.native
            if tuple(n.argv) != self._argv or n.deadline != self._deadline or not n.started or not n.assigned:
                raise ValueError("owner request changed")
            handles = (n.job, n.process, n.thread)
            if self._closed:
                if any(h is not None for h in handles):
                    raise ValueError("handles returned")
            elif any(a is not b for a, b in zip(handles, self._handles)):
                raise ValueError("retained handle identity changed")
        except BaseException:
            self._failed = True
            raise

    @property
    def identity(self):
        self._verify()
        return self._identity

    @property
    def owned(self):
        self._verify()
        return self.native.owned

    @property
    def cancelled(self):
        return self.native.cancelled

    @property
    def killed(self):
        return self.native.killed

    @property
    def drain_failure(self):
        return self.native.drain_failure

    def observe(self):
        try:
            if self._failed:
                raise ValueError("owner binding failure already latched")
            self._verify()
            if self._closed:
                raise ValueError("closed owner cannot be observed again")
            result = self.native.observe()
            self._verify()
            if (
                type(result) is not tuple
                or len(result) != 2
                or (result[0] is not None and type(result[0]) is not int)
                or type(result[1]) is not bool
            ):
                raise ValueError("uncertain ownership observation")
            self._observed = result == (0, False)
            return result
        except BaseException:
            self._failed = True
            raise

    def reap(self):
        try:
            if self._failed:
                raise ValueError("owner binding failure already latched")
            self._verify()
            if self._closed or not self._observed or self.cancelled or self.killed or self.drain_failure is not None:
                raise ValueError("exact successful closure prerequisite")
            self.native.reap()
            if self.native.owned:
                raise ValueError("reap retained handles")
            self._closed = True
            self._verify()
        except BaseException:
            self._failed = True
            raise
