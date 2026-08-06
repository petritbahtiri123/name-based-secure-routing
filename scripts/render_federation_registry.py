from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/protocol/registries/federation-v0.1-development.json"
OUTPUT = ROOT / "docs/protocol/wp8-federation-v0.1-registry-allocation.md"


def render() -> str:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    lines = [
        "# WP8 Federation v0.1 registry allocation amendment",
        "",
        "**Task 0 status:** Proposed for human approval. These are normative Development Profile proposals, not permanently frozen Federation wire allocations. Task 1 may consume them only after approval.",
        "",
        "The machine-readable authority is `registries/federation-v0.1-development.json`. This document is generated from it by `scripts/render_federation_registry.py`; tests require exact agreement. F105 supplies the semantic family requirement, while this amendment supplies the previously missing names, order, and values.",
        "",
        "Federation messages occupy extension-local values 16384 through 16417. Frozen Core message values are 1 through 17. The namespaces are disjoint, and a Federation value is never decoded as a Core message. Reserved ranges are unavailable until a later reviewed allocation. Extension ID 1 scopes every Federation registry. This is a Development Profile allocation proposal; permanent reservation waits for schema and vector review.",
        "",
        "Every registry is closed. Unknown, unallocated, or reserved values produce `REJECT/ERR_UNSUPPORTED_CRITICAL` with no state mutation. Core protocol versions, messages, and errors remain in their frozen Core namespaces; Core objects are schema-selected and have no numeric object registry. Federation extension-local values are never Core values.",
        "",
    ]
    for name, entries in source["registries"].items():
        lines.extend(
            [
                f"## {name.replace('_', ' ').title()}",
                "",
                f"<!-- registry:{name} -->",
                "| Value | Name | Status |",
                "|---:|---|---|",
            ]
        )
        for entry in entries:
            lines.append(f"| {entry['value']} | `{entry['name']}` | proposed Development Profile |")
        ranges = source["reserved_ranges"][name]
        rendered = ", ".join(f"{start}..{end}" for start, end in ranges)
        lines.extend(["", f"Reserved: `{rendered}`.", ""])
    lines.extend(
        [
            "## Approval and claim boundary",
            "",
            "Human approval promotes these entries from proposed values to approved Development Profile values. It does not create permanently frozen wire allocations. That later gate requires closed schemas, literal vectors, cross-verifier agreement, and a separate decision. Production-profile values remain deferred. Task 0 implements no federation runtime and supplies no live federation, governance, interoperability, privacy, or production evidence.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    OUTPUT.write_text(render(), encoding="utf-8", newline="\n")
