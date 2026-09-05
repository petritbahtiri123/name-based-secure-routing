"""Readiness-only checks; never classify authorization or send test traffic."""

from pathlib import Path
import sys

role = sys.argv[1]
if role == "runtime":
    valid = Path("/health/ready").is_file()
elif role == "origin":
    valid = Path("/state/counter.json").is_file()
else:
    transport, port = ("tcp", 18080) if role == "adapter-a" else ("udp", 45980)
    valid = any(
        line.split()[1].split(":")[-1] == f"{port:04X}" and (transport != "tcp" or line.split()[3] == "0A")
        for line in Path(f"/proc/net/{transport}").read_text().splitlines()[1:]
    )
raise SystemExit(0 if valid else 1)
