# No default base or implicit installer: supply an independently reviewed digest.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG BASE_IMAGE
ARG SOURCE_SHA
ARG TARGETARCH
ENV NBSR_DEMO_CONTAINER=1 GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off GOWORK=off     GOFLAGS=-mod=readonly GOMAXPROCS=2 CARGO_BUILD_JOBS=2 CARGO_NET_OFFLINE=true     PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1     PYTHONPATH=/src/tools/demo-lab     CARGO_TARGET_DIR=/opt/nbsr-cache/cargo-target
WORKDIR /src
# Build context is a reviewed clean export, never the user's working checkout.
COPY . /src/
RUN python3 /src/tools/demo-lab/container/build_image.py && mkdir -p /opt/nbsr && cp /src/tools/demo-lab/container/demo-container-worker /opt/nbsr/demo-container-worker && chmod 0555 /opt/nbsr/demo-container-worker
USER 65532:65532
WORKDIR /src/client/nbsr-go-client/demo
# Only the allowlisted scenario name may be supplied as argv.
ENTRYPOINT ["/opt/nbsr/demo-container-worker"]
