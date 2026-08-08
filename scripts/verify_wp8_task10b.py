from __future__ import annotations

import json
import sys

from wp8_conformance.runner import Command, ROOT, run_commands


def command_matrix() -> list[Command]:
    python = sys.executable
    return [
        Command("go-peer-dependency-boundary", (python, "-m", "pytest", "tests/federation/test_independent_peer_dependency_boundary.py", "-q"), count_mode="pytest"),
        Command("go-peer-unit", ("go", "test", "-json", "./..."), cwd="interop/nbsr-go-peer", count_mode="go-json"),
        Command("go-peer-vet", ("go", "vet", "./..."), cwd="interop/nbsr-go-peer"),
        Command("go-peer-module-lock", ("go", "mod", "verify"), cwd="interop/nbsr-go-peer", manifest_gate=True),
        Command("independent-wire-live", (python, "-m", "pytest", "tests/federation/test_independent_wire_peer.py", "-q"), count_mode="pytest"),
        Command("git-diff-check", ("git", "diff", "--check")),
    ]


def main() -> int:
    result = run_commands(command_matrix())
    output = ROOT / "evidence/wp8-task10b/conformance-result.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["totals"], sort_keys=True))
    print(f"WP8 Task 10B conformance outcome: {result['outcome']}")
    return 1 if result["outcome"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
