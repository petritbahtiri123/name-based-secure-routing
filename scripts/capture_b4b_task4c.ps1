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
$Runner = Join-Path $RepoRoot "scripts\run_b4b_task4c_profile.py"
$WptRoot = "C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit"
$Xperf = Join-Path $WptRoot "xperf.exe"
$Wpa = Join-Path $WptRoot "wpa.exe"
foreach ($required in @($Runner, $Xperf, $Wpa)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required file unavailable: $required" }
}

$Python = (Get-Command python -ErrorAction Stop).Source
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputRoot = "C:\NBSR-build\b4b-task4c-$stamp"
}
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw "Output root exists; refusing to overwrite evidence: $OutputRoot" }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null

$Control = Join-Path $OutputRoot "control"
$Profiled = Join-Path $OutputRoot "profiled"
$KernelRaw = Join-Path $OutputRoot "task4c-kernel-raw.etl"
$KernelTrace = Join-Path $OutputRoot "task4c-kernel.etl"
$NetworkRaw = Join-Path $OutputRoot "task4c-network-raw.etl"
$NetworkTrace = Join-Path $OutputRoot "task4c-network.etl"
$Trace = Join-Path $OutputRoot "task4c.etl"
$NetworkSession = "NBSRTask4cNetwork"
$env:CARGO_TARGET_DIR = "C:\NBSR-build\b4b-task4c-profile"
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

$kernelArguments = @(
    "-on", "PROC_THREAD+LOADER+PROFILE+CSWITCH+DISPATCHER",
    "-stackwalk", "Profile+CSwitch+ReadyThread",
    "-BufferSize", "1024", "-MinBuffers", "256", "-MaxBuffers", "768",
    "-f", $KernelRaw
)
$networkArguments = @(
    "-start", $NetworkSession,
    "-on", "Microsoft-Windows-Winsock-AFD+Microsoft-Windows-TCPIP",
    "-BufferSize", "256", "-MinBuffers", "128", "-MaxBuffers", "512",
    "-f", $NetworkRaw
)
$kernelStarted = $false
$networkStarted = $false
try {
    $controlRun = Invoke-Workload "control" $Control
    & $Xperf @kernelArguments 2>&1 | Set-Content (Join-Path $OutputRoot "xperf-kernel-start.log")
    if ($LASTEXITCODE -ne 0) { throw "xperf kernel start failed: $LASTEXITCODE" }
    $kernelStarted = $true
    & $Xperf @networkArguments 2>&1 | Set-Content (Join-Path $OutputRoot "xperf-network-start.log")
    if ($LASTEXITCODE -ne 0) { throw "xperf network start failed: $LASTEXITCODE" }
    $networkStarted = $true
    $profiledRun = Invoke-Workload "profiled" $Profiled
}
finally {
    if ($networkStarted) {
        & $Xperf -stop $NetworkSession -d $NetworkTrace 2>&1 | Set-Content (Join-Path $OutputRoot "xperf-network-stop.log")
        if ($LASTEXITCODE -ne 0) { throw "xperf network stop failed: $LASTEXITCODE" }
    }
    if ($kernelStarted) {
        & $Xperf -d $KernelTrace 2>&1 | Set-Content (Join-Path $OutputRoot "xperf-kernel-stop.log")
        if ($LASTEXITCODE -ne 0) { throw "xperf kernel stop failed: $LASTEXITCODE" }
    }
}

& $Xperf -merge $KernelTrace $NetworkTrace $Trace 2>&1 | Set-Content (Join-Path $OutputRoot "xperf-merge.log")
if ($LASTEXITCODE -ne 0) { throw "xperf merge failed: $LASTEXITCODE" }
$kernelTraceStats = & $Xperf -i $KernelTrace -tle -a tracestats 2>&1 | Out-String
$kernelTraceStats | Set-Content (Join-Path $OutputRoot "kernel-trace-stats.txt")
$kernelLostMatch = [regex]::Match($kernelTraceStats, "Total # Lost Events\s*:\s*(\d+)")
if (-not $kernelLostMatch.Success) { throw "Unable to determine kernel lost-event count" }
$kernelLostEvents = [int64]$kernelLostMatch.Groups[1].Value
$networkTraceStats = & $Xperf -i $NetworkTrace -tle -a tracestats 2>&1 | Out-String
$networkTraceStats | Set-Content (Join-Path $OutputRoot "network-trace-stats.txt")
$networkLostMatch = [regex]::Match($networkTraceStats, "Total # Lost Events\s*:\s*(\d+)")
if (-not $networkLostMatch.Success) { throw "Unable to determine network lost-event count" }
$networkLostEvents = [int64]$networkLostMatch.Groups[1].Value
$network_trace_valid = $networkLostEvents -eq 0

