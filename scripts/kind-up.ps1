Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$IdentityPublic = Join-Path $Root "secrets/identity-public.pem"
$TicketPrivate = Join-Path $Root "secrets/ticket-private.pem"
$TicketPublic = Join-Path $Root "secrets/ticket-public.pem"
$NameBindingPrivate = Join-Path $Root "secrets/name-binding-private.pem"
$NameBindingPublic = Join-Path $Root "secrets/name-binding-public.pem"
$IspCa = Join-Path $Root "secrets/isp-ca.pem"
$IspControlCert = Join-Path $Root "secrets/isp-control-cert.pem"
$IspControlKey = Join-Path $Root "secrets/isp-control-key.pem"
$IspRelayCert = Join-Path $Root "secrets/isp-relay-cert.pem"
$IspRelayKey = Join-Path $Root "secrets/isp-relay-key.pem"
$IspOriginCert = Join-Path $Root "secrets/isp-origin-cert.pem"
$IspOriginKey = Join-Path $Root "secrets/isp-origin-key.pem"
$EnterpriseCa = Join-Path $Root "secrets/demo-ca.pem"
$EnterpriseControlCert = Join-Path $Root "secrets/enterprise-control-plane-cert.pem"
$EnterpriseControlKey = Join-Path $Root "secrets/enterprise-control-plane-key.pem"
$EnterpriseGatewayCert = Join-Path $Root "secrets/enterprise-gateway-cert.pem"
$EnterpriseGatewayKey = Join-Path $Root "secrets/enterprise-gateway-key.pem"
$EnvoyConfig = Join-Path $Root "gateway/envoy.yaml"
$KindNodeImage = if ($env:NBSR_KIND_NODE_IMAGE) {
    $env:NBSR_KIND_NODE_IMAGE
} else {
    "kindest/node:v1.35.0@sha256:452d707d4862f52530247495d180205e029056831160e22870e37e3f6c1ac31f"
}
& (Join-Path $PSScriptRoot "bootstrap.ps1")
kind create cluster --name nbsr --config (Join-Path $Root "deploy/kind/cluster.yaml") --image $KindNodeImage
docker build -t nbsr:local $Root
kind load docker-image nbsr:local --name nbsr
kubectl create namespace nbsr --dry-run=client -o yaml | kubectl apply -f -
kubectl -n nbsr create secret generic nbsr-keys "--from-file=$IdentityPublic" "--from-file=$TicketPrivate" "--from-file=$TicketPublic" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n nbsr create secret generic nbsr-name-binding-keys "--from-file=$NameBindingPrivate" "--from-file=$NameBindingPublic" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n nbsr create secret generic nbsr-isp-tls "--from-file=$IspCa" "--from-file=$IspControlCert" "--from-file=$IspControlKey" "--from-file=$IspRelayCert" "--from-file=$IspRelayKey" "--from-file=$IspOriginCert" "--from-file=$IspOriginKey" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n nbsr create secret generic nbsr-enterprise-tls "--from-file=$EnterpriseCa" "--from-file=$EnterpriseControlCert" "--from-file=$EnterpriseControlKey" "--from-file=$EnterpriseGatewayCert" "--from-file=$EnterpriseGatewayKey" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n nbsr create configmap envoy-config "--from-file=envoy.yaml=$EnvoyConfig" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f (Join-Path $Root "deploy/kind/nbsr.yaml")
kubectl -n nbsr wait --for=condition=available deployment --all --timeout=180s
& (Join-Path $PSScriptRoot "verify-kind-security.ps1")
