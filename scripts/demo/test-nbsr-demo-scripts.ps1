$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$scriptRoot = Split-Path -Parent $PSCommandPath
$required = @(
    'lib-nbsr-demo.ps1',
    'start-nbsr-demo.ps1',
    'run-nbsr-demo.ps1',
    'stop-nbsr-demo.ps1'
)
foreach ($name in $required) {
    $path = Join-Path $scriptRoot $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "missing Task 5 script: $name"
    }
}

. (Join-Path $scriptRoot 'lib-nbsr-demo.ps1')

function Assert-Throws([scriptblock]$Action, [string]$Name) {
    try {
        & $Action
    }
    catch {
        return
    }
    throw "expected failure: $Name"
}

$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("nbsr-task5-test-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $runtimeBase = Join-Path $temporary 'test-results\nbsr-demo\runtime'
    $runRoot = Join-Path $runtimeBase 'run-a'
    $nested = Join-Path $runRoot 'readiness\client.json'
    New-Item -ItemType Directory -Path (Split-Path -Parent $nested) -Force | Out-Null
    Assert-NbsrContainedPath -Base $runRoot -Candidate $nested -AllowMissingLeaf | Out-Null
    Assert-Throws { Assert-NbsrRunRoots -RepositoryRoot $temporary -RunId 'run-a' -RuntimeRoot $runRoot -BuildRoot (Join-Path $temporary 'unapproved-build\run-a') } 'unapproved state roots'
    Assert-Throws { Assert-NbsrContainedPath -Base $runRoot -Candidate (Join-Path $runRoot '..\run-b\state.json') -AllowMissingLeaf } 'runtime traversal'
    Assert-Throws { Assert-NbsrContainedPath -Base $runRoot -Candidate (Join-Path $runtimeBase 'run-b\state.json') -AllowMissingLeaf } 'sibling runtime'
    $outside = Join-Path $temporary 'outside'
    New-Item -ItemType Directory -Path $outside | Out-Null
    $junction = Join-Path $runRoot 'junction'
    try {
        New-Item -ItemType Junction -Path $junction -Target $outside | Out-Null
        Assert-Throws { Assert-NbsrContainedPath -Base $runRoot -Candidate (Join-Path $junction 'escape.json') -AllowMissingLeaf } 'junction escape'
    } catch {
        if (Test-Path -LiteralPath $junction) { throw }
    }

    $buildBase = Join-Path $temporary 'NBSR-build\nbsr-demo'
    $buildRoot = Join-Path $buildBase 'run-a'
    New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
    $binary = Join-Path $buildRoot 'nbsr-demo-client.exe'
    [System.IO.File]::WriteAllBytes($binary, [byte[]](1, 2, 3, 4))
    $hash = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()
    Assert-NbsrArtifact -BuildRoot $buildRoot -Path $binary -Sha256 $hash | Out-Null
    Assert-Throws { Assert-NbsrArtifact -BuildRoot $buildRoot -Path $binary -Sha256 ('0' * 64) } 'binary hash mismatch'

    $state = [ordered]@{
        schema = 'nbsr-demo-state-v1'
        run_id = 'run-a'
        lifecycle = 'FAILED'
        source_sha = ('a' * 40)
        runtime_root = $runRoot
        build_root = $buildRoot
        service = 'service-a.nbsr.test'
        synthetic_ip = '127.0.0.2'
        started_at_utc = [DateTime]::UtcNow.ToString('o')
        endpoints = [ordered]@{ acp = 'https://127.0.0.1:1'; destination = '127.0.0.1:2'; proxy = '127.0.0.1:3' }
        readiness = [ordered]@{ authority = $nested; destination = $nested; client = $nested }
        artifacts = @([ordered]@{ name = 'client'; executable = $binary; sha256 = $hash })
        components = @()
    }
    $statePath = Join-Path $runRoot 'state.json'
    Write-NbsrJsonAtomic -Path $statePath -Value $state
    $loaded = Read-NbsrState -Path $statePath
    if ($loaded.run_id -ne 'run-a') { throw 'state round trip failed' }

    Assert-Throws { Read-NbsrState -Path (Join-Path $temporary 'missing.json') } 'stopped run'
    [System.IO.File]::WriteAllText($statePath, '{broken')
    Assert-Throws { Read-NbsrState -Path $statePath } 'malformed state'
    [System.IO.File]::WriteAllText($statePath, '{"schema":"nbsr-demo-state-v1","schema":"duplicate"}')
    Assert-Throws { Read-NbsrState -Path $statePath } 'duplicate state field'
    [System.IO.File]::WriteAllText($statePath, '{"schema":"nbsr-demo-state-v1","components":[{"pid":1,"pid":2}]}')
    try { Read-NbsrState -Path $statePath | Out-Null; throw 'nested duplicate state field was accepted' }
    catch { if ($_.Exception.Message -ne 'duplicate state field') { throw } }

    $self = Get-Process -Id $PID
    $pwsh = $self.Path
    $pwshHash = (Get-FileHash -LiteralPath $pwsh -Algorithm SHA256).Hash.ToLowerInvariant()
    $identity = [pscustomobject](Get-NbsrProcessIdentity -Process $self -Executable $pwsh -Sha256 $pwshHash)
    $identity.start_time_utc = [DateTime]::UtcNow.AddHours(-1).ToString('o')
    Assert-Throws { Assert-NbsrProcessIdentity -Component $identity -BuildRoot (Split-Path -Parent $pwsh) } 'PID start-time mismatch'
    if (-not (Get-Process -Id $PID -ErrorAction SilentlyContinue)) { throw 'identity mismatch killed unrelated process' }

    $sleepers = [Collections.Generic.List[object]]::new()
    foreach ($phase in @('authority','destination','client')) {
        $process = Start-NbsrLoggedProcess -Executable $pwsh -Arguments @('-NoProfile','-Command','Start-Sleep -Seconds 30') -WorkingDirectory $temporary -LogDirectory $temporary -Name $phase
        $sleepers.Add([pscustomobject](Get-NbsrProcessIdentity -Process $process -Executable $pwsh -Sha256 $pwshHash))
    }
    Assert-Throws { Wait-NbsrReadiness -Process (Get-Process -Id $sleepers[2].pid) -Path (Join-Path $temporary 'never-ready') -Validate { param($path) $true } -TimeoutSeconds 1 } 'readiness timeout'
    Stop-NbsrOwnedProcesses -Components $sleepers -BuildRoot (Split-Path -Parent $pwsh)
    if (@($sleepers | Where-Object { Get-Process -Id $_.pid -ErrorAction SilentlyContinue }).Count -ne 0) { throw 'rollback left an owned process' }
    foreach ($ownedCount in @(1, 2)) {
        $partial = [Collections.Generic.List[object]]::new()
        for ($index = 0; $index -lt $ownedCount; $index++) {
            $process = Start-NbsrLoggedProcess -Executable $pwsh -Arguments @('-NoProfile','-Command','Start-Sleep -Seconds 30') -WorkingDirectory $temporary -LogDirectory $temporary -Name "partial-$ownedCount-$index"
            $partial.Add([pscustomobject](Get-NbsrProcessIdentity -Process $process -Executable $pwsh -Sha256 $pwshHash))
        }
        Stop-NbsrOwnedProcesses -Components $partial -BuildRoot (Split-Path -Parent $pwsh)
        if (@($partial | Where-Object { Get-Process -Id $_.pid -ErrorAction SilentlyContinue }).Count -ne 0) { throw "partial-start rollback failed at count $ownedCount" }
    }

    $bestEffort = [Collections.Generic.List[object]]::new()
    foreach ($index in 0..1) {
        $process = Start-NbsrLoggedProcess -Executable $pwsh -Arguments @('-NoProfile','-Command','Start-Sleep -Seconds 30') -WorkingDirectory $temporary -LogDirectory $temporary -Name "best-effort-$index"
        $bestEffort.Add([pscustomobject](Get-NbsrProcessIdentity -Process $process -Executable $pwsh -Sha256 $pwshHash))
    }
    $bestEffort[1].start_time_utc = [DateTime]::UtcNow.AddHours(-1).ToString('o')
    Assert-Throws { Stop-NbsrOwnedProcesses -Components $bestEffort -BuildRoot (Split-Path -Parent $pwsh) } 'rollback identity mismatch'
    if (Get-Process -Id $bestEffort[0].pid -ErrorAction SilentlyContinue) { throw 'best-effort rollback stopped after first error' }
    Stop-Process -Id $bestEffort[1].pid -Force -ErrorAction SilentlyContinue

    'Task 5 PowerShell focused tests: PASS'
}
finally {
    $resolvedTemporary = [IO.Path]::GetFullPath($temporary)
    if (-not $resolvedTemporary.StartsWith([IO.Path]::GetTempPath(), [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolvedTemporary) -notlike 'nbsr-task5-test-*') { throw 'unsafe test cleanup target' }
    Remove-Item -LiteralPath $resolvedTemporary -Recurse -Force -ErrorAction SilentlyContinue
}
