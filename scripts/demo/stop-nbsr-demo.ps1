[CmdletBinding()]
param([Parameter(Mandatory)][string]$StatePath)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'lib-nbsr-demo.ps1')

$state = Read-NbsrState -Path $StatePath
Assert-NbsrRunRoots -RepositoryRoot (Get-NbsrRepositoryRoot) -RunId ([string]$state.run_id) -RuntimeRoot ([string]$state.runtime_root) -BuildRoot ([string]$state.build_root)
Assert-NbsrContainedPath -Base $state.runtime_root -Candidate $StatePath | Out-Null
if ($state.lifecycle -eq 'STOPPED') {
    Write-Output 'NBSR demo: already stopped'
    exit 0
}
if ($state.lifecycle -ne 'RUNNING') { throw 'NBSR demo state is not stoppable' }
foreach ($component in $state.components) {
    if (Get-Process -Id ([int]$component.pid) -ErrorAction SilentlyContinue) {
        Assert-NbsrProcessIdentity -Component $component -BuildRoot $state.build_root | Out-Null
    }
}
Stop-NbsrOwnedProcesses -Components $state.components -BuildRoot $state.build_root
foreach ($component in $state.components) {
    if (Get-Process -Id ([int]$component.pid) -ErrorAction SilentlyContinue) { throw "owned process remains: $($component.name)" }
}
$state.lifecycle = 'STOPPED'
Write-NbsrJsonAtomic -Path $StatePath -Value $state
$lockPath = Join-Path (Split-Path -Parent $state.runtime_root) 'active.lock'
if (Test-Path -LiteralPath $lockPath) {
    $owner = (Get-Content -LiteralPath $lockPath -Raw).Trim()
    if ($owner -ne $state.run_id) { throw 'active lock belongs to another run' }
    Remove-Item -LiteralPath $lockPath -Force
}
Write-Output 'NBSR demo: STOPPED'
Write-Output "Run ID: $($state.run_id)"
