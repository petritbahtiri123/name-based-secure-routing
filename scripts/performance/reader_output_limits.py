"""Fixed one-run output slots and sequential bounded persistence.

No process, filesystem admission, receiver or cross-process ledger. Callers must
bind these purposes to the reviewed fixed, exclusive outputs and existing owners.
A failed/partial operation never refunds a slot or establishes required evidence.
"""

import json
from threading import Lock
from types import MappingProxyType

_K = 1024
_M = _K * _K
_C = "cells/baseline8/"
_TRIAL = _C + "run01-trial/"
_COORD = _TRIAL + "coordinator/"
_ROLES = ("source", "destination")
_PREP_STEPS = (
    "bundle-control-admission",
    "transfer-control-bundle",
    "verify-control-bundle",
    "cold-bootstrap",
    "preflight",
    "prepare-mountpoints",
    "capability",
    "capability-absence",
)
_TLS_STEPS = ("clock", "start-tls", "public-csr", "transfer-public", "trial-mountpoints", "trial-tls")
_ORDINARY = tuple("step-" + role + "-" + step for role in _ROLES for step in (*_PREP_STEPS, *_TLS_STEPS)) + (
    "step-local-cold-bootstrap",
    "step-local-sign-public",
    "calibration-before-command",
    "calibration-after-command",
    "step-source-collect-guard",
    "step-destination-collect-guard",
)
_CLEANUP_WRAPPED = tuple(
    "step-" + role + "-" + step
    for role in _ROLES
    for step in ("preparation-rollback", "failure-remove-tls", "failure-stop-tls", "failure-cleanup-mountpoints", "failure-finalize")
)
_CLEANUP_DIRECT = tuple("worker-finalize-" + role for role in _ROLES)


