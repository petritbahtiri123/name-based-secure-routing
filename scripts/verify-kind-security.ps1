Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-ConnectionPolicy {
    param(
        [Parameter(Mandatory = $true)][string]$Namespace,
        [Parameter(Mandatory = $true)][string]$Workload,
        [Parameter(Mandatory = $true)][string]$HostName,
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][bool]$ShouldConnect
    )

    $Probe = "import socket; s=socket.create_connection(('$HostName',$Port),2); s.close()"
    $OriginalErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & kubectl -n $Namespace exec $Workload -- python -c $Probe *> $null
        $Connected = $LASTEXITCODE -eq 0
    } finally {
        $ErrorActionPreference = $OriginalErrorActionPreference
    }
    if ($Connected -ne $ShouldConnect) {
        $Expectation = if ($ShouldConnect) { "allowed" } else { "denied" }
        throw "Expected $Namespace/$Workload -> ${HostName}:$Port to be $Expectation."
    }
}

function Test-DnsPolicy {
    param(
        [Parameter(Mandatory = $true)][string]$Workload,
        [Parameter(Mandatory = $true)][string]$HostName
    )

    $Probe = "import socket; assert socket.getaddrinfo('$HostName',443)"
    $OriginalErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & kubectl -n nbsr exec $Workload -- python -c $Probe *> $null
        $Resolved = $LASTEXITCODE -eq 0
    } finally {
        $ErrorActionPreference = $OriginalErrorActionPreference
    }
    if (-not $Resolved) {
        throw "Expected nbsr/$Workload to resolve $HostName through cluster DNS."
    }
}

kubectl -n kube-system wait --for=condition=Ready pod -l k8s-app=calico-node --timeout=180s | Out-Null
kubectl -n nbsr wait --for=condition=Ready pod --all --timeout=180s | Out-Null

$GatewayProbe = "nbsr-policy-probe-gateway"
$UnrelatedProbe = "nbsr-policy-probe-unrelated"
$CrossNamespace = "nbsr-cross-namespace-probe"
$CrossTarget = "cross-target"

kubectl -n nbsr delete pod $GatewayProbe $UnrelatedProbe --ignore-not-found --wait | Out-Null
kubectl delete namespace $CrossNamespace --ignore-not-found --wait | Out-Null

