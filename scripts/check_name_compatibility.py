"""Bounded diagnostic of existing predicates; observations are not an IDNA policy.

Run with --source-root pointing at the checkout and --output at a fresh directory.
Uses installed Python dependencies and rustc only; no Cargo or network access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time


def section(source: str, start: str, end: str) -> str:
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError(f"source structure changed: {start}")
    return start + source.split(start, 1)[1].split(end, 1)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    sys.dont_write_bytecode = True
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    deadline = started + 95

    def run(command: list[str], input_text: str | None = None, **kwargs) -> str:
        process = subprocess.Popen(command, stdin=subprocess.PIPE if input_text is not None else None,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                   start_new_session=os.name != "nt", **kwargs)
        try:
            stdout, stderr = process.communicate(input_text, timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=10)
            (out / "timeout.log").write_text(stdout + stderr)
            raise
        with (out / "commands.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps({"command": command, "exit": process.returncode, "stdout": stdout, "stderr": stderr}) + "\n")
        if process.returncode:
            raise RuntimeError(f"command failed: {command}; see commands.jsonl")
        return stdout

    corpus = json.loads((Path(__file__).parent.parent / "tests/fixtures/name-compatibility.json").read_text())
    sys.path.insert(0, str(root))
    from nbsr.federation.ownership import _canonical_name
    from nbsr.federation.fields import _delegation_scope, FederationValidationError
    from nbsr.protocol.cbor import encode_deterministic

    federation = (root / "crates/nbsr-transport/src/federation.rs").read_text()
    connector = (root / "crates/nbsr-transport/src/connector_control.rs").read_text()
    chunks = ["use std::collections::BTreeMap;\n",
              section(connector, "pub type Result<T>", "pub fn bytes("),
              section(connector, "fn head(", "pub fn validate_body("),
              connector[connector.index("pub fn decode_value("):],
              section(federation, "fn valid_canonical_name(", "fn service_id(")]
    # The tail must remain exactly one function; rustc rejects unexpected dependencies.
    chunks.append('''
fn main() {
    for name in std::io::stdin().lines() {
        let name = name.unwrap();
        let wire = encode(&Value::Text(name.clone()));
        println!("{} {}", valid_canonical_name(&name), decode_value(&wire).is_ok());
    }
}
''')
    probe = out / "probe.rs"
    probe.write_text("\n".join(chunks), encoding="utf-8")
    initial_free = shutil.disk_usage(out).free
    if initial_free < 8 * 1024**3:
        raise RuntimeError("less than 8 GiB free")
    binary = out / ("probe.exe" if os.name == "nt" else "probe")
    rust_version = run(["rustc", "--version"])
    run(["rustc", "--edition=2024", "-C", "codegen-units=1", str(probe), "-o", str(binary)])
    remaining_free = shutil.disk_usage(out).free
    if remaining_free < 6 * 1024**3 or initial_free - remaining_free >= 2 * 1024**3:
        raise RuntimeError("disk resource bound exceeded")
    names = [case["name"] for case in corpus["cases"]]
    # No embedded newlines are permitted in this line-framed diagnostic corpus.
    assert all("\n" not in name and "\r" not in name for name in names)
    native = run([str(binary)], input_text="\n".join(names) + "\n").splitlines()
    assert len(native) == len(names)
    results = []
    for case, line in zip(corpus["cases"], native, strict=True):
        name = case["name"]
        def accepts(function, value):
            try:
                function(value)
            except FederationValidationError:
                return False
            return True
        scope = {1: name, 2: None, 3: None, 4: None, 5: None, 6: None,
                 7: [], 8: [1], 9: [1], 10: False, 11: 0}
        # A valid control ensures unrelated scope fields cannot mask name acceptance.
        _delegation_scope({**scope, 1: "service.example"})
        rust_name, rust_text = [item == "true" for item in line.split()]
        observed = [accepts(_canonical_name, name), accepts(_delegation_scope, scope), rust_name, rust_text]
        results.append({**case, "utf8_bytes": len(name.encode()), "cbor_hex": encode_deterministic(name).hex(), "observed": observed})
    source_paths = ["crates/nbsr-transport/src/federation.rs", "crates/nbsr-transport/src/connector_control.rs",
                    "nbsr/federation/ownership.py", "nbsr/federation/fields.py", "nbsr/protocol/cbor.py"]
    hashes = {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in source_paths}
    report = {"python": sys.version, "rustc": rust_version.strip(), "source_root": str(root),
              "source_sha256": hashes, "probe_sha256": hashlib.sha256(probe.read_bytes()).hexdigest(),
              "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
              "elapsed_seconds": time.monotonic() - started, "results": results}
    (out / "observed.json").write_text(json.dumps(report, indent=2) + "\n")
    failures = [row["id"] for row in results if row["observed"] != row["expected"]]
    if failures:
        raise AssertionError(f"observations changed: {failures}")
    print(f"{len(results)} observations matched; see {out / 'observed.json'}")


if __name__ == "__main__":
    main()
