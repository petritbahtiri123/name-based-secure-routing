[CmdletBinding()]
param(
    [ValidatePattern('^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$')][string]$RunId = ('run-' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)),
    [int]$ReadinessTimeoutSeconds = 20
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'lib-nbsr-demo.ps1')

if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 or newer is required' }
foreach ($command in @('git','go','cargo','rustc')) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { throw "missing prerequisite: $command" }
}

$repo = Get-NbsrRepositoryRoot
$branch = (& git -C $repo branch --show-current).Trim()
$sourceSha = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne 'codex/nbsr-v3-wp0-wp1') { throw 'unexpected repository state' }
$demo = Join-Path $repo 'client\nbsr-go-client\demo'
$rustManifest = Join-Path $repo 'crates\nbsr-transport\Cargo.toml'
$runtimeBase = Join-Path $demo 'test-results\nbsr-demo\runtime'
$runtimeRoot = Join-Path $runtimeBase $RunId
$relativeRoot = "test-results/nbsr-demo/runtime/$RunId"
$buildRoot = Join-Path 'C:\NBSR-build\nbsr-demo' $RunId
$lockPath = Join-Path $runtimeBase 'active.lock'
$statePath = Join-Path $runtimeRoot 'state.json'
$logs = Join-Path $runtimeRoot 'logs'
$started = [Collections.Generic.List[object]]::new()
$artifacts = @()

New-Item -ItemType Directory -Path $runtimeBase -Force | Out-Null
try {
    $lock = [IO.File]::Open($lockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $writer = [IO.StreamWriter]::new($lock); $writer.Write($RunId); $writer.Flush(); $writer.Dispose() } finally { if ($lock) { $lock.Dispose() } }
} catch { throw 'an active NBSR demo is already registered' }

