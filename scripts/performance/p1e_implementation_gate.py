"""Repository-backed P1E production implementation feasibility gate."""

from __future__ import annotations

import json
from pathlib import Path
import re


_NON_PRODUCTION_GO_ROOTS = {"interop", "verifiers"}


def _relative_files(root: Path, pattern: str) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob(pattern))


def evaluate_repository(root: Path) -> dict[str, object]:
    root = root.resolve()
    go_modules = _relative_files(root, "go.mod")
    go_files = [Path(path) for path in _relative_files(root, "*.go")]
    production_go_files = sorted(path.as_posix() for path in go_files if path.parts[0] not in _NON_PRODUCTION_GO_ROOTS)

    peer_main_path = root / "interop/nbsr-go-peer/cmd/nbsr-go-peer/main.go"
    peer_transport_path = root / "interop/nbsr-go-peer/internal/transport/quic.go"
    peer_main = peer_main_path.read_text(encoding="utf-8")
    peer_transport = peer_transport_path.read_text(encoding="utf-8")
    wire_capable = "transport.Dial(" in peer_main and "quic.DialAddr" in peer_transport
    fixture_authority = (
        '"route-open-body.cbor"' in peer_main and "mustRead(filepath.Join(" in peer_main and "VerifyRouteGrant(exactGrant" in peer_main
    )

    core_path = root / "interop/nbsr-go-peer/internal/core/core.go"
    core_source = core_path.read_text(encoding="utf-8")
    constant_block = core_source.split("const (", 1)[1].split(")", 1)[0]
    message_names = re.findall(r"^\s*([A-Z][A-Za-z]+)\s+MessageType", constant_block, re.MULTILINE)
    acquisition_messages = sorted(name for name in message_names if "Grant" in name or "Authority" in name)

    channel_streams = (root / "crates/nbsr-transport/src/channel_streams.rs").read_text(encoding="utf-8")
    stream_gate = (root / "crates/nbsr-transport/src/stream_gate.rs").read_text(encoding="utf-8")
    rust_cap_expressible = "fn prepare_open" in channel_streams and "OverCapacity" in stream_gate
    production_owner_exists = bool(production_go_files)
    live_acquisition_exists = bool(acquisition_messages)
    coordinated_fix_expressible = production_owner_exists and live_acquisition_exists

    return {
        "schema_version": 1,
        "go_modules": go_modules,
        "production_go_files": production_go_files,
        "wire_capable_go_owner": "interop_test_peer_only" if wire_capable else "none",
        "go_route_grant_source": {
            "kind": "filesystem_fixture" if fixture_authority else "unknown",
            "path_component": "route-open-body.cbor" if fixture_authority else None,
            "live_acquisition_api": live_acquisition_exists,
        },
        "core_route_grant_acquisition_messages": acquisition_messages,
        "rust_hard_cap": {
            "insertion_point": "ChannelStreams.prepare_open" if rust_cap_expressible else None,
            "typed_error": "StreamReject::OverCapacity" if rust_cap_expressible else None,
            "wire_change_required": not rust_cap_expressible,
        },
        "partial_rust_only_fix_authorized": False,
        "production_implementation_authorized": coordinated_fix_expressible,
        "outcome": "IMPLEMENT" if coordinated_fix_expressible else "C",
        "classification": ("IMPLEMENTATION_GATE_PASSED" if coordinated_fix_expressible else "CODE_LEVEL_PROTOCOL_BLOCKED"),
        "missing_contract": (
            None
            if coordinated_fix_expressible
            else "A production Go client/agent API and live fresh-RouteGrant acquisition "
            "contract for TS-B; the repository only supplies offline fixture bytes "
            "and Core v0.2 defines no acquisition exchange."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(evaluate_repository(Path.cwd()), indent=2, sort_keys=True))
