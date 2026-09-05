# Required immutable base references are validated by prepare.py before builds.
ARG GO_IMAGE
ARG RUST_IMAGE
ARG PYTHON_IMAGE
FROM ${GO_IMAGE} AS go-build
WORKDIR /src
COPY client/nbsr-go-client /src/client/nbsr-go-client
COPY interop/nbsr-go-peer /src/interop/nbsr-go-peer
COPY deploy/isp-federation-poc/adapter /src/deploy/isp-federation-poc/adapter
COPY deploy/isp-federation-poc/origin-connector /src/deploy/isp-federation-poc/origin-connector
RUN mkdir /out && cd /src/client/nbsr-go-client/demo && \
    CGO_ENABLED=0 go build -mod=readonly -o /out/nbsr-demo-authority ./cmd/nbsr-demo-authority && \
    CGO_ENABLED=0 go build -mod=readonly -o /out/nbsr-demo-client ./cmd/nbsr-demo-client && \
    cd /src/deploy/isp-federation-poc/adapter && \
    CGO_ENABLED=0 go build -mod=readonly -trimpath -o /out/isp-a-tcp ./cmd/isp-a-tcp && \
    CGO_ENABLED=0 go build -mod=readonly -trimpath -o /out/isp-b-udp ./cmd/isp-b-udp && \
    CGO_ENABLED=0 go build -trimpath -o /out/origin-connector /src/deploy/isp-federation-poc/origin-connector/main.go

FROM ${RUST_IMAGE} AS rust-build
ENV CARGO_TARGET_DIR=/cargo-target
WORKDIR /src
COPY crates/nbsr-transport /src/crates/nbsr-transport
RUN cargo build --locked --release --manifest-path crates/nbsr-transport/Cargo.toml --bin wp8_interop_server

# Official Python base plus a complete Linux wheel lock; no custom pushed base.
FROM ${PYTHON_IMAGE} AS python-deps
COPY deploy/isp-federation-poc/requirements.lock /tmp/requirements.lock
RUN python3 -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/requirements.lock && \
    python3 -m pip check

FROM python-deps AS runtime
ARG SOURCE_SHA
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/src
WORKDIR /src
COPY nbsr /src/nbsr
COPY tests /src/tests
COPY vectors /src/vectors
COPY docs/protocol/registries/federation-v0.1-development.json /src/docs/protocol/registries/federation-v0.1-development.json
COPY pyproject.toml /src/pyproject.toml
COPY client/nbsr-go-client/demo/testdata /src/client/nbsr-go-client/demo/testdata
COPY scripts/performance/authority.py /src/scripts/performance/authority.py
COPY deploy/isp-federation-poc/supervisor.py /opt/nbsr/supervisor.py
COPY deploy/isp-federation-poc/healthcheck.py /opt/nbsr/healthcheck.py
COPY deploy/isp-federation-poc/private-origin/main.py /opt/nbsr/private-origin.py
COPY --from=go-build /out/ /opt/nbsr/bin/
COPY --from=rust-build /cargo-target/release/wp8_interop_server /opt/nbsr/bin/wp8_interop_server
RUN python3 -c "import pytest, cryptography, cbor2; import scripts.performance.authority; import tests.federation.test_live_interoperability; import tests.federation.test_authorization" && \
    mkdir -p /src/client/nbsr-go-client/demo/test-results/nbsr-demo/runtime /opt/nbsr-build/nbsr-demo /projection-a /projection-b /control /health /state && \
    chown -R 65532:65532 /src/client/nbsr-go-client/demo/test-results /opt/nbsr-build /projection-a /projection-b /control /health /state && \
    python3 -c 'import json,sys,re; assert re.fullmatch("[0-9a-f]{40}",sys.argv[1]); json.dump({"source_sha":sys.argv[1]},open("/opt/nbsr/build-info.json","w"))' "$SOURCE_SHA"
USER 65532:65532
ENTRYPOINT ["python3", "/opt/nbsr/supervisor.py"]

FROM ${PYTHON_IMAGE} AS adapter
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=go-build /out/isp-a-tcp /out/isp-b-udp /opt/nbsr/bin/
COPY deploy/isp-federation-poc/supervisor.py /opt/nbsr/supervisor.py
COPY deploy/isp-federation-poc/healthcheck.py /opt/nbsr/healthcheck.py
USER 65532:65532
ENTRYPOINT ["python3", "/opt/nbsr/supervisor.py"]