try {
    kubectl -n nbsr run $GatewayProbe --labels="app=gateway" --image=nbsr:local --restart=Never --command -- python -c "import time; time.sleep(300)" | Out-Null
    kubectl -n nbsr run $UnrelatedProbe --labels="app=unrelated" --image=nbsr:local --restart=Never --command -- python -c "import time; time.sleep(300)" | Out-Null
    kubectl create namespace $CrossNamespace | Out-Null
    kubectl -n $CrossNamespace run $CrossTarget --labels="app=cross-target" --image=nbsr:local --restart=Never --command -- python -c "import socket,time; s=socket.socket(); s.bind(('0.0.0.0',8081)); s.listen(); time.sleep(300)" | Out-Null
    kubectl -n $CrossNamespace expose pod $CrossTarget --name=$CrossTarget --port=8081 --target-port=8081 | Out-Null

    kubectl -n nbsr wait "pod/$GatewayProbe" --for=condition=Ready --timeout=60s | Out-Null
    kubectl -n nbsr wait "pod/$UnrelatedProbe" --for=condition=Ready --timeout=60s | Out-Null
    kubectl -n $CrossNamespace wait "pod/$CrossTarget" --for=condition=Ready --timeout=60s | Out-Null

    $PaymentsServiceIP = kubectl -n nbsr get service payments-service -o jsonpath="{.spec.clusterIP}"
    $PaymentsPodIP = kubectl -n nbsr get pod -l app=payments -o jsonpath="{.items[0].status.podIP}"
    $VerifierServiceIP = kubectl -n nbsr get service ticket-verifier -o jsonpath="{.spec.clusterIP}"
    $OpaServiceIP = kubectl -n nbsr get service opa -o jsonpath="{.spec.clusterIP}"
    $ControlServiceIP = kubectl -n nbsr get service control-plane -o jsonpath="{.spec.clusterIP}"
    $OriginServiceIP = kubectl -n nbsr get service test -o jsonpath="{.spec.clusterIP}"
    $CrossServiceIP = kubectl -n $CrossNamespace get service $CrossTarget -o jsonpath="{.spec.clusterIP}"

    Test-ConnectionPolicy -Namespace nbsr -Workload "deployment/control-plane" -HostName "opa" -Port 8181 -ShouldConnect $true
    Test-ConnectionPolicy -Namespace nbsr -Workload "pod/$GatewayProbe" -HostName "ticket-verifier" -Port 9000 -ShouldConnect $true
    Test-ConnectionPolicy -Namespace nbsr -Workload "pod/$GatewayProbe" -HostName "payments-service" -Port 7000 -ShouldConnect $true
    Test-ConnectionPolicy -Namespace nbsr -Workload "deployment/name-relay" -HostName $OriginServiceIP -Port 80 -ShouldConnect $true
    Test-ConnectionPolicy -Namespace nbsr -Workload "deployment/name-relay" -HostName $OriginServiceIP -Port 443 -ShouldConnect $true
    Test-DnsPolicy -Workload "deployment/name-relay" -HostName "test"

    Test-ConnectionPolicy -Namespace nbsr -Workload "deployment/name-relay" -HostName $PaymentsServiceIP -Port 7000 -ShouldConnect $false
    Test-ConnectionPolicy -Namespace nbsr -Workload "deployment/name-relay" -HostName $PaymentsPodIP -Port 7000 -ShouldConnect $false
    Test-ConnectionPolicy -Namespace nbsr -Workload "deployment/name-relay" -HostName $VerifierServiceIP -Port 9000 -ShouldConnect $false
    Test-ConnectionPolicy -Namespace nbsr -Workload "deployment/name-relay" -HostName $OpaServiceIP -Port 8181 -ShouldConnect $false
    Test-ConnectionPolicy -Namespace nbsr -Workload "deployment/name-relay" -HostName $ControlServiceIP -Port 8000 -ShouldConnect $false
    Test-ConnectionPolicy -Namespace nbsr -Workload "pod/$UnrelatedProbe" -HostName $PaymentsServiceIP -Port 7000 -ShouldConnect $false
    Test-ConnectionPolicy -Namespace nbsr -Workload "pod/$UnrelatedProbe" -HostName $VerifierServiceIP -Port 9000 -ShouldConnect $false
    Test-ConnectionPolicy -Namespace nbsr -Workload "deployment/name-relay" -HostName $CrossServiceIP -Port 8081 -ShouldConnect $false
    Test-ConnectionPolicy -Namespace nbsr -Workload "pod/$UnrelatedProbe" -HostName $CrossServiceIP -Port 8081 -ShouldConnect $false
    Test-ConnectionPolicy -Namespace nbsr -Workload "deployment/name-relay" -HostName "169.254.169.254" -Port 80 -ShouldConnect $false
    Test-ConnectionPolicy -Namespace nbsr -Workload "deployment/name-relay" -HostName "169.254.1.1" -Port 80 -ShouldConnect $false

    Test-ConnectionPolicy -Namespace $CrossNamespace -Workload "pod/$CrossTarget" -HostName $CrossServiceIP -Port 8081 -ShouldConnect $true
} finally {
    kubectl -n nbsr delete pod $GatewayProbe $UnrelatedProbe --ignore-not-found --wait | Out-Null
    kubectl delete namespace $CrossNamespace --ignore-not-found --wait | Out-Null
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

Write-Host "Kind security verification passed: Calico enforced all required allow/deny probes, temporary resources removed, restartCount=0."
