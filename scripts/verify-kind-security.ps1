Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-ConnectionPolicy {
    param(
        [Parameter(Mandatory = $true)][string]$Workload,
        [Parameter(Mandatory = $true)][string]$HostName,
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][bool]$ShouldConnect
    )

    $Probe = "import socket; s=socket.create_connection(('$HostName',$Port),2); s.close()"
    & kubectl -n nbsr exec $Workload -- python -c $Probe *> $null
    $Connected = $LASTEXITCODE -eq 0
    if ($Connected -ne $ShouldConnect) {
        $Expectation = if ($ShouldConnect) { "allowed" } else { "denied" }
        throw "Expected $Workload -> ${HostName}:$Port to be $Expectation."
    }
}

kubectl -n nbsr wait --for=condition=Ready pod --all --timeout=180s | Out-Null

$PaymentsServiceIp = kubectl -n nbsr get service payments-service -o jsonpath="{.spec.clusterIP}"
$OriginServiceIp = kubectl -n nbsr get service test -o jsonpath="{.spec.clusterIP}"
Test-ConnectionPolicy -Workload "deployment/control-plane" -HostName "opa" -Port 8181 -ShouldConnect $true
Test-ConnectionPolicy -Workload "deployment/control-plane" -HostName $PaymentsServiceIp -Port 7000 -ShouldConnect $false
Test-ConnectionPolicy -Workload "deployment/name-relay" -HostName "test" -Port 443 -ShouldConnect $true
Test-ConnectionPolicy -Workload "deployment/name-control" -HostName $OriginServiceIp -Port 443 -ShouldConnect $false

$GatewayProbe = "nbsr-gateway-policy-probe"
kubectl -n nbsr delete pod $GatewayProbe --ignore-not-found --wait | Out-Null
try {
    kubectl -n nbsr run $GatewayProbe --labels="app=gateway" --image=nbsr:local --restart=Never --command -- python -c "import time; time.sleep(300)" | Out-Null
    kubectl -n nbsr wait "pod/$GatewayProbe" --for=condition=Ready --timeout=60s | Out-Null
    Test-ConnectionPolicy -Workload "pod/$GatewayProbe" -HostName "ticket-verifier" -Port 9000 -ShouldConnect $true
} finally {
    kubectl -n nbsr delete pod $GatewayProbe --ignore-not-found --wait | Out-Null
}

$Pods = kubectl -n nbsr get pods -o json | ConvertFrom-Json
$Restarts = @(
    $Pods.items |
        ForEach-Object { $_.status.containerStatuses } |
        Where-Object { $_.restartCount -ne 0 }
)
if ($Restarts.Count -ne 0) {
    throw "One or more NBSR containers have a non-zero restartCount."
}

Write-Host "Kind security verification passed: required flows allowed, forbidden flows denied, restartCount=0."
