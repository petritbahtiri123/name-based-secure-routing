"""Bounded B5 stdout framing and accounting; caller owns polling/process lifetime.

Call check() at every bounded controller poll, including when stdout is silent.
feed() cannot enforce deadlines while its caller is blocked reading a pipe.
Use a binary file opened exclusively for this run; this helper never closes it,
launches a process, discards raw evidence, or extends the supplied deadline.
"""

import json
import time

from scripts.performance.b5_grouped import ProgressValidator


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


class B5Stream:
    """Retains one bounded partial line, validator state, and one final record.

    Callbacks run synchronously after raw write/flush and validation. They may
    raise to propagate live drift/resource failures; callers must bound their
    own callback history. Unknown B5 schemas and non-diagnostic output fail closed.
    Successful finish proves accounting/exit only, not stability or cleanup.
    """

    def __init__(self, *, raw_sink, groups, payload_bytes, sampler, deadline_ns,
                 max_line_bytes, max_lines, clock=time.monotonic_ns,
                 on_progress=None, on_diagnostic=None):
        for value in (deadline_ns, max_line_bytes, max_lines):
            if type(value) is not int or value <= 0:
                raise ValueError("positive exact stream bound required")
        self._validator = ProgressValidator(groups, payload_bytes)
        self._raw = raw_sink
        self._sampler = sampler
        self._deadline = deadline_ns
        self._line_bound = max_line_bytes
        self._count_bound = max_lines
        self._clock = clock
        self._on_progress = on_progress
        self._on_diagnostic = on_diagnostic
        self._pending = bytearray()
        self._lines = 0
        self._final = None
        self._failed = self._finished = False
        self._last_clock = None

    @property
    def pending_bytes(self):
        return len(self._pending)

    def _available(self):
        if self._failed or self._finished:
            raise ValueError("B5 stream is failed or finished")

    def check(self, *, source_active=True):
        """Check fixed deadline and sampler health even when no line arrives."""
        try:
            self._available()
            now = self._clock()
            if type(now) is not int or now < 0 or (self._last_clock is not None and now < self._last_clock):
                raise ValueError("invalid controller clock")
            self._last_clock = now
            if now >= self._deadline:
                raise ValueError("B5 controller deadline reached")
            self._sampler.check_health(require_running=source_active)
        except Exception as error:
            self._failed = True
            raise ValueError(f"B5 stream failed: {error}") from error

    def _write_raw(self, data):
        # Even a huge caller-provided chunk is not copied/retained as one line.
        # Handle short binary writes and reject sinks making no progress.
        view = memoryview(data)
        offset = 0
        while offset < len(view):
            part = view[offset:offset + 65_536]
            count = self._raw.write(part)
            if type(count) is not int or not 0 < count <= len(part):
                raise OSError("raw evidence sink made no progress")
            offset += count
        self._raw.flush()

    def feed(self, data, *, source_active=True):
        """Append bytes before inspection; malformed/aborted input stays on disk.

        Caller should supply bounded chunks. After source exit it may drain
        already-buffered pipe bytes with source_active=False, then call finish.
        """
        try:
            self._available()
            if not isinstance(data, bytes):
                raise ValueError("binary stdout chunk required")
            self._write_raw(data)
            self.check(source_active=source_active)
            offset = 0
            while offset < len(data):
                end = data.find(b"\n", offset)
                stop = len(data) if end == -1 else end
                if len(self._pending) + stop - offset > self._line_bound:
                    raise ValueError("stdout line length bound exceeded")
                self._pending.extend(memoryview(data)[offset:stop])
                if end == -1:
                    break
                line = bytes(self._pending)
                self._pending.clear()
                self._accept_line(line)
                offset = end + 1
                # A large chunk cannot postpone failure/deadline checks while
                # processing many bounded lines or callback work.
                self.check(source_active=source_active)
        except Exception as error:
            self._failed = True
            raise ValueError(f"B5 stream failed: {error}") from error

    def _accept_line(self, line):
        if self._final is not None:
            raise ValueError("record after B5 final")
        self._lines += 1
        if self._lines > self._count_bound:
            raise ValueError("stdout line count bound exceeded")
        value = json.loads(line.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
        if type(value) is not dict:
            raise ValueError("stdout record must be an object")
        schema = value.get("schema")
        if schema == "nbsr-b5-grouped-progress-v1":
            self._validator.accept(value)
            if self._on_progress is not None:
                self._on_progress(value)
        elif schema == "nbsr-b5-grouped-final-v1":
            self._validator.finish(value)
            self._final = value
        elif (not isinstance(schema, str) or not schema.startswith("nbsr-b5")) and value.get("event") == "diagnostic":
            if self._on_diagnostic is not None:
                self._on_diagnostic(value)
        else:
            raise ValueError("unknown stdout/B5 record")

    def finish(self, returncode):
        """Call after pipe EOF and source exit; exactly one valid final required."""
        try:
            self.check(source_active=False)
            if type(returncode) is not int or returncode != 0:
                raise ValueError("source did not exit successfully")
            if self._pending:
                raise ValueError("unterminated stdout line")
            if self._final is None:
                raise ValueError("missing B5 final")
            self._finished = True
            return self._final
        except Exception as error:
            self._failed = True
            raise ValueError(f"B5 stream failed: {error}") from error
