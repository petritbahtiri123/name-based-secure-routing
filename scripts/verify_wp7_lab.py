"""Verify the deterministic, configuration-only WP7 topology model."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path


MAX_CONFIG_BYTES = 16_384
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nbsr.two_operator_lab import LabRejected, LabTopology, simulate_raw_scan  # noqa: E402


def main() -> int:
    config_path = ROOT / "config" / "wp7-two-operator-lab.json"
    try:
        with config_path.open("rb") as config_file:
            raw = config_file.read(MAX_CONFIG_BYTES + 1)
        if len(raw) > MAX_CONFIG_BYTES:
            raise LabRejected("topology configuration exceeds the bounded size", code="topology-config-size")
        topology = LabTopology.from_dict(json.loads(raw.decode("utf-8")))
        scan = simulate_raw_scan(topology)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, LabRejected):
        return 1
    print(json.dumps(asdict(scan), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
