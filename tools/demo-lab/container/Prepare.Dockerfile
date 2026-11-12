# Explicit network preparation ONLY. All three official references are mandatory.
ARG GO_IMAGE
ARG RUST_IMAGE
ARG PYTHON_IMAGE
FROM ${GO_IMAGE} AS go
FROM ${RUST_IMAGE} AS rust
FROM ${PYTHON_IMAGE} AS prepared
ARG GO_IMAGE
ARG RUST_IMAGE
ARG PYTHON_IMAGE
ARG TARGETARCH
ENV PATH=/usr/local/go/bin:/usr/local/cargo/bin:$PATH     CARGO_HOME=/usr/local/cargo RUSTUP_HOME=/usr/local/rustup     GOTOOLCHAIN=local GOWORK=off GOFLAGS=-mod=readonly GOMAXPROCS=2     CARGO_BUILD_JOBS=2 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1     PYTHONPATH=/src/tools/demo-lab
COPY --from=go /usr/local/go /usr/local/go
COPY --from=rust /usr/local/cargo /usr/local/cargo
COPY --from=rust /usr/local/rustup /usr/local/rustup
WORKDIR /src
COPY . /src/
RUN python3 /src/tools/demo-lab/container/prepare_image.py
# No apt install. The reviewed full Python Debian base must already include cc.
