#!/usr/bin/env bash
set -euo pipefail

probe() {
  local workload="$1"
  local host="$2"
  local port="$3"
  local expectation="$4"
  local connected=0

  if kubectl -n nbsr exec "$workload" -- \
    python -c "import socket; s=socket.create_connection(('$host',$port),2); s.close()" \
    >/dev/null 2>&1; then
    connected=1
  fi

  if [[ "$expectation" == "allowed" && "$connected" -ne 1 ]]; then
    echo "Expected $workload -> $host:$port to be allowed." >&2
    return 1
  fi
  if [[ "$expectation" == "denied" && "$connected" -ne 0 ]]; then
    echo "Expected $workload -> $host:$port to be denied." >&2
    return 1
  fi
}

kubectl -n nbsr wait --for=condition=Ready pod --all --timeout=180s >/dev/null

payments_service_ip="$(kubectl -n nbsr get service payments-service -o jsonpath='{.spec.clusterIP}')"
origin_service_ip="$(kubectl -n nbsr get service test -o jsonpath='{.spec.clusterIP}')"
probe deployment/control-plane opa 8181 allowed
probe deployment/control-plane "$payments_service_ip" 7000 denied
probe deployment/name-relay test 443 allowed
probe deployment/name-control "$origin_service_ip" 443 denied

gateway_probe="nbsr-gateway-policy-probe"
cleanup_gateway_probe() {
  kubectl -n nbsr delete pod "$gateway_probe" --ignore-not-found --wait >/dev/null
}
trap cleanup_gateway_probe EXIT
cleanup_gateway_probe
kubectl -n nbsr run "$gateway_probe" --labels="app=gateway" --image=nbsr:local \
  --restart=Never --command -- python -c "import time; time.sleep(300)" >/dev/null
kubectl -n nbsr wait "pod/$gateway_probe" --for=condition=Ready --timeout=60s >/dev/null
probe "pod/$gateway_probe" ticket-verifier 9000 allowed
cleanup_gateway_probe
trap - EXIT

while read -r pod restartCount; do
  if [[ "$restartCount" != "0" ]]; then
    echo "$pod has restartCount=$restartCount." >&2
    exit 1
  fi
done < <(
  kubectl -n nbsr get pods \
    -o jsonpath='{range .items[*]}{.metadata.name}{" "}{range .status.containerStatuses[*]}{.restartCount}{"\n"}{end}{end}'
)

echo "Kind security verification passed: required flows allowed, forbidden flows denied, restartCount=0."