def _make_table():
    rows, paths, prefixes = [], {}, []
    capacities = {
        "normal/staging": 4096 * _K,
        "normal/archives": 12240 * _K,
        "normal/guards": 2048 * _K,
        "normal/live": 2608 * _K,
        "normal/streams": 512 * _K,
        "normal/wrapper_metadata": 2048 * _K,
        "normal/public": 256 * _K,
        "normal/entry": 256 * _K,
        "normal/coordinator": 256 * _K,
        "normal/nonwrapper": 256 * _K,
        "cleanup/reports": 512 * _K,
    }
    for command in (*_CLEANUP_WRAPPED, *_CLEANUP_DIRECT):
        capacities["cleanup/command/" + command] = 128 * _K

    def add(purpose, partition, kib, names=(), prefix=None):
        if any(row[0] == purpose for row in rows):
            raise ValueError("duplicate fixed purpose")
        rows.append((purpose, partition, kib * _K))
        for name in names:
            if name in paths:
                raise ValueError("duplicate fixed output path")
            paths[name] = purpose
        if prefix is not None:
            prefixes.append((prefix, purpose))

    def file(name, partition, kib):
        add("file/" + name, partition, kib, (name,))

    def pair(command, partition, kib, names=None):
        if names is None:
            names = tuple(_C + command + "/" + s for s in ("stdout.log", "stderr.log"))
        add("streams/" + command, partition, kib, names)

    file("bundles/baseline8.zip", "normal/staging", 4096)
    for role in _ROLES:
        file(_COORD + role + ".tar.gz", "normal/archives", 1024)
        file(_COORD + role + ".tar", "normal/archives", 1024)
        add("archive/" + role + "/extracted", "normal/archives", 1024, prefix=_COORD + role + "/")
    add("live/whole", "normal/live", 2608, prefix="live-lab/")

    for command in _ORDINARY:
        if command.endswith("-collect-guard"):
            file(_C + command + "/stdout.log", "normal/guards", 1024)
            file(_C + command + "/stderr.log", "normal/streams", 8)
        else:
            pair(command, "normal/streams", 8)
    for role in _ROLES:
        file(_COORD + role + "-stderr.log", "normal/streams", 16)
        file(_COORD + role + "-transfer-stderr.log", "normal/streams", 16)

    for command in (*_ORDINARY, "run01-trial"):
        large = command.endswith(("-bundle-control-admission", "-verify-control-bundle"))
        metadata = [
            ("request.json", 32 if large else 8),
            ("job-exit-observations.json", 32),
            ("job-drain.json", 8),
            ("supervision.json", 4),
        ]
        if command != "run01-trial":
            metadata += [("exit.json", 1), ("capture.json", 2)]
        for name, kib in metadata:
            file(_C + command + "/" + name, "normal/wrapper_metadata", kib)

    public = [
        ("clock-offsets.json", 4),
        ("calibration-anchor.json", 4),
        ("calibration-before.json", 32),
        ("calibration-after.json", 32),
        ("CALIBRATION.json", 16),
        ("tls-public/certificates/public-hashes.json", 4),
    ]
    public += [("tls-public/" + role + ".csr", 4) for role in _ROLES]
    public += [("tls-public/certificates/" + name + ".der", 4) for name in ("ca", *_ROLES)]
    for name, kib in public:
        file(_C + name, "normal/public", kib)

    entries = [
        ("PREPARE-INTENT.json", 8),
        ("PREPARE-RESULT.json", 8),
        (_C + "LOCAL-ADMISSION.json", 8),
        ("CONTINUATION-INTENT.json", 8),
        (_C + "attempt.json", 4),
        (_C + "LIVE-AUTHORIZATION.json", 4),
        (_C + "accepted.json", 64),
        ("STOP.json", 16),
    ]
    for role in _ROLES:
        entries += [
            ("archive-" + role + "-mountpoint-dispatch-intent.json", 4),
            (_C + role + "-capability-PASS.json", 16),
            (_C + "guard-summary-" + role + ".json", 8),
        ]
    for name, kib in entries:
        file(name, "normal/entry", kib)

    coordinator = [
        ("config.json", 8),
        ("management.ndjson", 64),
        ("cleanup.json", 16),
        ("driver-failure.json", 4),
        ("result.json", 32),
        ("failure.json", 16),
        ("essential-accounting.json", 4),
        ("checksums.sha256", 64),
    ]
    for role in _ROLES:
        coordinator += [(role + "-collection-skipped.json", 4), (role + "-collection-failure.json", 8), (role + "-transfer.json", 8)]
    for name, kib in coordinator:
        file(_COORD + name, "normal/coordinator", kib)

    for role in _ROLES:
        file(_COORD + role + "-capture.json", "normal/nonwrapper", 4)
        file(_COORD + role + "-transfer-capture.json", "normal/nonwrapper", 4)
    file(_TRIAL + "worker-failure.json", "normal/nonwrapper", 128)
    file(_TRIAL + "final-result.json", "normal/nonwrapper", 4)
    file("normal-evidence-unknown.json", "normal/nonwrapper", 16)
    for profile in ("prepare", "continuation"):
        prefix = "parent-" + profile + "/"
        pair("parent-" + profile, "normal/nonwrapper", 32, (prefix + "stdout.log", prefix + "stderr.log"))
        for name, kib in (("job-exit-observations.json", 32), ("job-drain.json", 8)):
            file(prefix + name, "normal/entry", kib)
        for name, kib in (
            ("request.json", 2),
            ("supervision.json", 4),
            ("capture.json", 2),
            ("exit.json", 1),
            ("evidence-unknown.json", 1),
        ):
            file(prefix + name, "normal/nonwrapper", kib)

    for command in _CLEANUP_WRAPPED:
        partition = "cleanup/command/" + command
        pair(command, partition, 32)
        for name, kib in (
            ("request.json", 8),
            ("job-exit-observations.json", 48),
            ("job-drain.json", 24),
            ("supervision.json", 4),
            ("exit.json", 1),
            ("capture.json", 2),
            ("evidence-unknown.json", 1),
        ):
            file(_C + command + "/" + name, partition, kib)
    for role in _ROLES:
        command = "worker-finalize-" + role
        partition = "cleanup/command/" + command
        base = _TRIAL + role + "-cleanup-"
        pair(command, partition, 32, (base + "stdout.log", base + "stderr.log"))
        file(base + "capture.json", partition, 4)
        file(base + "unknown.json", partition, 4)
    for name, kib in (
        ("archive-preparation-failure.json", 64),
        (_C + "failure.json", 64),
        (_TRIAL + "independent-cleanup.json", 64),
        (_TRIAL + "worker-ended.json", 4),
        ("cleanup-evidence-unknown.json", 64),
    ):
        file(name, "cleanup/reports", kib)
    return (tuple(rows), MappingProxyType(paths), tuple(prefixes), MappingProxyType(capacities))


