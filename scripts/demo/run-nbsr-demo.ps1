[CmdletBinding()]
param([Parameter(Mandatory)][string]$StatePath)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'lib-nbsr-demo.ps1')

$state = Read-NbsrState -Path $StatePath
Assert-NbsrRunRoots -RepositoryRoot (Get-NbsrRepositoryRoot) -RunId ([string]$state.run_id) -RuntimeRoot ([string]$state.runtime_root) -BuildRoot ([string]$state.build_root)
if ($state.lifecycle -ne 'RUNNING') { throw 'NBSR demo is not running' }
Assert-NbsrContainedPath -Base $state.runtime_root -Candidate $StatePath | Out-Null
foreach ($component in $state.components) { Assert-NbsrProcessIdentity -Component $component -BuildRoot $state.build_root | Out-Null }
foreach ($artifact in $state.artifacts) { Assert-NbsrArtifact -BuildRoot $state.build_root -Path ([string]$artifact.executable) -Sha256 ([string]$artifact.sha256) | Out-Null }
foreach ($property in @('authority','destination','client')) {
    $path = [string]$state.readiness.$property
    Assert-NbsrContainedPath -Base $state.runtime_root -Candidate $path | Out-Null
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "missing readiness: $property" }
}
$startGate = Assert-NbsrContainedPath -Base $state.runtime_root -Candidate ([string]$state.readiness.destination_start_gate) -AllowMissingLeaf
$completionAck = Assert-NbsrContainedPath -Base $state.runtime_root -Candidate ([string]$state.readiness.completion_ack) -AllowMissingLeaf
if (-not (Test-NbsrLoopbackEndpoint -Endpoint $state.endpoints.proxy)) { throw 'invalid proxy endpoint in state' }
try {
    try {
        $gate = [IO.File]::Open($startGate, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $gate.Dispose()
    } catch {
        throw 'this run has already attempted its single application request'
    }
    $body = Invoke-NbsrConnectRequest -ProxyEndpoint ([string]$state.endpoints.proxy) -Service ([string]$state.service)
} catch { throw }
if ($body -ne 'hello from service-a through NBSR') { throw 'unexpected NBSR demo response' }
[IO.File]::WriteAllText($completionAck, 'complete', [Text.UTF8Encoding]::new($false))
Write-Output 'NBSR demo: PASS'
Write-Output "Service: $($state.service)"
Write-Output 'Path: NBSR secure route'
Write-Output "Response: $body"
