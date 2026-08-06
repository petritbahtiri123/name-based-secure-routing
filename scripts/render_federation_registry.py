from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/protocol/registries/federation-v0.1-development.json"
OUTPUT = ROOT / "docs/protocol/wp8-federation-v0.1-registry-allocation.md"


def render() -> str:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    lines = [
        "# WP8 Federation v0.1 registry allocation amendment",
        "",
        "**Task 0 status:** Proposed for human approval. These are normative Development Profile proposals, not permanently frozen Federation wire allocations. `WP8-NORMATIVE-SOURCE-01` remains blocking, so Task 1 may not consume them until both the source blocker and human approval gate close.",
        "",
        "The machine-readable authority is `registries/federation-v0.1-development.json`. This document is generated from it by `scripts/render_federation_registry.py`; tests require exact agreement. F105 supplies the semantic family requirement, while this amendment supplies the previously missing names, order, and values.",
        "",
        f"Federation messages occupy extension-local values {source['core_collision_proof']['federation_message_range'][0]} through {source['core_collision_proof']['federation_message_range'][1]}. Frozen Core message values are 1 through 17. The namespaces are disjoint, and a Federation value is never decoded as a Core message. Reserved ranges are unavailable until a later reviewed allocation. Extension ID 1 scopes every Federation registry. This is a Development Profile allocation proposal; permanent reservation waits for schema and vector review.",
        "",
        "Every registry is closed. Unknown, unallocated, or reserved values produce `REJECT/ERR_UNSUPPORTED_CRITICAL` with no state mutation. Core protocol versions, messages, and errors remain in their frozen Core namespaces; Core objects are schema-selected and have no numeric object registry. Federation extension-local values are never Core values.",
        "",
    ]
    for name, entries in source["registries"].items():
        lines.extend([f"## {name.replace('_', ' ').title()}", "", f"<!-- registry:{name} -->"])
        if name == "message_types":
            lines.extend(
                [
                    f"The count is derived from the {len(entries)} semantic entries; no target count applies.",
                    "",
                    "| Value | Name | Family | Class | Senders | Receivers | Allowed state | Replay context | State mutation | Idempotency | Object | Authority effect | Why | Status |",
                    "|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|",
                ]
            )
            for entry in entries:
                metadata = source["message_semantics"][entry["name"]]
                cells = [
                    str(entry["value"]),
                    f"`{entry['name']}`",
                    metadata["family"],
                    metadata["class"],
                    ", ".join(metadata["senders"]),
                    ", ".join(metadata["receivers"]),
                    metadata["allowed_protocol_state"],
                    metadata["replay_context"],
                    metadata["state_mutation"],
                    metadata["idempotency"],
                    metadata["object_type"] or "none",
                    metadata["authority_effect"],
                    metadata["why"],
                    "proposed Development Profile",
                ]
                lines.append("| " + " | ".join(cells) + " |")
        else:
            lines.extend(["| Value | Name | Status |", "|---:|---|---|"])
            for entry in entries:
                lines.append(f"| {entry['value']} | `{entry['name']}` | proposed Development Profile |")
        ranges = source["reserved_ranges"][name]
        rendered = ", ".join(f"{start}..{end}" for start, end in ranges)
        lines.extend(["", f"Reserved: `{rendered}`.", ""])
    lines.extend(
        [
            "## Contextual lifecycle rules",
            "",
            "`recovery_stage` is required exactly when `operator_lifecycle=RECOVERY` and forbidden otherwise. The only wire stages are `RECOVERY_PENDING`, `RECOVERY_VERIFIED`, and `REENTRY_RESTRICTED`. Normal `ACTIVE` follows `REENTRY_RESTRICTED` only after peer synchronization, compatible checkpoints, current revocations, monitoring completion, and readiness approval.",
            "",
            "The labels `REQUESTED`, `EVIDENCE_VERIFIED`, `APPROVED`, `ACTIVATED`, `REENTRY_MONITORING`, `COMPLETE`, and local `REJECTED` are non-wire implementation workflow labels only.",
            "",
            "Lifecycle numbers are identifiers rather than transition ranks. Monotonicity applies to identity generation and record sequence. Allowed transitions are:",
            "",
        ]
    )
    lifecycle = source["operator_lifecycle_semantics"]
    for state, targets in lifecycle["allowed_transitions"].items():
        rendered_targets = ", ".join(f"`{target}`" for target in targets) or "none"
        lines.append(f"- `{state}` -> {rendered_targets}")
    lines.extend(
        [
            "",
            "Recovery stages advance only `RECOVERY_PENDING -> RECOVERY_VERIFIED -> REENTRY_RESTRICTED -> ACTIVE`; skips and rollback reject `ERR_CONTINUITY` without mutation.",
            "",
            "## Approval and claim boundary",
            "",
            "Human approval promotes these entries from proposed values to approved Development Profile values. It does not create permanently frozen wire allocations. That later gate requires closed schemas, literal vectors, cross-verifier agreement, and a separate decision. Production-profile values remain deferred. Task 0 implements no federation runtime and supplies no live federation, governance, interoperability, privacy, or production evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render()
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != rendered:
            sys.stderr.write("registry-render-drift\n")
            return 1
        return 0
    OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
