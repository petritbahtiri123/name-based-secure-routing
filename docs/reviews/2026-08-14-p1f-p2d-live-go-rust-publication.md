# P1F/P2D live Go-to-Rust publication verification

Date: 2026-08-14  
Branch: `codex/nbsr-v3-wp0-wp1`  
Source commit: `11565de27a6dd642cd7c9f0b4de81655eec3c5e1`  
Source tree: `ce98f30e3b2970386a85ed6a784b589fa404cf25`  
Frozen `main`: `1938154d498b32d81a3564319969430644e8a688`  
P1F/P2D authority: `7a33b7d6dd87031018563da0e8d2b1857515bc3ae2427094a6967d9e6329d3e4`

## Outcome

The committed source candidate passed the real cross-process Go-to-Rust wire matrix, the repository-wide Ruff baseline, and every mandatory fresh verification gate. The authority chain remains `baseline -> unchanged F75 -> P1F/P2D overlay`; no protocol, message-number, replay, or Stream Credit semantics changed.

## Exact build binding

The repository remained in OneDrive, but every live build and runtime artifact was written beneath `C:\NBSR-build\live-wire-closure-final`.

| Item | Value |
| --- | --- |
| Rust binary | `C:\NBSR-build\live-wire-closure-final\cargo-target\release\wp8_interop_server.exe` |
| Rust SHA-256 | `a0c30db7a66839769166d36a5343a5d06c895b76fca576782fc1afd4af1da05a` |
| Go binary | `C:\NBSR-build\live-wire-closure-final\go\nbsr-go-peer.exe` |
| Go SHA-256 | `c755fd11649920a4892ed978871cdc8c8997cc9662f8ba969f98571891492399` |
| Rust | `rustc 1.97.1 (8bab26f4f 2026-07-14)`; LLVM 22.1.6; `x86_64-pc-windows-msvc` |
| Cargo | `cargo 1.97.1 (c980f4866 2026-06-30)` |
| Go | `go1.26.5 windows/amd64` |
| Python | `3.14.6` |

Build commands:

```text
cargo build --release --features benchmark-harness --manifest-path crates/nbsr-transport/Cargo.toml --bin wp8_interop_server --target-dir C:\NBSR-build\live-wire-closure-final\cargo-target
go build -trimpath -o C:\NBSR-build\live-wire-closure-final\go\nbsr-go-peer.exe ./cmd/nbsr-go-peer
```

## Live topology and positive result

`Go peer process -> QUIC v1 / TLS 1.3 / nbsr-quic-1 -> Rust server process`

The approved case used `127.0.0.1:56578`, Go exit `0`, and Rust PID `1356` / exit `0`. The live sequence was `CLIENT_HELLO`, `EDGE_HELLO`, `ROUTE_OPEN`, `ROUTE_ACCEPT`, `STREAM_CREDIT_PREFACE`, and `STREAM_CREDIT_ACCEPT`. Rust consumed the Go-produced credited preface under `nbsr-stream-credit-1`, then verified a 1,024-byte payload with SHA-256 `e8fb68ce4d4d002dba40c0a459d96807c96ded1c2fdefae3f56f8a0c06a4fecf`. The result recorded one completed operation, one replay entry, replay limit 10,000, 63 credits remaining, zero errors, and payload correctness `true`. The Go peer sends application payload only after live ACCEPT.

## Negative live results and exit 101

| Case | Endpoint | Go exit/observation | Rust PID/exit | Rust typed result | Payload exposed |
| --- | --- | --- | --- | --- | --- |
| Malformed credited preface | `127.0.0.1:56581` | `1`; admission rejected | `10952` / `0` | `APPLICATION_STREAM_REJECTED` | `false` |
| Credit profile/version mismatch | `127.0.0.1:56584` | `1`; admission rejected | `11860` / `0` | `APPLICATION_STREAM_REJECTED` | `false` |
| Required-credit Legacy downgrade | `127.0.0.1:56587` | `1`; admission rejected | `8956` / `0` | `APPLICATION_STREAM_REJECTED` | `false` |

The former Rust exit `101` was caused by `unwrap()` calls in the one-shot benchmark/interop binary after the transport adapter correctly returned a typed rejection. It was a harness panic, not a panic in the production-equivalent Quinn admission handler. The harness now handles the existing rejection result, emits a typed JSON result, and exits `0`; this is an implementation-only availability correction and changes no wire behavior.

The binary is intentionally one-shot (`accept_one` once), so it is not evidence of a long-lived production server architecture. Long-lived production-equivalent behavior is proved at the adapter/connection boundary by focused integration regressions: malformed early bytes are rejected and a later valid credit succeeds on the same connection; a Legacy open is rejected without state mutation and a credited retry succeeds on the same connection. No rejected attempt exposes application payload.

## Ruff baseline reconciliation

