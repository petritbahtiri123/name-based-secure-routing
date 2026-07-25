#!/usr/bin/env bash
set -euo pipefail

probe() {
  local namespace="$1"
  local workload="$2"
  local host="$3"
  local port="$4"
  local expectation="$5"
  local connected=0

  if kubectl -n "$namespace" exec "$workload" -- \
    python -c "import socket; s=socket.create_connection(('$host',$port),2); s.close()" \
    >/dev/null 2>&1; then
    connected=1
  fi

  if [[ "$expectation" == "allowed" && "$connected" -ne 1 ]]; then
    echo "Expected $namespace/$workload -> $host:$port to be allowed." >&2
    return 1
  fi
  if [[ "$expectation" == "denied" && "$connected" -ne 0 ]]; then
    echo "Expected $namespace/$workload -> $host:$port to be denied." >&2
    return 1
  fi
}

probe_dns() {
  local workload="$1"
  local host="$2"
  kubectl -n nbsr exec "$workload" -- \
    python -c "import socket; assert socket.getaddrinfo('$host',443)" \
    >/dev/null 2>&1
}

kubectl -n kube-system wait --for=condition=Ready pod -l k8s-app=calico-node --timeout=180s >/dev/null
kubectl -n nbsr wait --for=condition=Ready pod --all --timeout=180s >/dev/null

gateway_probe="nbsr-policy-probe-gateway"
unrelated_probe="nbsr-policy-probe-unrelated"
cross_namespace="nbsr-cross-namespace-probe"
cross_target="cross-target"

cleanup_probes() {
  kubectl -n nbsr delete pod "$gateway_probe" "$unrelated_probe" --ignore-not-found --wait >/dev/null
  kubectl delete namespace "$cross_namespace" --ignore-not-found --wait >/dev/null
}
trap cleanup_probes EXIT
cleanup_probes

kubectl -n nbsr run "$gateway_probe" --labels="app=gateway" --image=nbsr:local \
  --restart=Never --command -- python -c "import time; time.sleep(300)" >/dev/null
kubectl -n nbsr run "$unrelated_probe" --labels="app=unrelated" --image=nbsr:local \
  --restart=Never --command -- python -c "import time; time.sleep(300)" >/dev/null
kubectl create namespace "$cross_namespace" >/dev/null
kubectl -n "$cross_namespace" run "$cross_target" --labels="app=cross-target" --image=nbsr:local \
  --restart=Never --command -- \
  python -c "import socket,time; s=socket.socket(); s.bind(('0.0.0.0',8081)); s.listen(); time.sleep(300)" >/dev/null
kubectl -n "$cross_namespace" expose pod "$cross_target" --name="$cross_target" \
  --port=8081 --target-port=8081 >/dev/null

kubectl -n nbsr wait "pod/$gateway_probe" --for=condition=Ready --timeout=60s >/dev/null
kubectl -n nbsr wait "pod/$unrelated_probe" --for=condition=Ready --timeout=60s >/dev/null
kubectl -n "$cross_namespace" wait "pod/$cross_target" --for=condition=Ready --timeout=60s >/dev/null

payments_service_ip="$(kubectl -n nbsr get service payments-service -o jsonpath='{.spec.clusterIP}')"
payments_pod_ip="$(kubectl -n nbsr get pod -l app=payments -o jsonpath='{.items[0].status.podIP}')"
verifier_service_ip="$(kubectl -n nbsr get service ticket-verifier -o jsonpath='{.spec.clusterIP}')"
opa_service_ip="$(kubectl -n nbsr get service opa -o jsonpath='{.spec.clusterIP}')"
control_service_ip="$(kubectl -n nbsr get service control-plane -o jsonpath='{.spec.clusterIP}')"
origin_service_ip="$(kubectl -n nbsr get service test -o jsonpath='{.spec.clusterIP}')"
cross_service_ip="$(kubectl -n "$cross_namespace" get service "$cross_target" -o jsonpath='{.spec.clusterIP}')"

probe nbsr deployment/control-plane opa 8181 allowed
probe nbsr "pod/$gateway_probe" ticket-verifier 9000 allowed
probe nbsr "pod/$gateway_probe" payments-service 7000 allowed
probe nbsr deployment/name-relay "$origin_service_ip" 80 allowed
probe nbsr deployment/name-relay "$origin_service_ip" 443 allowed
probe_dns deployment/name-relay test

probe nbsr deployment/name-relay "$payments_service_ip" 7000 denied
probe nbsr deployment/name-relay "$payments_pod_ip" 7000 denied
probe nbsr deployment/name-relay "$verifier_service_ip" 9000 denied
probe nbsr deployment/name-relay "$opa_service_ip" 8181 denied
probe nbsr deployment/name-relay "$control_service_ip" 8000 denied
probe nbsr "pod/$unrelated_probe" "$payments_service_ip" 7000 denied
probe nbsr "pod/$unrelated_probe" "$verifier_service_ip" 9000 denied
probe nbsr deployment/name-relay "$cross_service_ip" 8081 denied
probe nbsr "pod/$unrelated_probe" "$cross_service_ip" 8081 denied
probe nbsr deployment/name-relay 169.254.169.254 80 denied
probe nbsr deployment/name-relay 169.254.1.1 80 denied

probe "$cross_namespace" "pod/$cross_target" "$cross_service_ip" 8081 allowed

cleanup_probes
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

echo "Kind security verification passed: Calico enforced all required allow/deny probes, temporary resources removed, restartCount=0."
