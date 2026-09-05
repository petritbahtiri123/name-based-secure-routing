[CmdletBinding()]
param([string]$OutputRoot, [switch]$DatagramDropsOnly)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    [Console]::Error.WriteLine('MANUAL_ELEVATION_REQUIRED: ETW provider capture requires Administrator.')
    exit 5
}
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Xperf = (Get-Command xperf.exe -ErrorAction Stop).Source
$Python = (Get-Command python.exe -ErrorAction Stop).Source
$Runner = Join-Path $PSScriptRoot 'run_b4b_task4l.py'
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = 'C:\NBSR-build\b4b-task4l-etw-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
}
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Refusing existing evidence: $OutputRoot" }
if ((& git -C $RepoRoot branch --show-current).Trim() -ne 'codex/nbsr-v3-wp0-wp1') {
    throw 'Unexpected benchmark branch'
}
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$Target = 'C:\NBSR-build\b4b-task4k'
$RawTrace = Join-Path $OutputRoot 'kernel-raw.etl'
$Trace = Join-Path $OutputRoot 'kernel.etl'
$CaptureArguments = @(
    '-on', 'PROC_THREAD+LOADER+PROFILE+CSWITCH+DISPATCHER+NETWORKTRACE+TIMER',
    '-stackwalk', 'Profile',
    '-BufferSize', '1024', '-MinBuffers', '128', '-MaxBuffers', '512',
    '-f', $RawTrace
)
$CaptureTool = $Xperf
$StopArguments = @('-d', $Trace)
if ($DatagramDropsOnly) {
    $CaptureTool = (Get-Command wpr.exe -ErrorAction Stop).Source
    $Profile = Join-Path $PSScriptRoot 'performance\task4l-afd.wprp'
    $Trace = Join-Path $OutputRoot 'afd-drops.etl'
    $Instance = 'NBSRTask4lAFD-' + [guid]::NewGuid().ToString('N')
    $CaptureArguments = @('-start', "${Profile}!NBSRTask4lAFD", '-filemode', '-instancename', $Instance,
        '-recordtempto', $OutputRoot)
    $StopArguments = @('-stop', $Trace, '-skipPdbGen', '-instancename', $Instance)
    Copy-Item -LiteralPath $Profile -Destination (Join-Path $OutputRoot 'capture-profile.wprp')
}
function Invoke-BoundaryWorkload([string]$Mode) {
    & $Python -u $Runner --output (Join-Path $OutputRoot $Mode) --target $Target --mode $Mode 2>&1 |
        Tee-Object -FilePath (Join-Path $OutputRoot "$Mode.log") | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "$Mode workload failed: $LASTEXITCODE" }
}
# Verify that WPR can actually collect the provider before expensive controls.
# Enumeration alone did not detect the failed provider startup.
if ($DatagramDropsOnly) {
    $ProbeTrace = Join-Path $OutputRoot 'afd-preflight.etl'
    $probeStarted = $false
    try {
        & $CaptureTool @CaptureArguments 2>&1 | Set-Content (Join-Path $OutputRoot 'preflight-start.log')
        if ($LASTEXITCODE -ne 0) { throw "AFD preflight start failed: $LASTEXITCODE" }
        $probeStarted = $true
        $probeSocket = [Net.Sockets.UdpClient]::new([Net.Sockets.AddressFamily]::InterNetwork)
        try {
            $probeSocket.Client.Bind([Net.IPEndPoint]::new([Net.IPAddress]::Loopback, 0))
        }
        finally { $probeSocket.Dispose() }
    }
    finally {
        if ($probeStarted) {
            & $CaptureTool -stop $ProbeTrace -skipPdbGen -instancename $Instance 2>&1 |
                Set-Content (Join-Path $OutputRoot 'preflight-stop.log')
            if ($LASTEXITCODE -ne 0) { throw "AFD preflight stop failed: $LASTEXITCODE" }
        }
    }
    $probeEvents = @(Get-WinEvent -FilterHashtable @{
        Path = $ProbeTrace; ProviderName = 'Microsoft-Windows-Winsock-AFD'
    } -Oldest -ErrorAction Stop)
    $probeIds = @($probeEvents | Select-Object -ExpandProperty Id -Unique)
    if (1000 -notin $probeIds -or 1030 -notin $probeIds) {
        throw 'AFD preflight lacks required socket-create/bind events; controls were not started'
    }
    [ordered]@{ status = 'PASS'; event_ids = $probeIds; trace = $ProbeTrace } |
        ConvertTo-Json | Set-Content (Join-Path $OutputRoot 'preflight.json') -Encoding utf8
    Write-Host 'AFD_PREFLIGHT_PASS: socket-create/bind events captured'
}
# Build and measure controls before the measured trace. No capture process controls admission.
Invoke-BoundaryWorkload 'none'
$started = $false
try {
    & $CaptureTool @CaptureArguments 2>&1 | Set-Content (Join-Path $OutputRoot 'start.log')
    if ($LASTEXITCODE -ne 0) { throw "ETW start failed: $LASTEXITCODE" }
    $started = $true
    Invoke-BoundaryWorkload 'etw'
}
finally {
    if ($started) {
        & $CaptureTool @StopArguments 2>&1 | Set-Content (Join-Path $OutputRoot 'stop.log')
        if ($LASTEXITCODE -ne 0) { throw "ETW stop failed: $LASTEXITCODE" }
    }
}
$stats = & $Xperf -i $Trace -tle -a tracestats 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) { throw 'Trace statistics failed' }
$stats | Set-Content (Join-Path $OutputRoot 'trace-stats.txt')
$lost = [regex]::Match($stats, 'Total # Lost Events\s*:\s*(\d+)')
& $Python $Runner --compare-etw $OutputRoot
if ($LASTEXITCODE -ne 0) { throw 'Matched observer comparison failed; preserve traces' }
[ordered]@{
    schema = 'nbsr-b4b-task4l-etw-v1'
    sha = (& git -C $RepoRoot rev-parse HEAD).Trim()
    timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
    arguments = $CaptureArguments
    capture_tool = $CaptureTool
    datagram_drops_only = [bool]$DatagramDropsOnly
    trace = $Trace
    trace_sha256 = (Get-FileHash -LiteralPath $Trace -Algorithm SHA256).Hash.ToLowerInvariant()
    lost_events = $(if ($lost.Success) { [int64]$lost.Groups[1].Value } else { $null })
    classification = 'DIAGNOSTIC; see observer-comparison.json; causal attribution pending event analysis'
    symbols = 'PDBs in C:\NBSR-build\b4b-task4k\release; export after capture'
} | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $OutputRoot 'metadata.json') -Encoding utf8
if (-not $lost.Success -or [int64]$lost.Groups[1].Value -ne 0) {
    throw "Trace loss or unknown integrity; preserve $OutputRoot"
}
Write-Host "CAPTURE_READY: $OutputRoot"
