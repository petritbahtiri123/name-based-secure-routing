"""Real signed fixture controls for combined capability/replay rejection.

This tests the offline threshold oracle, not runtime transport or authority.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.verify_federation_threshold_container_fixtures import verify_literal

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("replay", "missing_capability", "expected"),
    [
        (False, False, ("ACCEPT", "NONE", False)),
        (True, False, ("REJECT", "ERR_REPLAY", False)),
        (False, True, ("REJECT", "ERR_UNSUPPORTED_CRITICAL", False)),
        (True, True, ("REJECT", "ERR_UNSUPPORTED_CRITICAL", False)),
    ],
    ids=["valid", "session-replay", "missing-capability", "combined"],
)
def test_capability_rejection_precedes_real_session_replay(replay, missing_capability, expected):
    package = json.loads((ROOT / "vectors/federation-v0.1-threshold-container/literal-fixtures.json").read_bytes())
    fixture = next(item for item in package["fixtures"] if item["name"] == "valid-witness-2-of-3")
    profile = json.loads((ROOT / "docs/protocol/registries/federation-v0.1-threshold-container-proposal.json").read_bytes())
    raw = bytes.fromhex(fixture["canonical_cbor_hex"])
    assert hashlib.sha256(raw).hexdigest() == fixture["sha256"]
    context = deepcopy(fixture["validation_context"])
    if replay:
        original = bytes.fromhex(context["authenticated_session_transcript_digest"])
        changed = bytes([original[0] ^ 1]) + original[1:]
        context["authenticated_session_transcript_digest"] = changed.hex()
    if missing_capability:
        context["negotiated_capabilities"] = []
        context["authenticated_capabilities"] = []
    before = deepcopy(context)
    assert verify_literal(raw, context, profile) == expected
    assert context == before
    assert hashlib.sha256(raw).hexdigest() == fixture["sha256"]