try {
    if (Test-Path -LiteralPath $runtimeRoot) { throw 'run ID already exists' }
    New-Item -ItemType Directory -Path $runtimeRoot | Out-Null
    New-Item -ItemType Directory -Path $buildRoot | Out-Null
    New-Item -ItemType Directory -Path $logs | Out-Null
    foreach ($directory in @('authority','client\bootstrap','destination','readiness')) { New-Item -ItemType Directory -Path (Join-Path $runtimeRoot $directory) -Force | Out-Null }

    $authorityExe = Join-Path $buildRoot 'nbsr-demo-authority.exe'
    $clientExe = Join-Path $buildRoot 'nbsr-demo-client.exe'
    $backendExe = Join-Path $buildRoot 'nbsr-demo-backend.exe'
    Push-Location $demo
    try {
        & go build -o $authorityExe ./cmd/nbsr-demo-authority
        if ($LASTEXITCODE -ne 0) { throw 'authority build failed' }
        & go build -o $clientExe ./cmd/nbsr-demo-client
        if ($LASTEXITCODE -ne 0) { throw 'client build failed' }
        & go build -o $backendExe ./cmd/nbsr-demo-backend
        if ($LASTEXITCODE -ne 0) { throw 'backend build failed' }
    } finally { Pop-Location }
    $cargoTarget = Join-Path $buildRoot 'cargo-target'
    $previousTarget = $env:CARGO_TARGET_DIR
    try { $env:CARGO_TARGET_DIR = $cargoTarget; & cargo build --locked --release --manifest-path $rustManifest --bin wp8_interop_server } finally { $env:CARGO_TARGET_DIR = $previousTarget }
    if ($LASTEXITCODE -ne 0) { throw 'Rust build failed' }
    $rustExe = Join-Path $cargoTarget 'release\wp8_interop_server.exe'
    $hashes = [ordered]@{}
    $executables = [ordered]@{ authority=$authorityExe; client=$clientExe; backend=$backendExe; destination=$rustExe }
    foreach ($entry in $executables.GetEnumerator()) {
        $hashes[$entry.Key] = (Get-FileHash -LiteralPath $entry.Value -Algorithm SHA256).Hash.ToLowerInvariant()
        Assert-NbsrArtifact -BuildRoot $buildRoot -Path $entry.Value -Sha256 $hashes[$entry.Key] | Out-Null
    }
    $artifacts = @($executables.GetEnumerator() | ForEach-Object { [pscustomobject]@{ name=$_.Key; executable=$_.Value; sha256=$hashes[$_.Key] } })

    $bootstrapRelative = "$relativeRoot/client/bootstrap"
    $admissionRelative = "$relativeRoot/destination/runtime-admission.conf"
    $authority = Start-NbsrLoggedProcess -Executable $authorityExe -Arguments @('--listen','127.0.0.1:0','--runtime',$relativeRoot,'--client-bootstrap',$bootstrapRelative,'--runtime-admission',$admissionRelative) -WorkingDirectory $demo -LogDirectory $logs -Name authority
    $started.Add([pscustomobject](Get-NbsrProcessIdentity -Process $authority -Executable $authorityExe -Sha256 $hashes.authority))
    $bootstrapManifest = Join-Path $runtimeRoot 'client\bootstrap\client-bootstrap.json'
    $bootstrap = Wait-NbsrReadiness -Process $authority -Path $bootstrapManifest -TimeoutSeconds $ReadinessTimeoutSeconds -Validate {
        param($path) $value = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        if ($value.schema -ne 'nbsr-demo-client-bootstrap-v1' -or -not (Test-NbsrLoopbackEndpoint -Endpoint $value.endpoint -Https)) { throw 'invalid ACP readiness' }
        $value
    }
    $admissionPath = Join-Path $runtimeRoot 'destination\runtime-admission.conf'
    if (-not (Test-Path -LiteralPath $admissionPath -PathType Leaf)) { throw 'destination admission artifact missing' }

    $transportAuthority = Join-Path $runtimeRoot 'destination\authority'
    New-NbsrTransportAuthority -Directory $transportAuthority
    $backendMap = Join-Path $runtimeRoot 'destination\backend.map'
    $map = "NBSR-DEMO-BACKEND-MAP-v1`nservice_id=nbsr-demo-service-a-v1`nexecutable=$($backendExe.Replace('\','/'))`nsha256=$($hashes.backend)`n"
    [IO.File]::WriteAllText($backendMap, $map, [Text.UTF8Encoding]::new($false))
    $destinationReady = Join-Path $runtimeRoot 'readiness\destination.json'
    $destinationStartGate = Join-Path $runtimeRoot 'readiness\destination-start.gate'
    $destinationResult = Join-Path $runtimeRoot 'destination\result.json'
    $completionAck = Join-Path $runtimeRoot 'destination\completion.ack'
    $destination = Start-NbsrLoggedProcess -Executable $rustExe -Arguments @('--ready',$destinationReady,'--result',$destinationResult,'--authority-dir',$transportAuthority,'--completion-ack',$completionAck,'--demo-backend-map',$backendMap,'--runtime-admission',$admissionPath,'--demo-start-gate',$destinationStartGate) -WorkingDirectory $repo -LogDirectory $logs -Name destination
    $started.Add([pscustomobject](Get-NbsrProcessIdentity -Process $destination -Executable $rustExe -Sha256 $hashes.destination))
    $destinationView = Wait-NbsrReadiness -Process $destination -Path $destinationReady -TimeoutSeconds $ReadinessTimeoutSeconds -Validate {
        param($path) $value = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        if ($value.alpn -ne 'nbsr-quic-1' -or -not (Test-NbsrLoopbackEndpoint -Endpoint $value.endpoint)) { throw 'invalid destination readiness' }
        $value
    }

    $configRelative = "$relativeRoot/client/config.json"
    $clientReadyRelative = "$relativeRoot/readiness/client.json"
    $config = [ordered]@{
        schema='nbsr-demo-config-v1'; production_semantic=[ordered]@{alpn='nbsr-quic-1';quic_version='v1';tls_version='1.3';stream_credit_profile='nbsr-stream-credit-1'}
        client=[ordered]@{service_fixture='testdata/service-a.json';shared_synthetic_ip='127.0.0.2';proxy_endpoint='127.0.0.1:0';acp_endpoint=$bootstrap.endpoint;destination_readiness="$relativeRoot/readiness/destination.json";application_transport='tcp';service_port=8080}
        acp_fixture=[ordered]@{classification='DEMO FIXTURE — NOT PRODUCTION AUTHORITY';public_fixture="$relativeRoot/client/bootstrap/client-bootstrap.json"}
        destination=[ordered]@{authority_fixture="$relativeRoot/destination/authority";rust_artifact=[ordered]@{path=$rustExe;sha256=$hashes.destination}}
        evidence=[ordered]@{directory="$relativeRoot/evidence"};secrets=[ordered]@{directory="$relativeRoot/client/bootstrap"}
        timeouts=[ordered]@{handshake_seconds=5;operation_seconds=15};limits=[ordered]@{max_proxy_connections=16;max_request_bytes=4096}
    }
    $configPath = Join-Path $runtimeRoot 'client\config.json'
    Write-NbsrJsonAtomic -Path $configPath -Value $config
    $clientReady = Join-Path $runtimeRoot 'readiness\client.json'
    $client = Start-NbsrLoggedProcess -Executable $clientExe -Arguments @('--config',$configRelative,'--bootstrap',$bootstrapRelative,'--ready',$clientReadyRelative,'--runtime-root',$relativeRoot,'--build-root',$buildRoot) -WorkingDirectory $demo -LogDirectory $logs -Name client
    $started.Add([pscustomobject](Get-NbsrProcessIdentity -Process $client -Executable $clientExe -Sha256 $hashes.client))
    $clientView = Wait-NbsrReadiness -Process $client -Path $clientReady -TimeoutSeconds $ReadinessTimeoutSeconds -Validate {
        param($path) $value = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        if ($value.schema -ne 'nbsr-demo-client-ready-v1' -or $value.state -ne 'ready' -or -not (Test-NbsrLoopbackEndpoint -Endpoint $value.Proxy)) { throw 'invalid client readiness' }
        $value
    }
    foreach ($component in $started) { Assert-NbsrProcessIdentity -Component $component | Out-Null }
    $state = [ordered]@{schema='nbsr-demo-state-v1';run_id=$RunId;lifecycle='RUNNING';source_sha=$sourceSha;runtime_root=$runtimeRoot;build_root=$buildRoot;service='service-a.nbsr.test';synthetic_ip='127.0.0.2';started_at_utc=[DateTime]::UtcNow.ToString('o');endpoints=[ordered]@{acp=$bootstrap.endpoint;destination=$destinationView.endpoint;proxy=$clientView.Proxy};readiness=[ordered]@{authority=$bootstrapManifest;destination=$destinationReady;client=$clientReady;destination_start_gate=$destinationStartGate;completion_ack=$completionAck};artifacts=$artifacts;components=@($started)}
    Write-NbsrJsonAtomic -Path $statePath -Value $state
    Write-Output 'NBSR demo: READY'
    Write-Output "Run ID: $RunId"
    Write-Output "Proxy: $($clientView.Proxy)"
    Write-Output "Next: pwsh -NoProfile -File scripts/demo/run-nbsr-demo.ps1 -StatePath `"$statePath`""
} catch {
    $startupFailure = $_
    $rollbackFailure = $null
    try { Stop-NbsrOwnedProcesses -Components $started -BuildRoot $buildRoot } catch { $rollbackFailure = $_ }
    if (Test-Path -LiteralPath $runtimeRoot) {
        $failed = [ordered]@{schema='nbsr-demo-state-v1';run_id=$RunId;lifecycle='FAILED';source_sha=$sourceSha;runtime_root=$runtimeRoot;build_root=$buildRoot;service='service-a.nbsr.test';synthetic_ip='127.0.0.2';started_at_utc=[DateTime]::UtcNow.ToString('o');endpoints=[ordered]@{};readiness=[ordered]@{};artifacts=$artifacts;components=@()}
        try { Write-NbsrJsonAtomic -Path $statePath -Value $failed } catch { }
    }
    $remaining = @($started | Where-Object { Get-Process -Id ([int]$_.pid) -ErrorAction SilentlyContinue })
    if ($remaining.Count -eq 0) { Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue }
    if ($rollbackFailure -or $remaining.Count -ne 0) { throw 'demo startup failed and owned-process rollback was incomplete; active lock retained' }
    throw $startupFailure
}
