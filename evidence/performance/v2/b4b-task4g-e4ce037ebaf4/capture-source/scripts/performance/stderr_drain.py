"""Bounded-memory binary stderr capture, independent of the child runtime."""
import hashlib
import os
import threading


class StderrDrain:
    def __init__(self, pipe, path):
        self.pipe = pipe
        self.path = path
        self.error = None
        self.byte_count = 0
        self.digest = hashlib.sha256()
        self.thread = threading.Thread(target=self._read, name="nbsr-stderr-evidence", daemon=True)
        self.thread.start()

    def _read(self):
        sink = None
        try:
            try:
                sink = self.path.open("xb")
            except Exception as error:
                self.error = error
            while chunk := self.pipe.read(65536):
                self.byte_count += len(chunk)
                self.digest.update(chunk)
                if sink is not None and self.error is None:
                    try:
                        if sink.write(chunk) != len(chunk):
                            raise OSError("short stderr evidence write")
                    except Exception as error:
                        # Keep draining so a disk failure cannot block the child.
                        # The run remains invalid; discarded bytes are not evidence.
                        self.error = error
            if sink is not None:
                sink.flush()
                os.fsync(sink.fileno())
        except Exception as error:
            self.error = error
        finally:
            for stream in (sink, self.pipe):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception as error:
                        self.error = error

    def finish(self, timeout):
        self.thread.join(max(0, timeout))
        if self.thread.is_alive():
            raise TimeoutError("stderr evidence drain shutdown exceeded cleanup deadline")
        if self.error is not None:
            raise RuntimeError(f"stderr evidence invalid: {self.error}") from self.error
        return dict(valid=True, bytes=self.byte_count, sha256=self.digest.hexdigest(), flushed=True)
