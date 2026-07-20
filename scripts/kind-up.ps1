Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$IdentityPublic = Join-Path $Root "secrets/identity-public.pem"
$TicketPrivate = Join-Path $Root "secrets/ticket-private.pem"
$TicketPublic = Join-Path $Root "secrets/ticket-public.pem"
$NameBindingPrivate = Join-Path $Root "secrets/name-binding-private.pem"
$NameBindingPublic = Join-Path $Root "secrets/name-binding-public.pem"
$EnvoyConfig = Join-Path $Root "gateway/envoy.yaml"
& (Join-Path $PSScriptRoot "bootstrap.ps1")
kind create cluster --name nbsr --config (Join-Path $Root "deploy/kind/cluster.yaml")
docker build -t nbsr:local $Root
kind load docker-image nbsr:local --name nbsr
kubectl create namespace nbsr --dry-run=client -o yaml | kubectl apply -f -
kubectl -n nbsr create secret generic nbsr-keys "--from-file=$IdentityPublic" "--from-file=$TicketPrivate" "--from-file=$TicketPublic" "--from-file=$NameBindingPrivate" "--from-file=$NameBindingPublic" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n nbsr create configmap envoy-config "--from-file=envoy.yaml=$EnvoyConfig" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f (Join-Path $Root "deploy/kind/nbsr.yaml")
kubectl -n nbsr wait --for=condition=available deployment --all --timeout=180s
