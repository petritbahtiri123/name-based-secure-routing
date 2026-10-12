"""Generate explicitly approved development-only connector envelope vectors."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from nbsr.connector_registration_offline import canonical, decode_body

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "vectors/connector-registration-development-v1"
REGISTRY = ROOT / "docs/protocol/registries/connector-registration-development-v1.json"
PROFILE = "connector-registration-development-v1"
ALPN = "nbsr-connector-dev-1"
KINDS = dict(zip(("REQUEST", "CHALLENGE", "PROOF", "ACCEPT", "REJECT", "WITHDRAW"), range(24576, 24582)))


def artifacts():
    registry = {
        "format_version": 1,
        "profile": PROFILE,
        "status": "APPROVED DEVELOPMENT ONLY - IN-MEMORY TESTS",
        "runtime_authorized": False,
        "live_trust_authorized": False,
        "alpn": ALPN,
        "envelope_version": 1,
        "message_namespace": "connector-development-local; never Core or Federation message decoding",
        "messages": KINDS,
        "actions": {
            "namespace": PROFILE,
            "CONNECTOR_REGISTER": 24576,
            "effects": ["register", "renew"],
            "excludes": ["publication", "route grants", "delegation", "application admission"],
        },
        "signer_purposes": {"transport": 14, "delegation": 6, "bilateral_authorization": 11},
        "envelope_keys": {
            "0": "connector version",
            "1": "message",
            "2": "request_id",
            "3": "session_id",
            "4": "directional sequence",
            "5": "body",
        },
        "unknown_policy": "reject before mutation; no Core ALPN/version fallback",
        "exporter_label": "EXPORTER-NBSR-Connector-Registration-v1",
    }
    files = {}
    cases = []

    def add(name, body, accepted=True, alpn=ALPN):
        filename = name + ".cbor"
        files[filename] = canonical(body)
        cases.append({"file": filename, "accepted": accepted, "alpn": alpn})

    for kind, code in KINDS.items():
        body = decode_body(kind, (ROOT / "vectors/connector-registration-v1-counter" / (kind.lower() + ".cbor")).read_bytes())
        envelope = {0: 1, 1: code, 2: b"s" * 8 + (1).to_bytes(8, "big"), 3: b"s" * 16, 4: 1, 5: body}
        add(kind.lower(), envelope)
        if kind == "REQUEST":
            request = envelope
    for name, key, value in [
        ("unknown-version", 0, 2),
        ("unknown-message", 1, 24582),
        ("core-message", 1, 1),
        ("zero-sequence", 4, 0),
        ("bool-sequence", 4, True),
        ("bad-request-prefix", 2, b"x" * 16),
        ("zero-counter", 2, b"s" * 8 + b"\0" * 8),
        ("extra-key", 6, 0),
    ]:
        add(name, request | {key: value}, False)
    add("wrong-alpn", request, False, "nbsr-quic-1")
    for name, key, value in [
        ("wrong-gateway", 6, "22" * 32),
        ("bool-lease", 13, True),
        ("long-lease", 13, 61),
        ("missing-authority-refs", 10, []),
    ]:
        add(name, request | {5: request[5] | {key: value}}, False)
    for name, raw in [
        ("trailing", files["request.cbor"] + b"\0"),
        ("nonpreferred", b"\xb8\x06" + files["request.cbor"][1:]),
        ("indefinite", b"\xbf" + files["request.cbor"][1:] + b"\xff"),
    ]:
        files[name + ".cbor"] = raw
        cases.append({"file": name + ".cbor", "accepted": False, "alpn": ALPN})
    rejected = decode_body("REJECT", (ROOT / "vectors/connector-registration-v1-counter/reject.cbor").read_bytes())
    for name, key, value in [
        ("reject-correlation", 2, b"s" * 8 + (2).to_bytes(8, "big")),
        ("reject-zero-retry", 4, 0),
        ("reject-forbidden-retry", 4, 1),
    ]:
        add(name, request | {1: KINDS["REJECT"], 5: rejected | {2: rejected[2] | {key: value}}}, False)
    manifest = {
        "profile": PROFILE,
        "alpn": ALPN,
        "status": "IN-MEMORY FIXTURES; NO LIVE TRUST",
        "cases": cases,
        "artifacts": {n: {"sha256": sha256(b).hexdigest(), "bytes": len(b)} for n, b in files.items()},
    }
    files["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    return registry, files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    registry, files = artifacts()
    outputs = {REGISTRY: (json.dumps(registry, indent=2) + "\n").encode(), **{PACKAGE / n: b for n, b in files.items()}}
    for path, raw in outputs.items():
        if args.check:
            assert path.read_bytes() == raw, path
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    print(f"{len(outputs)} development artifacts verified" if args.check else f"{len(outputs)} development artifacts written")


if __name__ == "__main__":
    main()
