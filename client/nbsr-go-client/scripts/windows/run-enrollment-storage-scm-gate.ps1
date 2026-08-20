#Requires -Version 7.0
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$serviceName = 'NBSRClient'
$serviceAccount = 'NT SERVICE\NBSRClient'
$expectedBranch = 'codex/nbsr-v3-wp0-wp1'
$auditBaseline = 'db8b4f807a0017c4652d7dac893e028b52a2d4fc'
$expectedRemoteWorking = '891ea07218977630aa80a073b1625db4cfcd515b'
$expectedMain = '1938154d498b32d81a3564319969430644e8a688'
$moduleRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$repoRoot = [IO.Path]::GetFullPath((Join-Path $moduleRoot '..\..'))
$programDataRoot = [IO.Path]::GetFullPath((Join-Path $env:ProgramData 'NBSR'))
$enrollmentRoot = Join-Path $programDataRoot 'GoClient\Enrollment'
$evidenceRoot = Join-Path $programDataRoot 'SCMGateEvidence'
$harnessRoot = Join-Path $programDataRoot 'SCMGateHarness'
$workRoot = Join-Path $env:TEMP ('NBSRClient-scm-gate-' + [guid]::NewGuid().ToString('N'))
$builtExecutable = Join-Path $workRoot 'enrollment-storage-scm-gate.exe'
$serviceExecutable = Join-Path $harnessRoot 'enrollment-storage-scm-gate.exe'
$serviceCreated = $false
$programDataCreated = $false
$networkBefore = $null
$networkAfter = $null

function Assert-ExitCode([string]$Operation) {
    if ($LASTEXITCODE -ne 0) { throw "$Operation failed with exit code $LASTEXITCODE" }
}

function Get-NetworkSnapshot {
    $protectedServices = 'Dhcp', 'Dnscache', 'NlaSvc', 'WlanSvc', 'BFE', 'MpsSvc'
    [ordered]@{
        Adapters = @(Get-NetAdapter | Sort-Object ifIndex | Select-Object Name, InterfaceDescription, ifIndex, Status, MacAddress)
        IP = @(Get-NetIPConfiguration | Sort-Object InterfaceIndex | ForEach-Object {
            [ordered]@{
                InterfaceIndex = $_.InterfaceIndex
                InterfaceAlias = $_.InterfaceAlias
                IPv4Address = @($_.IPv4Address.IPAddress | Sort-Object)
                IPv6Address = @($_.IPv6Address.IPAddress | Sort-Object)
                IPv4Gateway = @($_.IPv4DefaultGateway.NextHop | Sort-Object)
                IPv6Gateway = @($_.IPv6DefaultGateway.NextHop | Sort-Object)
            }
        })
        DNS = @(Get-DnsClientServerAddress | Sort-Object InterfaceIndex, AddressFamily | Select-Object InterfaceIndex, InterfaceAlias, AddressFamily, @{Name='ServerAddresses';Expression={@($_.ServerAddresses)}})
        Routes = @(Get-NetRoute | Sort-Object InterfaceIndex, AddressFamily, DestinationPrefix, NextHop | Select-Object InterfaceIndex, AddressFamily, DestinationPrefix, NextHop, RouteMetric, Protocol)
        WinHTTPProxy = (netsh winhttp show proxy | Out-String).Trim()
        FirewallProfiles = @(Get-NetFirewallProfile | Sort-Object Name | Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction)
        ProtectedServices = @(Get-Service -Name $protectedServices | Sort-Object Name | Select-Object Name, Status, StartType)
    }
}

function Save-NetworkInspection([string]$Prefix, $Snapshot) {
    $Snapshot | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $workRoot "$Prefix-normalized.json") -Encoding UTF8
    Get-NetAdapter | Format-List * | Out-String | Set-Content -LiteralPath (Join-Path $workRoot "$Prefix-adapters.txt")
    Get-NetIPConfiguration | Format-List * | Out-String | Set-Content -LiteralPath (Join-Path $workRoot "$Prefix-ip.txt")
    Get-DnsClientServerAddress | Format-Table -AutoSize | Out-String | Set-Content -LiteralPath (Join-Path $workRoot "$Prefix-dns.txt")
    route print | Set-Content -LiteralPath (Join-Path $workRoot "$Prefix-routes.txt")
    netsh winhttp show proxy | Set-Content -LiteralPath (Join-Path $workRoot "$Prefix-winhttp.txt")
    Get-NetFirewallProfile | Format-List * | Out-String | Set-Content -LiteralPath (Join-Path $workRoot "$Prefix-firewall.txt")
}

