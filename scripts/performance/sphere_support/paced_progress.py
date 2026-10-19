"""Grouped progress validation for externally owned bounded SPHERE runners."""

import json


class Progress:
    def __init__(self, path):
        self.path = path
        self.offset = 0
        self.pending = b""
        self.started = False
        from scripts.performance.b5_grouped import ProgressValidator

        self.grouped = ProgressValidator(1, 1024)

    def poll(self, guard, now):
        if not self.path.exists():
            return
        if not self.started:
            self.started = True
            guard.monitor_progress = True
            guard.last_progress = [now]
        size = self.path.stat().st_size
        if size < self.offset or size > 4 * 1024**2:
            raise RuntimeError("progress file bounds")
        with self.path.open("rb") as f:
            f.seek(self.offset)
            data = f.read(65537)
        if len(data) > 65536:
            raise RuntimeError("progress backlog")
        self.offset += len(data)
        self.pending += data
        lines = self.pending.split(b"\n")
        self.pending = lines.pop()
        if len(self.pending) > 8192:
            raise RuntimeError("progress line bounds")
        for line in lines:
            row = json.loads(line)
            if row.get("schema") == "nbsr-b5-grouped-progress-v1":
                self.grouped.accept(row)
                if row["completed"] > guard.completed[0]:
                    guard.progress(0, row["completed"], now)
                continue
            if row.get("schema") == "nbsr-b5-grouped-final-v1":
                self.grouped.finish(row)
                continue
            if row.get("event") != "p2a_progress":
                continue
            if row.get("schema") != "nbsr-b5-progress-v1" or row.get("errors") != 0 or row.get("timeouts") != 0:
                raise RuntimeError("application progress integrity")
            guard.progress(0, row.get("completed_total"), now)
