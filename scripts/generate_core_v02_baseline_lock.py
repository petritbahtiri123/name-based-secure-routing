from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/protocol/registries/core-v0.2-baseline-lock.json"
SCOPES = [
    "docs/protocol/core-v0.1-wire.md",
    "docs/protocol/core-v0.1-wire-schema.md",
    "docs/protocol/core-v0.2-version-negotiation-decision.md",
    "docs/protocol/core-v0.2-session-route-schema-proposal.md",
    "docs/protocol/core-v0.2-stream-binding-schema-proposal.md",
    "docs/protocol/core-v0.2-channel-lifecycle-schema-proposal.md",
    "docs/protocol/core-v0.2-udp-datagram-schema-proposal.md",
    "docs/protocol/core-v0.2-service-channel-exporter.md",
    "nbsr/protocol",
    "scripts/generate_core_v02_vectors.py",
    "scripts/core_v02_vectors",
    "scripts/generate_wp4_exporter_vectors.py",
    "scripts/verify_wp4_exporter_vectors.mjs",
    "tools/core-v02-node-verifier",
    "vectors/core-v0.2",
    "crates/nbsr-transport/src/core_v02.rs",
    "crates/nbsr-transport/src/lib.rs",
    "crates/nbsr-transport/src/session.rs",
    "crates/nbsr-transport/src/admission.rs",
    "crates/nbsr-transport/src/quinn_adapter.rs",
    "crates/nbsr-transport/tests/core_v02_vectors.rs",
]


def files_for_scope(scope: str) -> list[Path]:
    path = ROOT / scope
    if path.is_file():
        return [path]
    return sorted(item for item in path.rglob("*") if item.is_file() and "__pycache__" not in item.parts)


def build() -> dict:
    artifacts: dict[str, dict[str, int | str]] = {}
    for scope in SCOPES:
        for path in files_for_scope(scope):
            data = path.read_bytes()
            artifacts[path.relative_to(ROOT).as_posix()] = {
                "length": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
    return {
        "format_version": 1,
        "baseline_commit": "b1edfa8cd4bb9a2f280e14a2973e404dd8e4c914",
        "inventory_basis": "Core semantic baseline at baseline_commit plus the Task 0 verifier-ownership amendment; this lock is ratified by the Task 0 commit.",
        "task0_amended_paths": [
            "tools/core-v02-node-verifier/README.md",
            "tools/core-v02-node-verifier/lib/manifest.mjs",
            "tools/core-v02-node-verifier/test/verifier.test.mjs",
        ],
        "scopes": SCOPES,
        "external_packages": {
            "vectors/core-v0.2/wp4-exporter": {
                "owner": "scripts/verify_wp4_exporter_vectors.mjs",
                "inventory": "vectors/core-v0.2/wp4-exporter/manifest.json",
            }
        },
        "artifacts": dict(sorted(artifacts.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(build(), indent=2, sort_keys=False) + "\n"
    if args.check:
        return 0 if OUTPUT.read_text(encoding="utf-8") == rendered else 1
    OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