function Assert-RepositorySafety {
    Push-Location $repoRoot
    try {
        if ((git status --short) -ne $null) { throw 'repository worktree is not clean' }
        if ((git branch --show-current).Trim() -ne $expectedBranch) { throw 'unexpected working branch' }
        git merge-base --is-ancestor $auditBaseline HEAD
        Assert-ExitCode 'verify audit baseline ancestry'
        if ((git rev-parse origin/codex/nbsr-v3-wp0-wp1).Trim() -ne $expectedRemoteWorking) { throw 'unexpected remote working-branch HEAD' }
        if ((git rev-parse main).Trim() -ne $expectedMain -or (git rev-parse origin/main).Trim() -ne $expectedMain) { throw 'frozen main changed' }
    } finally { Pop-Location }
}

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'ELEVATION_REQUIRED: run this script from an elevated PowerShell 7 session'
    }
}

function Set-ExactGateAcl([string]$Path, [Security.Principal.SecurityIdentifier]$ServiceSid) {
    & icacls.exe $Path /setowner '*S-1-5-18' | Out-Null
    Assert-ExitCode "set owner on $Path"
    $suffix = if (Test-Path -LiteralPath $Path -PathType Container) { '(OI)(CI)F' } else { 'F' }
    & icacls.exe $Path /inheritance:r /grant:r "*$($ServiceSid.Value):$suffix" "*S-1-5-18:$suffix" "*S-1-5-32-544:$suffix" | Out-Null
    Assert-ExitCode "set ACL on $Path"
}

function Wait-ServiceState([string]$State, [int]$Seconds = 15) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        $service = Get-Service -Name $serviceName
        if ($service.Status.ToString() -eq $State) { return }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "service did not reach $State"
}

function Invoke-GateAction([string]$Action, [string]$MarkerName) {
    $marker = Join-Path $evidenceRoot $MarkerName
    Remove-Item -LiteralPath $marker -Force -ErrorAction SilentlyContinue
    @{action=$Action; marker=$MarkerName} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidenceRoot 'request.json') -Encoding ASCII
    Start-Service -Name $serviceName
    Wait-ServiceState 'Running'
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while (-not (Test-Path -LiteralPath $marker)) {
        if ([DateTime]::UtcNow -ge $deadline) { throw "$Action marker timeout" }
        Start-Sleep -Milliseconds 100
    }
    $result = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
    if (-not $result.success) { throw "$Action failed: $($result.error)" }
    if ($result.sid -ne $script:serviceSid.Value) { throw "$Action ran under unexpected SID $($result.sid)" }
    if ([string]::IsNullOrWhiteSpace($result.user_profile)) { throw "$Action has no service profile" }
    if ($result.enrollment_root -ne $enrollmentRoot) { throw "$Action used unexpected enrollment root" }
    if (-not $result.identity_match -or $result.ready) { throw "$Action returned invalid identity/readiness evidence" }
    Stop-Service -Name $serviceName
    Wait-ServiceState 'Stopped'
    if (Get-Process -Id ([int]$result.pid) -ErrorAction SilentlyContinue) { throw "$Action process $($result.pid) remains alive" }
    return $result
}

