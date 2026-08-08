from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
from typing import Any


class EvidenceOverflow(RuntimeError):
    pass


_STOP = object()


class EvidenceWriter:
    def __init__(self, path: Path, capacity: int, *, start_worker: bool = True) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self.path = path
        self.capacity = capacity
        self._queue: queue.Queue[object] = queue.Queue(maxsize=capacity)
        self._ids: set[int] = set()
        self._submitted = 0
        self._written = 0
        self._error: BaseException | None = None
        self._thread: threading.Thread | None = None
        if start_worker:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._thread = threading.Thread(target=self._run, name="nbsr-evidence-writer", daemon=True)
            self._thread.start()

    def __enter__(self) -> EvidenceWriter:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        if exc_type is not None:
            self.abort()
            return False
        self.close()
        return False

    def submit(self, record: dict[str, Any]) -> None:
        sample_id = record.get("sample_id")
        if not isinstance(sample_id, int):
            raise ValueError("sample_id must be an integer")
        if sample_id in self._ids:
            raise ValueError(f"duplicate sample_id {sample_id}")
        self._ids.add(sample_id)
        if self._error is not None:
            raise RuntimeError("evidence writer failed") from self._error
        try:
            self._queue.put_nowait(dict(record))
        except queue.Full as error:
            raise EvidenceOverflow(f"evidence queue exceeded capacity {self.capacity}") from error
        self._submitted += 1

    def close(self) -> None:
        if self._thread is None:
            raise RuntimeError("evidence worker was not started")
        self._queue.put(_STOP)
        self._thread.join()
        if self._error is not None:
            raise RuntimeError("evidence writer failed") from self._error
        if self._submitted != self._written:
            raise RuntimeError(f"evidence count mismatch: submitted={self._submitted} written={self._written}")

    def abort(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._queue.put(_STOP)
            self._thread.join()

    def _run(self) -> None:
        try:
            with self.path.open("w", encoding="utf-8", newline="\n") as handle:
                while True:
                    item = self._queue.get()
                    if item is _STOP:
                        return
                    handle.write(json.dumps(item, sort_keys=True, separators=(",", ":")))
                    handle.write("\n")
                    self._written += 1

        except BaseException as error:
            self._error = error