$oldSymbols = $env:_NT_SYMBOL_PATH
$env:_NT_SYMBOL_PATH = "C:\NBSR-build\b4b-task4c-profile\release"
try {
    & $Xperf -i $KernelTrace -tle -symbols -a profile -detail -ao (Join-Path $OutputRoot "cpu-profile-detail.txt") -ae (Join-Path $OutputRoot "cpu-profile-errors.txt")
    & $Xperf -i $KernelTrace -tle -a cswitch -process -thread -ao (Join-Path $OutputRoot "cswitch-process-thread.txt")
    & $Xperf -i $KernelTrace -tle -a readythread -counts -list -stacks -ao (Join-Path $OutputRoot "readythread.txt")
    & $Xperf -i $KernelTrace -tle -a activityintervals -thread -interval 1000000 -ao (Join-Path $OutputRoot "thread-activity.txt")
    & $Xperf -i $KernelTrace -tle -a process -thread -withcmdline -ao (Join-Path $OutputRoot "process-thread.txt")
}
finally {
    $env:_NT_SYMBOL_PATH = $oldSymbols
}

$profileText = Get-Content -Raw (Join-Path $OutputRoot "cpu-profile-detail.txt")
$symbolChecks = [ordered]@{
    perf_rust_source = [bool]($profileText -match "perf_rust_source\.exe!_R")
    wp8_interop_server = [bool]($profileText -match "wp8_interop_server\.exe!_R")
}
$controlManifest = Get-Content -Raw (Join-Path $Control "manifest.json") | ConvertFrom-Json
$profiledManifest = Get-Content -Raw (Join-Path $Profiled "manifest.json") | ConvertFrom-Json
$overhead = @()
foreach ($controlCell in $controlManifest.records) {
    $profiledCell = $profiledManifest.records | Where-Object { $_.clients -eq $controlCell.clients } | Select-Object -First 1
    $controlRate = [double]$controlCell.successful_admissions / [double]$controlCell.admission_elapsed_seconds
    $profiledRate = [double]$profiledCell.successful_admissions / [double]$profiledCell.admission_elapsed_seconds
    $fraction = 1.0 - ($profiledRate / $controlRate)
    $overhead += [ordered]@{
        clients = $controlCell.clients
        control_admissions_per_second = $controlRate
        profiled_admissions_per_second = $profiledRate
        admission_rate_overhead_fraction = $fraction
    }
}
$overhead | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $OutputRoot "profile-overhead.json") -Encoding utf8

[ordered]@{
    schema = "nbsr-b4b-task4c-capture-v1"
    timestamp_utc = (Get-Date).ToUniversalTime().ToString("o")
    git = [ordered]@{
        branch = (& git -C $RepoRoot branch --show-current).Trim()
        sha = (& git -C $RepoRoot rev-parse HEAD).Trim()
    }
    workload = [ordered]@{ clients = @(64, 128); connections_per_client = 1 }
    xperf_kernel_arguments = $kernelArguments
    xperf_network_arguments = $networkArguments
    trace = $Trace
    kernel_lost_events = $kernelLostEvents
    network_lost_events = $networkLostEvents
    network_trace_valid = $network_trace_valid
    symbol_checks = $symbolChecks
    control = $controlRun
    profiled = $profiledRun
} | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $OutputRoot "metadata.json") -Encoding utf8

if ($kernelLostEvents -ne 0 -or $symbolChecks.Values -contains $false) {
    throw "TRACE_INTEGRITY_FAILED: kernel_lost_events=$kernelLostEvents symbols=$($symbolChecks.Values -join ',')"
}

Write-Host "Capture completed: $OutputRoot"
Write-Host "Open with: & '$Wpa' '$Trace'"