New-Item -ItemType Directory -Path $workRoot | Out-Null
try {
    Assert-RepositorySafety
    Assert-Administrator
    if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) { throw 'EXISTING_NBSR_SERVICE_BLOCKER' }
    if (Test-Path -LiteralPath $enrollmentRoot) { throw 'EXISTING_ENROLLMENT_STATE_BLOCKER' }
    if (Test-Path -LiteralPath $programDataRoot) { throw 'EXISTING_ENROLLMENT_STATE_BLOCKER: existing ProgramData\NBSR tree cannot be safely reprovisioned' }

    $networkBefore = Get-NetworkSnapshot
    Save-NetworkInspection 'before' $networkBefore

    Push-Location $moduleRoot
    try {
        go build -trimpath -o $builtExecutable ./cmd/enrollment-storage-scm-gate
        Assert-ExitCode 'build SCM gate service'
    } finally { Pop-Location }

    $binaryPath = ('"{0}" --evidence "{1}"' -f $serviceExecutable, $evidenceRoot)
    & sc.exe create $serviceName "binPath= $binaryPath" 'type= own' 'start= demand' "obj= $serviceAccount" | Out-Null
    Assert-ExitCode 'create NBSRClient service'
    $serviceCreated = $true
    $script:serviceSid = ([Security.Principal.NTAccount]$serviceAccount).Translate([Security.Principal.SecurityIdentifier])
    $scmConfiguration = (& sc.exe qc $serviceName | Out-String).Trim()
    Assert-ExitCode 'read back NBSRClient service configuration'

    New-Item -ItemType Directory -Path $programDataRoot | Out-Null
    $programDataCreated = $true
    New-Item -ItemType Directory -Path $enrollmentRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $evidenceRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $harnessRoot -Force | Out-Null
    foreach ($path in @($programDataRoot, (Join-Path $programDataRoot 'GoClient'), $enrollmentRoot, $evidenceRoot, $harnessRoot)) {
        Set-ExactGateAcl $path $script:serviceSid
    }
    Copy-Item -LiteralPath $builtExecutable -Destination $serviceExecutable
    Set-ExactGateAcl $serviceExecutable $script:serviceSid

    $store = Invoke-GateAction 'STORE' 'store.json'
    $keyPath = Join-Path $enrollmentRoot 'enrollment-state.integrity-key'
    $statePath = Join-Path $enrollmentRoot 'enrollment-state.bin'
    $keyHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $keyPath).Hash
    $stateHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $statePath).Hash
    $load1 = Invoke-GateAction 'LOAD' 'load-1.json'
    $load2 = Invoke-GateAction 'LOAD' 'load-2.json'
    if (@(@($store.pid, $load1.pid, $load2.pid) | Select-Object -Unique).Count -ne 3) { throw 'SCM did not create three distinct service processes' }
    if ($store.sid -ne $load1.sid -or $store.sid -ne $load2.sid) { throw 'service SID changed across restart' }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $keyPath).Hash -ne $keyHash) { throw 'integrity key changed during restart/load' }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $statePath).Hash -ne $stateHash) { throw 'authenticated state changed during restart/load' }

    [ordered]@{
        Service = $serviceName
        Account = $serviceAccount
        SID = $script:serviceSid.Value
        SCMConfiguration = $scmConfiguration
        Store = $store
        Load1 = $load1
        Load2 = $load2
        IntegrityKeySHA256Stable = $keyHash
        AuthenticatedStateSHA256Stable = $stateHash
        NegativeIdentityTest = 'NOT EXECUTED'
    } | ConvertTo-Json -Depth 6
} finally {
    $cleanupErrors = [Collections.Generic.List[string]]::new()
    if ($serviceCreated) {
        try {
            Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
            & sc.exe delete $serviceName | Out-Null
            $deleteDeadline = [DateTime]::UtcNow.AddSeconds(15)
            while ((Get-Service -Name $serviceName -ErrorAction SilentlyContinue) -and [DateTime]::UtcNow -lt $deleteDeadline) {
                Start-Sleep -Milliseconds 100
            }
            if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) { throw 'temporary NBSRClient service was not deleted' }
            $serviceCreated = $false
        } catch {
            $cleanupErrors.Add($_.Exception.Message)
        }
    }
    if ($programDataCreated) {
        try {
            $resolved = [IO.Path]::GetFullPath($programDataRoot)
            $expected = [IO.Path]::GetFullPath((Join-Path $env:ProgramData 'NBSR'))
            if ($resolved -ne $expected) { throw 'refusing cleanup outside exact test ProgramData root' }
            Remove-Item -LiteralPath $resolved -Recurse -Force
            $programDataCreated = $false
        } catch {
            $cleanupErrors.Add($_.Exception.Message)
        }
    }
    try {
        $networkAfter = Get-NetworkSnapshot
        Save-NetworkInspection 'after' $networkAfter
        $beforeJSON = $networkBefore | ConvertTo-Json -Depth 8 -Compress
        $afterJSON = $networkAfter | ConvertTo-Json -Depth 8 -Compress
        if ($null -ne $networkBefore -and $beforeJSON -ne $afterJSON) {
            throw 'NETWORK_CONFIGURATION_CHANGED: inspect retained baseline under the temporary work directory; no repair was attempted'
        }
        if ($null -ne $networkBefore) { Write-Output 'NETWORK_CONFIGURATION_CHANGED=NO' }
    } catch {
        $cleanupErrors.Add($_.Exception.Message)
    }
    if ($cleanupErrors.Count -eq 0) {
        if (Test-Path -LiteralPath $workRoot) { Remove-Item -LiteralPath $workRoot -Recurse -Force }
    } else {
        throw ('gate cleanup/safety failure; evidence retained at {0}: {1}' -f $workRoot, ($cleanupErrors -join '; '))
    }
}

Push-Location $moduleRoot
try {
    go test ./internal/authority -count=1
    go test ./internal/identity -count=1
    go test -race ./internal/authority -count=1
    go test -race ./internal/identity -count=1
    go vet ./internal/authority ./internal/identity
} finally { Pop-Location }

Push-Location $repoRoot
try {
    git diff --check
    git status --short
    git rev-parse HEAD
    git rev-parse origin/codex/nbsr-v3-wp0-wp1
    git rev-parse main
    git rev-parse origin/main
} finally { Pop-Location }
