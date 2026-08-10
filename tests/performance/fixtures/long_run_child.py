from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def emit(document: dict[str, object]) -> None:
    print(json.dumps(document, sort_keys=True, separators=(",", ":")), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("completed", "failed", "empty-failed", "timeout"), required=True)
    parser.add_argument("--descendant-pid", type=Path)
    parser.add_argument("--self-pid", type=Path)
    args = parser.parse_args()

    if args.self_pid is not None:
        args.self_pid.write_text(str(os.getpid()), encoding="ascii")

    descendant: subprocess.Popen[str] | None = None
    if args.descendant_pid is not None:
        descendant = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            text=True,
        )
        args.descendant_pid.write_text(str(descendant.pid), encoding="ascii")

    if args.mode == "empty-failed":
        raise SystemExit(9)

    for sample_id in range(3):
        emit({
            "event": "request",
            "sample_id": sample_id,
            "started": True,
            "result": "failed" if args.mode == "failed" and sample_id == 2 else "completed",
        })
        emit({
            "event": "resource",
            "timestamp_ns": sample_id * 1_000_000_000,
            "working_set_bytes": 10_000 + sample_id,
            "private_bytes": 8_000 + sample_id,
        })
        emit({
            "event": "runtime",
            "timestamp_ns": sample_id * 1_000_000_000,
            "heap_alloc": 1_000 + sample_id,
        })
        emit({
            "event": "diagnostic",
            "timestamp_ns": sample_id * 1_000_000_000,
            "application_streams_current_live": 0,
            "replay_state_current_entries": sample_id,
        })
        time.sleep(0.05)

    if args.mode == "failed":
        raise SystemExit(7)
    if args.mode == "timeout":
        time.sleep(60)


if __name__ == "__main__":
    main()
