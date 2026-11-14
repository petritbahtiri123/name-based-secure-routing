"""Diagnostic comparison only; neither codec selects NBSR's normative profile."""
import encodings.idna
import hashlib
import json
from pathlib import Path
import sys

import idna


def outcome(call):
    try:
        value = call()
        return {"accepted": True, "value": value}
    except UnicodeError as exc:
        return {"accepted": False, "error": str(exc), "error_type": type(exc).__name__}


def main():
    expected = {
        "xn--a": ("\u0080", False, False),
        "xn--fa-hia": ("fa\u00df", False, True),
        "xn--bcher-kva": ("b\u00fccher", True, True),
        "xn--invalid": (None, True, True),
    }
    rows = []
    for label, (decoded, legacy_ok, modern_ok) in expected.items():
        raw = label[4:].encode("ascii").decode("punycode")
        if decoded is not None:
            assert raw == decoded
        # ASCII ToASCII alone does not establish ACE validity.
        ascii_only = label.encode("idna").decode("ascii")
        legacy = outcome(lambda: label.encode("ascii").decode("idna"))
        modern = outcome(lambda: idna.decode(label, strict=True, uts46=False))
        assert legacy["accepted"] == legacy_ok
        assert modern["accepted"] == modern_ok
        assert ascii_only == label
        if modern_ok:
            assert idna.encode(modern["value"], strict=True, uts46=False).decode("ascii") == label
        rows.append({"label": label, "punycode_codepoints": [f"U+{ord(c):04X}" for c in raw],
                     "raw_punycode": raw, "stdlib_ascii_encode": ascii_only,
                     "stdlib_decode": legacy, "idna2008_decode": modern})
    assert encodings.idna.nameprep("fa\u00df") == "fass"
    assert "fa\u00df".encode("idna") == b"fass"
    assert idna.encode("fa\u00df", strict=True, uts46=False) == b"xn--fa-hia"
    domain = b"NBSR-FEDERATION-SERVICE-ID-v1\x00"
    # Public synthetic owner, raw formula only; no signing or validation claim.
    owner = bytes(32)
    ids = {}
    for name in [b"xn--fa-hia.example", b"fass.example"]:
        ids[name.decode()] = hashlib.sha256(domain + owner + len(name).to_bytes(2, "big") + name).hexdigest()
    assert len(set(ids.values())) == 2
    print(json.dumps({"python": sys.version, "installed_idna_version": idna.__version__,
                      "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      "scope": "codec comparison, not approved NBSR profile or signed admission",
                      "cases": rows, "synthetic_service_id_formula": ids}, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
