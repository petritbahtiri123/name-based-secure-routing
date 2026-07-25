#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KIND_NODE_IMAGE="${NBSR_KIND_NODE_IMAGE:-kindest/node:v1.35.0@sha256:452d707d4862f52530247495d180205e029056831160e22870e37e3f6c1ac31f}"
CALICO_VERSION="v3.32.1"
CALICO_SHA256="a1df919d9721cf667accdc3e72848911b0cb25cfab7d2478ad0c996302c95744"
CALICO_MANIFEST="$(mktemp "${TMPDIR:-/tmp}/nbsr-calico.XXXXXX.yaml")"
cleanup_calico_manifest() {
  rm -f "$CALICO_MANIFEST"
}
trap cleanup_calico_manifest EXIT
"$ROOT/scripts/bootstrap.sh"
kind create cluster --name nbsr --config "$ROOT/deploy/kind/cluster.yaml" --image "$KIND_NODE_IMAGE"
curl --fail --show-error --silent --location \
  "https://raw.githubusercontent.com/projectcalico/calico/$CALICO_VERSION/manifests/calico.yaml" \
  --output "$CALICO_MANIFEST"
if command -v sha256sum >/dev/null 2>&1; then
  actual_calico_sha256="$(sha256sum "$CALICO_MANIFEST" | awk '{print $1}')"
else
  actual_calico_sha256="$(shasum -a 256 "$CALICO_MANIFEST" | awk '{print $1}')"
fi
if [[ "$actual_calico_sha256" != "$CALICO_SHA256" ]]; then
  echo "Calico manifest checksum mismatch." >&2
  exit 1
fi
kubectl apply -f "$CALICO_MANIFEST"
kubectl -n kube-system rollout status daemonset/calico-node --timeout=240s
kubectl -n kube-system rollout status deployment/calico-kube-controllers --timeout=240s
cleanup_calico_manifest
trap - EXIT
docker build -t nbsr:local "$ROOT"
kind load docker-image nbsr:local --name nbsr
kubectl create namespace nbsr --dry-run=client -o yaml | kubectl apply -f -
kubectl -n nbsr create secret generic nbsr-keys --from-file="$ROOT/secrets/identity-public.pem" --from-file="$ROOT/secrets/ticket-private.pem" --from-file="$ROOT/secrets/ticket-public.pem" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n nbsr create secret generic nbsr-name-binding-keys --from-file="$ROOT/secrets/name-binding-private.pem" --from-file="$ROOT/secrets/name-binding-public.pem" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n nbsr create secret generic nbsr-isp-tls --from-file="$ROOT/secrets/isp-ca.pem" --from-file="$ROOT/secrets/isp-control-cert.pem" --from-file="$ROOT/secrets/isp-control-key.pem" --from-file="$ROOT/secrets/isp-relay-cert.pem" --from-file="$ROOT/secrets/isp-relay-key.pem" --from-file="$ROOT/secrets/isp-origin-cert.pem" --from-file="$ROOT/secrets/isp-origin-key.pem" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n nbsr create secret generic nbsr-enterprise-tls --from-file="$ROOT/secrets/demo-ca.pem" --from-file="$ROOT/secrets/enterprise-control-plane-cert.pem" --from-file="$ROOT/secrets/enterprise-control-plane-key.pem" --from-file="$ROOT/secrets/enterprise-gateway-cert.pem" --from-file="$ROOT/secrets/enterprise-gateway-key.pem" --from-file="$ROOT/secrets/enterprise-opa-cert.pem" --from-file="$ROOT/secrets/enterprise-opa-key.pem" --from-file="$ROOT/secrets/enterprise-control-plane-client-cert.pem" --from-file="$ROOT/secrets/enterprise-control-plane-client-key.pem" --from-file="$ROOT/secrets/enterprise-gateway-client-cert.pem" --from-file="$ROOT/secrets/enterprise-gateway-client-key.pem" --from-file="$ROOT/secrets/enterprise-ticket-verifier-cert.pem" --from-file="$ROOT/secrets/enterprise-ticket-verifier-key.pem" --from-file="$ROOT/secrets/enterprise-payments-service-cert.pem" --from-file="$ROOT/secrets/enterprise-payments-service-key.pem" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n nbsr create configmap envoy-config --from-file=envoy.yaml="$ROOT/gateway/envoy.yaml" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "$ROOT/deploy/kind/nbsr.yaml"
kubectl -n nbsr wait --for=condition=available deployment --all --timeout=180s
"$ROOT/scripts/verify-kind-security.sh"
