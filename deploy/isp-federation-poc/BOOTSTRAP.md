# Pinned Linux bootstrap

`base-images.json` contains verified official Docker Library Linux/amd64 manifest digests for Go 1.26.5 Bookworm, Rust 1.97.1 Bookworm and Python 3.14.6 slim Bookworm. The registry tags were inspected before the digest pulls; raw manifests, pull/inspect logs and wheel evidence are retained at `C:/NBSR-build/isp-bootstrap-20260906`.

The Go modules declare `go 1.26.5`. Rust declares edition 2024 but no explicit `rust-version` or toolchain file; 1.97.1 matches the locally used compiler, and the locked full Rust build remains a separate acceptance gate. Python declares `>=3.12,<3.15`. Both Rust builder and Python runtime use Debian Bookworm, avoiding a newer-builder/older-runtime glibc pairing. This lock is specific to CPython 3.14 Linux/amd64, not a universal Python lock.

`requirements.in` pins the eight existing project runtime dependencies plus pytest to versions observed in the accepted local environment and within `pyproject.toml` constraints. Linux pip resolution selected 28 wheels. `requirements.lock` records every direct/transitive version and the SHA-256 of the actual Linux wheel; the external `wheel-manifest.json` records names and hashes. No additional dev tools or project build backend are needed because the runtime copies source instead of installing the project package. The build installs with `--only-binary=:all: --require-hashes`, then `pip check`; wheel substitution, missing dependencies or unavailable hashes fail the build.

## Reproduce base prerequisites

After measurement clearance, from the repository root in PowerShell:

```powershell
$ispBases = Get-Content deploy/isp-federation-poc/base-images.json -Raw | ConvertFrom-Json
foreach ($ispBase in @($ispBases.go, $ispBases.rust, $ispBases.python)) {
    docker pull --platform linux/amd64 $ispBase
    if ($LASTEXITCODE -ne 0) { throw 'Pinned base pull failed' }
    docker image inspect $ispBase
    if ($LASTEXITCODE -ne 0) { throw 'Pinned base inspect failed' }
}
```

These commands pull fixed public digests; they do not push images, remove existing resources or change Docker configuration. `prepare.py` independently verifies each reference exists in local `RepoDigests`. No local dependency-image tag is passed as the Python base.

## Dependency-only check

```powershell
docker build --pull=false --file deploy/isp-federation-poc/Dockerfile --target python-deps --tag nbsr-isp-poc-python-deps:bootstrap-20260906 --build-arg "GO_IMAGE=$($ispBases.go)" --build-arg "RUST_IMAGE=$($ispBases.rust)" --build-arg "PYTHON_IMAGE=$($ispBases.python)" .
if ($LASTEXITCODE -ne 0) { throw 'Dependency stage failed' }
```

The bootstrap reproduced a literal RED (`ModuleNotFoundError: pytest`) in the official Python base, then built this stage and passed imports of pytest, cryptography, cbor2, the authority helper and both selected federation test modules in a network-disabled container. Full runtime/adapter builds and topology execution are separate gates, not implied by this dependency check.

## Full build after clean-source acceptance

Select a fresh run ID/output and a dedicated nonoverlapping RFC1918 subnet, then use the same resolved base values:

```powershell
python deploy/isp-federation-poc/prepare.py --go-image $ispBases.go --rust-image $ispBases.rust --python-image $ispBases.python --private-cidr 172.29.248.0/24 --run-id nbsr-isp-poc-bootstrap-20260906 --output C:/NBSR-build/isp-prepare-20260906
```

The example subnet is a candidate, not an assertion that it is free: prepare rejects an existing overlapping Docker network before building. It also rejects a dirty/changing checkout and an existing output directory. Retain its command logs and final image IDs. Do not run the full build before the accepted clean SHA is committed.

To refresh dependencies intentionally, resolve `requirements.in` inside the pinned Python image using `python -m pip download --only-binary=:all:` into a fresh external wheelhouse, read each wheel's METADATA name/version, and record its SHA-256 in a new complete lock. Recheck project constraints and the selected tests before accepting changed pins. Ordinary builds consume the existing lock and do not resolve floating dependencies.