_ROWS, _PATHS, _PREFIXES, _CAPACITIES = _make_table()
_BY_PURPOSE = MappingProxyType({row[0]: row for row in _ROWS})


def audit():
    """Check the fixed table, never current filesystem/resource admission."""
    totals = dict.fromkeys(_CAPACITIES, 0)
    seen = set()
    for purpose, partition, maximum in _ROWS:
        if (
            type(purpose) is not str
            or not purpose
            or purpose in seen
            or partition not in totals
            or type(maximum) is not int
            or maximum <= 0
        ):
            raise ValueError("invalid fixed allowance table")
        seen.add(purpose)
        totals[partition] += maximum
    for partition, capacity in _CAPACITIES.items():
        if type(capacity) is not int or capacity <= 0 or totals[partition] > capacity:
            raise ValueError("fixed partition exceeds reservation")
    for purpose in (*_PATHS.values(), *(p for _, p in _PREFIXES)):
        if purpose not in seen:
            raise ValueError("unallocated fixed output")
    for index, (prefix, _) in enumerate(_PREFIXES):
        if not prefix.endswith("/") or any(name.startswith(prefix) for name in _PATHS):
            raise ValueError("overlapping fixed path mappings")
        if any(prefix.startswith(other) or other.startswith(prefix) for other, _ in _PREFIXES[index + 1 :]):
            raise ValueError("overlapping fixed prefix mappings")
    normal = sum(v for p, v in _CAPACITIES.items() if p.startswith("normal/"))
    cleanup = sum(v for p, v in _CAPACITIES.items() if p.startswith("cleanup/"))
    if normal != 24 * _M or cleanup != 2 * _M or normal + cleanup != sum(_CAPACITIES.values()):
        raise ValueError("fixed normal/cleanup reservation changed")
    return {
        "normal_reserved_bytes": normal,
        "cleanup_reserved_bytes": cleanup,
        "normal_allocated_bytes": sum(v for p, v in totals.items() if p.startswith("normal/")),
        "cleanup_allocated_bytes": sum(v for p, v in totals.items() if p.startswith("cleanup/")),
    }


def purpose_for_path(relative_posix_path):
    """Map a canonical logical path; does not inspect or authorize an OS path."""
    if type(relative_posix_path) is not str:
        raise TypeError("exact relative path string required")
    value = relative_posix_path
    if (
        not value
        or any(c in value for c in '\\:\0<>"|?*')
        or any(ord(c) < 32 for c in value)
        or any(part in ("", ".", "..") or part.endswith((" ", ".")) for part in value.split("/"))
    ):
        raise ValueError("canonical relative POSIX path required")
    purpose = _PATHS.get(value)
    if purpose is not None:
        return purpose
    for prefix, purpose in _PREFIXES:
        if value.startswith(prefix):
            return purpose
    raise ValueError("output path has no fixed allowance")


class OutputLimitError(RuntimeError):
    """Required evidence is incomplete/uncertain; never a truncated success."""

    status = "UNKNOWN"

    def __init__(self, purpose, stage):
        self.purpose = purpose
        self.stage = stage
        super().__init__("required output UNKNOWN: " + purpose + " (" + stage + ")")


_MINT = object()


