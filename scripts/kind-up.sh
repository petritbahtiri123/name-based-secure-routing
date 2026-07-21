#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$ROOT/scripts/bootstrap.sh"
kind create cluster --name nbsr --config "$ROOT/deploy/kind/cluster.yaml"
docker build -t nbsr:local "$ROOT"
kind load docker-image nbsr:local --name nbsr
kubectl create namespace nbsr --dry-run=client -o yaml | kubectl apply -f -
kubectl -n nbsr create secret generic nbsr-keys --from-file="$ROOT/secrets/identity-public.pem" --from-file="$ROOT/secrets/ticket-private.pem" --from-file="$ROOT/secrets/ticket-public.pem" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n nbsr create secret generic nbsr-name-binding-keys --from-file="$ROOT/secrets/name-binding-private.pem" --from-file="$ROOT/secrets/name-binding-public.pem" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n nbsr create secret generic nbsr-isp-tls --from-file="$ROOT/secrets/isp-ca.pem" --from-file="$ROOT/secrets/isp-control-cert.pem" --from-file="$ROOT/secrets/isp-control-key.pem" --from-file="$ROOT/secrets/isp-relay-cert.pem" --from-file="$ROOT/secrets/isp-relay-key.pem" --from-file="$ROOT/secrets/isp-origin-cert.pem" --from-file="$ROOT/secrets/isp-origin-key.pem" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n nbsr create configmap envoy-config --from-file=envoy.yaml="$ROOT/gateway/envoy.yaml" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "$ROOT/deploy/kind/nbsr.yaml"
kubectl -n nbsr wait --for=condition=available deployment --all --timeout=180s
