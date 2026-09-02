[CmdletBinding()]
param(
    [string]$OutputRoot,
    [double]$WarmupSeconds = 2,
    [double]$DurationSeconds = 8
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdministrator)) {
    [Console]::Error.WriteLine("MANUAL_ELEVATION_REQUIRED: Open PowerShell as Administrator and run:")
    [Console]::Error.WriteLine("pwsh -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"")
    exit 5
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Runner = Join-Path $RepoRoot "scripts\run_max_throughput_v2_stage3_profile.py"
$WptRoot = "C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit"
$Xperf = Join-Path $WptRoot "xperf.exe"
$Wpa = Join-Path $WptRoot "wpa.exe"
foreach ($required in @($Runner, $Xperf, $Wpa)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required file unavailable: $required"
    }
}

$Python = (Get-Command python -ErrorAction Stop).Source
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputRoot = "C:\NBSR-build\max-throughput-v2-stage3-$stamp"
}
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) {
    throw "Output root exists; refusing to overwrite evidence: $OutputRoot"
}
New-Item -ItemType Directory -Path $OutputRoot | Out-Null

$Control = Join-Path $OutputRoot "control"
$Profiled = Join-Path $OutputRoot "profiled"
$RawTrace = Join-Path $OutputRoot "stage3-raw.etl"
$Trace = Join-Path $OutputRoot "stage3.etl"
$env:CARGO_TARGET_DIR = "C:\NBSR-build\b2-v2-profile"
$arguments = @(
    $Runner,
    "--warmup-seconds", $WarmupSeconds.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--duration-seconds", $DurationSeconds.ToString([Globalization.CultureInfo]::InvariantCulture)
)

function Invoke-Workload([string]$Label, [string]$Destination) {
    $started = Get-Date
    & $Python @arguments --output $Destination 2>&1 | Tee-Object -FilePath (Join-Path $OutputRoot "$Label.log")
    if ($LASTEXITCODE -ne 0) { throw "$Label workload failed: $LASTEXITCODE" }
    return [ordered]@{
        label = $Label
        started_utc = $started.ToUniversalTime().ToString("o")
        ended_utc = (Get-Date).ToUniversalTime().ToString("o")
        output = $Destination
    }
}

$startArguments = @(
    "-on", "PROC_THREAD+LOADER+PROFILE+CSWITCH+DISPATCHER",
    "-stackwalk", "Profile+CSwitch+ReadyThread",
    "-BufferSize", "1024", "-MinBuffers", "256", "-MaxBuffers", "768",
    "-f", $RawTrace
)
$traceStarted = $false
try {
    $controlRun = Invoke-Workload "control" $Control
    & $Xperf @startArguments 2>&1 | Set-Content (Join-Path $OutputRoot "xperf-start.log")
    if ($LASTEXITCODE -ne 0) { throw "xperf start failed: $LASTEXITCODE" }
    $traceStarted = $true
    $profiledRun = Invoke-Workload "profiled" $Profiled
}
finally {
    if ($traceStarted) {
        & $Xperf -d $Trace 2>&1 | Set-Content (Join-Path $OutputRoot "xperf-stop.log")
        if ($LASTEXITCODE -ne 0) { throw "xperf stop/merge failed: $LASTEXITCODE" }
    }
}

$traceStats = & $Xperf -i $Trace -tle -a tracestats 2>&1 | Out-String
$traceStats | Set-Content (Join-Path $OutputRoot "trace-stats.txt")
$lostMatch = [regex]::Match($traceStats, "Total # Lost Events\s*:\s*(\d+)")
if (-not $lostMatch.Success) { throw "Unable to determine lost-event count" }
$lostEvents = [int64]$lostMatch.Groups[1].Value

$oldSymbols = $env:_NT_SYMBOL_PATH
$env:_NT_SYMBOL_PATH = "C:\NBSR-build\b2-v2-profile\release"
try {
    & $Xperf -i $Trace -tle -symbols -a profile -detail -ao (Join-Path $OutputRoot "cpu-profile-detail.txt") -ae (Join-Path $OutputRoot "cpu-profile-errors.txt")
    & $Xperf -i $Trace -tle -a cswitch -process -thread -ao (Join-Path $OutputRoot "cswitch-process-thread.txt")
    & $Xperf -i $Trace -tle -a readythread -counts -list -stacks -ao (Join-Path $OutputRoot "readythread.txt")
    & $Xperf -i $Trace -tle -a activityintervals -thread -interval 1000000 -ao (Join-Path $OutputRoot "thread-activity.txt")
    & $Xperf -i $Trace -tle -a process -thread -withcmdline -ao (Join-Path $OutputRoot "process-thread.txt")
}
finally {
    $env:_NT_SYMBOL_PATH = $oldSymbols
}

$profileText = Get-Content -Raw (Join-Path $OutputRoot "cpu-profile-detail.txt")
$symbolChecks = [ordered]@{
    perf_direct_peer = [bool]($profileText -match "perf_direct_peer\.exe!_R")
    perf_rust_source = [bool]($profileText -match "perf_rust_source\.exe!_R")
    wp8_interop_server = [bool]($profileText -match "wp8_interop_server\.exe!_R")
}

$controlManifest = Get-Content -Raw (Join-Path $Control "manifest.json") | ConvertFrom-Json
$profiledManifest = Get-Content -Raw (Join-Path $Profiled "manifest.json") | ConvertFrom-Json
$overhead = @()
foreach ($controlCell in $controlManifest.records) {
    $profiledCell = $profiledManifest.records | Where-Object {
        $_.path -eq $controlCell.path -and $_.groups -eq $controlCell.groups
    } | Select-Object -First 1
    $fraction = 1.0 - ([double]$profiledCell.operations_per_second / [double]$controlCell.operations_per_second)
    $overhead += [ordered]@{
        path = $controlCell.path
        groups = $controlCell.groups
        control_gbps = $controlCell.aggregate_application_gbps
        profiled_gbps = $profiledCell.aggregate_application_gbps
        throughput_overhead_fraction = $fraction
    }
}
$overhead | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $OutputRoot "profile-overhead.json") -Encoding utf8

[ordered]@{
    schema = "nbsr-max-throughput-v2-stage3-capture-v1"
    timestamp_utc = (Get-Date).ToUniversalTime().ToString("o")
    git = [ordered]@{
        branch = (& git -C $RepoRoot branch --show-current).Trim()
        sha = (& git -C $RepoRoot rev-parse HEAD).Trim()
    }
    workload = [ordered]@{
        payload_bytes = 16384
        streams_per_group = 1
        outstanding_per_stream = 4
        groups = @(1, 2, 4)
        paths = @("direct", "nbsr")
        runtime_workers = 1
    }
    xperf_start_arguments = $startArguments
    trace = $Trace
    lost_events = $lostEvents
    symbol_checks = $symbolChecks
    control = $controlRun
    profiled = $profiledRun
} | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $OutputRoot "metadata.json") -Encoding utf8

if ($lostEvents -ne 0 -or $symbolChecks.Values -contains $false) {
    throw "TRACE_INTEGRITY_FAILED: lost_events=$lostEvents symbols=$($symbolChecks.Values -join ',')"
}

Write-Host "Capture completed: $OutputRoot"
Write-Host "Open with: & '$Wpa' '$Trace'"