class Claim:
    __slots__ = ("_purpose", "_partition", "_maximum", "_reserved", "_failure", "_lock")

    def __init__(self, row, token):
        if token is not _MINT:
            raise TypeError("claims are issued only by the fixed ClaimBook")
        self._purpose, self._partition, self._maximum = row
        self._reserved = 0
        self._failure = None
        self._lock = Lock()

    @property
    def purpose(self):
        return self._purpose

    @property
    def partition(self):
        return self._partition

    @property
    def maximum_bytes(self):
        return self._maximum

    @property
    def reserved_bytes(self):
        with self._lock:
            return self._reserved

    @property
    def failed(self):
        with self._lock:
            return self._failure is not None


def _require_claim(claim):
    if type(claim) is not Claim:
        raise TypeError("fixed Claim required")


def _check_locked(claim):
    if claim._failure is not None:
        raise OutputLimitError(claim._purpose, claim._failure)


def _check(claim):
    with claim._lock:
        _check_locked(claim)


def _latch_locked(claim, stage):
    if claim._failure is None:
        claim._failure = stage
    return OutputLimitError(claim._purpose, claim._failure)


def _latch(claim, stage):
    with claim._lock:
        return _latch_locked(claim, stage)


def _reserve_locked(claim, count):
    _check_locked(claim)
    if count > claim._maximum - claim._reserved:
        raise _latch_locked(claim, "limit")
    claim._reserved += count


class ClaimBook:
    """One local claimant; exclusive fixed dispatch is a separate prerequisite."""

    __slots__ = ("_claimed", "_lock")

    def __init__(self):
        audit()
        self._claimed = set()
        self._lock = Lock()

    def claim(self, purpose):
        if type(purpose) is not str:
            raise TypeError("exact purpose string required")
        row = _BY_PURPOSE.get(purpose)
        if row is None:
            raise ValueError("unknown fixed purpose")
        with self._lock:
            if purpose in self._claimed:
                raise ValueError("fixed purpose already claimed")
            self._claimed.add(purpose)  # Never refund even if construction fails.
        return Claim(row, _MINT)


def mark_unknown(claim, stage):
    _require_claim(claim)
    if type(stage) is not str:
        raise TypeError("failure stage string required")
    if not stage or len(stage) > 64:
        raise ValueError("bounded nonempty failure stage required")
    _latch(claim, stage)


def charge_alias(claim, byte_count):
    """Reserve another immutable retained name before publication; no refund."""
    _require_claim(claim)
    if type(byte_count) is not int:
        _latch(claim, "alias_type")
        raise TypeError("plain integer alias size required")
    if byte_count < 0:
        _latch(claim, "alias_size")
        raise ValueError("nonnegative alias size required")
    with claim._lock:
        _reserve_locked(claim, byte_count)


class BoundedWriter:
    """Sequential sink adapter. State locks are NEVER held across sink I/O.

    An already reserved in-flight write may complete after another sink fails;
    it stays charged and cannot report success after observing that failure.
    The existing capture/owner, not this adapter, bounds blocking sink I/O.
    """

    __slots__ = ("_claim", "_sink", "_closed", "_busy")

    def __init__(self, claim, binary_sink):
        _require_claim(claim)
        if not callable(getattr(binary_sink, "write", None)) or not callable(getattr(binary_sink, "flush", None)):
            raise _latch(claim, "sink_interface")
        _check(claim)
        self._claim = claim
        self._sink = binary_sink
        self._closed = False
        self._busy = False

    def _begin(self, count=None):
        claim = self._claim
        with claim._lock:
            _check_locked(claim)
            if self._closed or self._busy:
                raise _latch_locked(claim, "closed" if self._closed else "concurrent_writer")
            if count is not None:
                _reserve_locked(claim, count)
            self._busy = True

    def _end(self):
        with self._claim._lock:
            self._busy = False

    def write(self, raw):
        if type(raw) is not bytes:
            raise _latch(self._claim, "binary_input")
        self._begin(len(raw))
        try:
            _check(self._claim)
            if raw:
                written = self._sink.write(raw)
                if type(written) is not int or written != len(raw):
                    raise OSError("short or invalid binary write")
        except BaseException as exc:
            raise _latch(self._claim, "sink") from exc
        finally:
            self._end()
        _check(self._claim)
        return len(raw)

    def flush(self):
        self._begin()
        try:
            _check(self._claim)
            self._sink.flush()
        except BaseException as exc:
            raise _latch(self._claim, "flush") from exc
        finally:
            self._end()
        _check(self._claim)

    def finish(self):
        self.flush()
        with self._claim._lock:
            _check_locked(self._claim)
            if self._busy or self._closed:
                raise _latch_locked(self._claim, "concurrent_finish")
            self._closed = True
            return self._claim._reserved


