from __future__ import annotations

import json
import sys
from wp8_conformance.runner import Command, ROOT, run_commands


def command_matrix() -> list[Command]:
    python = sys.executable
    return [
        Command("core-v02-original-baseline-lock", (python, "scripts/verify_f75_core_overlay.py", "original", "."), manifest_gate=True),
        Command("f75-additive-overlay", (python, "scripts/verify_f75_core_overlay.py", "overlay", "."), manifest_gate=True),
        Command("f75-manifest", (python, "scripts/generate_wp8_f75_vectors.py", "--check", "vectors/wp8-f75-route-open"), manifest_gate=True),
        Command("local-admission-attestations", (python, "scripts/generate_wp8_local_admission_attestations.py", "--check"), manifest_gate=True),
        Command("federation-v01-manifest", (python, "scripts/generate_federation_v01_vectors.py", "--check", "vectors/federation-v0.1"), manifest_gate=True),
        Command("schema-literals", (python, "scripts/verify_federation_schema_fixtures.py"), manifest_gate=True),
        Command("threshold-literals", (python, "scripts/verify_federation_threshold_container_fixtures.py", "--check"), manifest_gate=True),
        Command("f75-python", (python, "-m", "pytest", "tests/protocol/test_wp8_f75_vectors.py", "-q"), count_mode="pytest"),
        Command("f75-node", ("node", "scripts/verify_wp8_f75_vectors.mjs", "vectors/wp8-f75-route-open")),
        Command("federation-python", (python, "-m", "pytest", "tests/federation", "--ignore=tests/federation/test_independent_wire_peer.py", "-q"), count_mode="pytest"),
        Command("wp7-python", (python, "-m", "pytest", "tests/test_wp7_admission.py", "tests/test_wp7_conformance.py", "tests/test_wp7_review_fixes.py", "-q"), count_mode="pytest"),
        Command("packet-evidence", (python, "-m", "pytest", "tests/federation/test_packet_evidence.py", "-q"), count_mode="pytest"),
        Command("full-python", (python, "-m", "pytest", "--ignore=tests/federation/test_independent_wire_peer.py", "-q"), count_mode="pytest"),
        Command("ruff", (python, "-m", "ruff", "check", ".")),
        Command("pip-check", (python, "-m", "pip", "check")),
        Command("dependency-inspection", (python, "scripts/verify_wp8_repository_safety.py", "dependencies", "."), manifest_gate=True),
        Command("repository-privacy-secret-scan", (python, "scripts/verify_wp8_repository_safety.py", "privacy", "."), manifest_gate=True),
        Command("node-federation-tests", ("npm", "test"), cwd="verifiers/federation-node", count_mode="tap"),
        Command("node-federation-verify", ("npm", "run", "verify"), cwd="verifiers/federation-node"),
        Command("node-core-tests", ("npm", "test"), cwd="tools/core-v02-node-verifier", count_mode="tap"),
        Command("node-core-verify", ("npm", "run", "verify"), cwd="tools/core-v02-node-verifier"),
        Command("wp4-exporter", ("node", "scripts/verify_wp4_exporter_vectors.mjs", "vectors/core-v0.2/wp4-exporter")),
        Command("go-federation-tests", ("go", "test", "-json", "./..."), cwd="verifiers/federation-go", count_mode="go-json"),
        Command("go-federation-vet", ("go", "vet", "./..."), cwd="verifiers/federation-go"),
        Command("rust-format", ("cargo", "fmt", "--manifest-path", "crates/nbsr-transport/Cargo.toml", "--", "--check")),
        Command("rust-clippy", ("cargo", "clippy", "--manifest-path", "crates/nbsr-transport/Cargo.toml", "--all-targets", "--", "-D", "warnings")),
        Command("rust-all", ("cargo", "test", "--manifest-path", "crates/nbsr-transport/Cargo.toml"), count_mode="rust"),
        Command("documentation", (python, "-m", "pytest", "tests/federation/test_runtime_documentation.py", "-q"), count_mode="pytest"),
        Command("git-diff-check", ("git", "diff", "--check")),
        Command("independent-wire-peer", (python, "scripts/verify_wp8_task10b.py")),
    ]


def main() -> int:
    result = run_commands(command_matrix())
    output = ROOT / "evidence/wp8-task10/conformance-result.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["totals"], sort_keys=True))
    print(f"WP8 conformance outcome: {result['outcome']}")
    return 1 if result["outcome"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