The dirty starting worktree reproduced 27 lint violations and 61 formatting candidates. The committed starting tree alone contains 60 formatting candidates; the additional candidate was the new live-verification script in the preserved working changes.

The intended policy is repository-wide: `pyproject.toml` sets Ruff's line length and Python target, while repository documentation and CI-facing guidance invoke `python -m ruff check .` and `python -m ruff format --check .`. There were no prior Ruff exclusions. All candidates were ordinary active source, tests, or tooling, so no generated, vendored, immutable-evidence, legacy, or unknown file was excluded.

Formatting classification: 2 `ACTIVE_SOURCE`, 25 `ACTIVE_TEST`, and 34 `TOOLING/SCRIPT` files across the dirty-worktree set of 61. The 60 baseline files were formatted by an explicit reviewed path list; the live runner was formatted during its focused edit. No broad `ruff format .` mutation was used. AST comparison for the 56 formatting-only tracked files found all 56 equivalent. No Ruff configuration or exclusion changed.

All 27 lint findings and their minimal remediation were:

| File and original location(s) | Rule/count | Original code shape | Remediation | Runtime behavior |
| --- | --- | --- | --- | --- |
| `scripts/build_p2a_report.py:56,121,123` | E702 x3 | sequential statements joined by semicolons | split into separate statements | unchanged |
| `scripts/performance/session_rotation_model.py:113` | F841 x1 | unused local `old` assignment | remove unused binding | unchanged |
| `scripts/run_p2a_established.py:12` | F401 x1 | unused `time` import | remove import | unchanged |
| `scripts/run_p2a_established.py:150,169 (x2),176 (x2)` | E702 x5 | sequential statements joined by semicolons | split into separate statements | unchanged |
| `scripts/run_p2a_established.py:188` | E731 x1 | lambda assigned to a local name | equivalent local `def` | unchanged |
| `scripts/run_p2b_profile.py:4,12` | F401 x2 | unused `asdict` and `time` imports | remove imports | unchanged |
| `scripts/run_p2b_profile.py:99,100,104,105,106,183,184,185,196` | E701 x9 | compound statements on one line after a colon | expand blocks | unchanged |
| `scripts/run_p2b_profile.py:128,179,182 (x2)` | E702 x4 | sequential statements joined by semicolons | split into separate statements | unchanged |
| `scripts/run_p2b_profile.py:119` | E731 x1 | lambda assigned to a local name | equivalent local `def` | unchanged |

Final results: `ruff check .` reports `All checks passed!`; `ruff format --check .` reports `279 files already formatted`.

## Fresh verification gates

| Gate | Fresh result |
| --- | --- |
| Full Python | 1,847 passed, 1 skipped; 0 failed |
| Federation Python | 576 passed; 0 failed |
| Focused reconciliation tests | 42 passed; 0 failed |
| Rust default | 188 passed, 1 ignored; 0 failed |
| Rust all-targets + `benchmark-harness` | 180 passed, 1 ignored; 0 failed |
| Rust format | PASS |
| Rust Clippy all-targets + feature, `-D warnings` | PASS |
| Go tests | PASS across seven tested packages; transport has no test files |
| Go vet | PASS |
| Go module verification | PASS (`all modules verified`) |
| Federation vectors | PASS; 9 package files verified |
| F75 Node parity vectors | PASS; binding, transcript, digest, signature |
| Core v0.2 vectors | PASS |
| P1F/P2D Stream Credit vectors | PASS in Rust default and feature matrices |
| Ruff check / format check | PASS / PASS |
| `git diff --check` | PASS |
| Git LFS fsck | PASS |
| Accepted P1A-P2D evidence diff | empty |

## Evidence boundaries

- **Live evidence:** independent Go and Rust OS processes, real QUIC v1/TLS 1.3 transport, live control exchange, credited admission, ACCEPT-gated payload, and three live negative cases.
- **Fixture/config evidence:** certificates, signed authority/profile material, expected route data, and deterministic test inputs are fixture/config driven. They select the approved authority but do not substitute for wire traffic.
- **Deterministic-vector evidence:** federation, F75 Node, Core v0.2, and Rust Stream Credit vectors verify stable encodings and authority/profile behavior; they are not the live run.
- **Inherited benchmark evidence:** accepted Attempt 8 remains immutable: 4,282.05 to 15,567.44 ops/s (+263.55%), p99 18.6981 to 5.4623 ms, 300.387-second soak, 4,832,000 successful lifecycles, replay limit 10,000. Those results were not regenerated or modified.

## Non-claims

The Go implementation used here is the current interop/benchmark peer. This proves cross-language interoperability, cross-process credited wire compatibility, authority/profile compatibility, and real Rust consumption of Go-produced protocol material. It does not prove production Go client readiness, WAN readiness, production capacity, resolver integration, router deployment, session rotation/recovery, or full end-to-end production rollout behavior.
