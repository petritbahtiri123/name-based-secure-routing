ARG RUST_IMAGE=rust@sha256:408fe88047cef61a2087653b0c5255fa51c0f2d6d94ddedd7a2562a9b91a46f6
ARG PYTHON_IMAGE=python@sha256:ff83a535339812dd72e69c93b3c48ddf7c85a324d6330af5797c82a255dbeef4
FROM ${RUST_IMAGE} AS build
COPY source.bundle /input/source.bundle
RUN git clone /input/source.bundle /src && cd /src && git checkout --detach 3644c324a535586e89af72a8c9796e8d58fadf48 && test -z "$(git status --porcelain)"
WORKDIR /src
ENV CARGO_TARGET_DIR=/build
RUN mkdir /provenance && rustc -Vv > /provenance/rustc.txt && cargo -V > /provenance/cargo.txt && \
    cargo build --locked --release --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --bin perf_direct_peer --bin perf_rust_source --bin wp8_interop_server

FROM ${PYTHON_IMAGE} AS smoke
RUN apt-get update && apt-get install --yes --no-install-recommends git util-linux && \
    command -v git && command -v taskset && command -v lscpu
COPY --from=build /src /src
RUN python3 -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /src/deploy/isp-federation-poc/requirements.lock && python3 -m pip check
COPY --from=build /build/release/perf_direct_peer /build/release/perf_rust_source /build/release/wp8_interop_server /opt/nbsr/bin/
COPY --from=build /provenance /opt/nbsr/provenance
COPY run.py /opt/nbsr/run.py
RUN mkdir /evidence && chown 65532:65532 /evidence && chmod 0755 /opt/nbsr/bin/* && \
    git --version > /opt/nbsr/provenance/git.txt && lscpu --version > /opt/nbsr/provenance/lscpu.txt && \
    dpkg-query -W > /opt/nbsr/provenance/packages.txt && python3 -m pip freeze > /opt/nbsr/provenance/python-packages.txt
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/src GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=/src
WORKDIR /src
USER 65532:65532
ENTRYPOINT ["python3", "/opt/nbsr/run.py"]