def write_json(claim, sink, value, *, indent=None, sort_keys=False):
    """Preflight complete JSON within the claim, then one charged sink write.

    Bounds the retained encoding buffer, not all encoder/input-object transient
    memory. No required value/history is sampled or truncated on overflow.
    """
    _require_claim(claim)
    with claim._lock:
        _check_locked(claim)
        remaining = claim._maximum - claim._reserved
    encoded = bytearray()
    try:
        encoder = json.JSONEncoder(indent=indent, sort_keys=sort_keys, ensure_ascii=True, allow_nan=False)
        for part in encoder.iterencode(value):
            _check(claim)
            if len(part) > remaining - len(encoded):
                raise _latch(claim, "serialize_limit")
            chunk = part.encode("utf-8")
            if len(chunk) > remaining - len(encoded):
                raise _latch(claim, "serialize_limit")
            encoded.extend(chunk)
    except OutputLimitError:
        raise
    except BaseException as exc:
        raise _latch(claim, "serialize") from exc
    writer = BoundedWriter(claim, sink)
    writer.write(bytes(encoded))  # Rechecks remaining under the shared claim lock.
    return writer.finish()


# A finite subdivision of the existing live/whole reservation, never a new one.
# Parent and worker instantiate local views; exact process/path ownership and
# one global whole-run reservation remain prerequisites outside this class.
_LIVE_READER = MappingProxyType(
    {
        "request.json": 8,
        "job-exit-observations.json": 32,
        "job-drain.json": 8,
        "supervision.json": 4,
        "stdout.log": 128,
        "stderr.log": 8,
        "capture.json": 2,
        "exit.json": 1,
        "evidence-unknown.json": 1,
    }
)


def live_reader_claims(book):
    if type(book) is not ClaimBook:
        raise TypeError("fixed local ClaimBook required")
    whole = book.claim("live/whole")
    charge_alias(whole, 2480 * _K)
    if sum(_LIVE_READER.values()) != 192:
        raise ValueError("reader subdivision changed")
    return {name: Claim(("file/live-lab/reader-command/" + name, "normal/live", kib * _K), _MINT) for name, kib in _LIVE_READER.items()}


def live_completion_claim(book):
    if type(book) is not ClaimBook:
        raise TypeError("fixed local ClaimBook required")
    whole = book.claim("live/whole")
    charge_alias(whole, 2480 * _K)
    # One shared16KiB for completion pending/rename and acquisition result.
    return Claim(("live/completion", "normal/live", 16 * _K), _MINT)


def live_receiver_claims(book):
    if type(book) is not ClaimBook:
        raise TypeError("fixed local ClaimBook required")
    charge_alias(book.claim("live/whole"), 2480 * _K)
    sizes = {
        "request.json": 8,
        "job-exit-observations.json": 64,
        "job-drain.json": 8,
        "supervision.json": 4,
        "capture.json": 2,
        "exit.json": 1,
        "evidence-unknown.json": 1,
        "stdout.log": 8,
        "ready.pending": 1,
        "ready.json": 1,
        "stop.pending": 1,
        "stop.json": 1,
        "ended.pending": 2,
        "ended.json": 2,
        "failure.json": 4,
    }
    if sum(sizes.values()) != 108:
        raise ValueError("receiver subdivision changed")
    claims = {name: Claim(("file/live-lab/receiver-command/" + name, "normal/live", kib * _K), _MINT) for name, kib in sizes.items()}
    claims["stderr.log"] = claims["stdout.log"]
    return claims
