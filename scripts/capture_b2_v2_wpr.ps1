[CmdletBinding()]
param(
    [string]$OutputRoot,
    [double]$WarmupSeconds = 3,
    [double]$DurationSeconds = 10,
    [int]$Repeats = 1,
    [string]$Streams = "8",
    [string]$Payloads = "16384",
    [string]$Paths = "direct,nbsr",
    [string]$Affinities = "4",
    [int]$MaxRepeats = 1
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdministrator)) {
    $quotedScript = '"' + $PSCommandPath + '"'
    Write-Error ("MANUAL_ELEVATION_REQUIRED: Open PowerShell as Administrator and run:`n" +
        "pwsh -NoProfile -ExecutionPolicy Bypass -File $quotedScript")
    exit 5
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ProfileRunner = Join-Path $RepoRoot "scripts\profile_b2_v2.py"
$WptRoot = "C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit"
$Wpr = Join-Path $WptRoot "wpr.exe"
$Wpa = Join-Path $WptRoot "wpa.exe"
$WpaExporter = Join-Path $WptRoot "wpaexporter.exe"
$Xperf = Join-Path $WptRoot "xperf.exe"

foreach ($required in @($ProfileRunner, $Wpr, $Wpa, $WpaExporter, $Xperf)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required file is unavailable: $required"
    }
}

$Python = (Get-Command python -ErrorAction Stop).Source
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputRoot = "C:\NBSR-build\b2-v2-wpr-manual-$stamp"
}
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$ControlOutput = Join-Path $OutputRoot "control"
$ProfiledOutput = Join-Path $OutputRoot "profiled"
$RawTracePath = Join-Path $OutputRoot "b2-v2-cpu-raw.etl"
$TracePath = Join-Path $OutputRoot "b2-v2-cpu.etl"

if (Test-Path -LiteralPath $OutputRoot) {
    throw "Output root already exists; refusing to overwrite evidence: $OutputRoot"
}

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$oldTargetDir = $env:CARGO_TARGET_DIR
$env:CARGO_TARGET_DIR = "C:\NBSR-build\b2-v2-profile"

$BenchmarkArguments = @(
    $ProfileRunner,
    "--warmup-seconds", $WarmupSeconds.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--duration-seconds", $DurationSeconds.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--repeats", $Repeats.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--streams", $Streams,
    "--payloads", $Payloads,
    "--paths", $Paths,
    "--affinities", $Affinities,
    "--max-repeats", $MaxRepeats.ToString([Globalization.CultureInfo]::InvariantCulture)
)

function Run-Benchmark {
    param([Parameter(Mandatory)][string]$Label, [Parameter(Mandatory)][string]$Destination)
    $logPath = Join-Path $OutputRoot "$Label.log"
    $arguments = @($BenchmarkArguments + @("--output", $Destination))
    $started = Get-Date
    & $Python @arguments 2>&1 | Tee-Object -FilePath $logPath
    $exitCode = $LASTEXITCODE
    $ended = Get-Date
    if ($exitCode -ne 0) {
        throw "$Label benchmark failed with exit code $exitCode; see $logPath"
    }
    return [ordered]@{
        label = $Label
        command = @($Python) + $arguments
        started_utc = $started.ToUniversalTime().ToString("o")
        ended_utc = $ended.ToUniversalTime().ToString("o")
        elapsed_seconds = ($ended - $started).TotalSeconds
        output = $Destination
        log = $logPath
    }
}

function Read-RawCells([string]$Root) {
    $cells = @{}
    Get-ChildItem -LiteralPath (Join-Path $Root "raw") -Filter "*-a*-s*-r*.json" | ForEach-Object {
        $record = Get-Content -Raw -LiteralPath $_.FullName | ConvertFrom-Json
        $key = $_.Name
        $cells[$key] = $record
    }
    return $cells
}

function Write-ProfileOverhead {
    $controlCells = Read-RawCells $ControlOutput
    $profiledCells = Read-RawCells $ProfiledOutput
    $matched = @()
    foreach ($key in ($controlCells.Keys | Sort-Object)) {
        if (-not $profiledCells.ContainsKey($key)) { continue }
        $controlOps = [double]$controlCells[$key].operations_per_second
        $profiledOps = [double]$profiledCells[$key].operations_per_second
        $overhead = if ($controlOps -gt 0) { 1.0 - ($profiledOps / $controlOps) } else { $null }
        $matched += [ordered]@{
            cell = $key
            control_operations_per_second = $controlOps
            profiled_operations_per_second = $profiledOps
            throughput_overhead_fraction = $overhead
            within_five_percent = ($null -ne $overhead -and $overhead -le 0.05)
        }
    }
    $valid = @($matched | Where-Object { $null -ne $_.throughput_overhead_fraction })
    $sorted = @($valid.throughput_overhead_fraction | Sort-Object)
    $median = if ($sorted.Count) { $sorted[[math]::Floor(($sorted.Count - 1) / 2)] } else { $null }
    $report = [ordered]@{
        schema = "nbsr-b2-v2-wpr-overhead-v1"
        matched_cells = $matched.Count
        median_throughput_overhead_fraction = $median
        maximum_throughput_overhead_fraction = if ($sorted.Count) { $sorted[-1] } else { $null }
        all_cells_within_five_percent = ($matched.Count -gt 0 -and @($matched | Where-Object { -not $_.within_five_percent }).Count -eq 0)
        cells = $matched
    }
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputRoot "profile-overhead.json") -Encoding utf8
    return $report
}

$traceStarted = $false
$controlRun = $null
$profiledRun = $null
$XperfStartArguments = @(
    "-on", "PROC_THREAD+LOADER+PROFILE",
    "-stackwalk", "Profile",
    "-BufferSize", "1024",
    "-MinBuffers", "128",
    "-MaxBuffers", "256",
    "-f", $RawTracePath
)
try {
    $controlRun = Run-Benchmark -Label "control" -Destination $ControlOutput
    $startOutput = & $Xperf @XperfStartArguments 2>&1 | Out-String
    $startOutput | Set-Content -LiteralPath (Join-Path $OutputRoot "xperf-start.log")
    if ($LASTEXITCODE -ne 0) {
        throw "xperf sampled CPU capture failed to start with exit code $LASTEXITCODE`n$startOutput"
    }
    $traceStarted = $true
    $profiledRun = Run-Benchmark -Label "profiled" -Destination $ProfiledOutput
}
finally {
    if ($traceStarted) {
        try {
            $stopOutput = & $Xperf -d $TracePath 2>&1 | Out-String
            $stopOutput | Set-Content -LiteralPath (Join-Path $OutputRoot "xperf-stop.log")
            if ($LASTEXITCODE -ne 0) {
                throw "xperf sampled CPU capture failed to stop/merge with exit code $LASTEXITCODE`n$stopOutput"
            }
        }
        catch {
            $_ | Out-String | Set-Content -LiteralPath (Join-Path $OutputRoot "xperf-stop-error.log")
            throw
        }
    }
    $env:CARGO_TARGET_DIR = $oldTargetDir
}

$overheadReport = Write-ProfileOverhead

$traceStats = & $Xperf -i $TracePath -tle -a tracestats 2>&1 | Out-String
$traceStatsExit = $LASTEXITCODE
$traceStats | Set-Content -LiteralPath (Join-Path $OutputRoot "trace-stats.txt") -Encoding utf8
if ($traceStatsExit -ne 0) {
    throw "xperf trace statistics failed with exit code $traceStatsExit"
}
$lostMatch = [regex]::Match($traceStats, "Total # Lost Events\s*:\s*(\d+)")
if (-not $lostMatch.Success) {
    throw "Could not determine lost-event count from xperf output"
}
$lostEvents = [int64]$lostMatch.Groups[1].Value

$profileDetail = Join-Path $OutputRoot "cpu-profile-detail.txt"
$profileErrors = Join-Path $OutputRoot "cpu-profile-errors.txt"
$oldSymbolPath = $env:_NT_SYMBOL_PATH
$env:_NT_SYMBOL_PATH = "C:\NBSR-build\b2-v2-profile\release"
try {
    & $Xperf -i $TracePath -tle -symbols -a profile -detail -ao $profileDetail -ae $profileErrors
    if ($LASTEXITCODE -ne 0) {
        throw "xperf CPU profile export failed with exit code $LASTEXITCODE"
    }
}
finally {
    $env:_NT_SYMBOL_PATH = $oldSymbolPath
}
$profileText = Get-Content -Raw -LiteralPath $profileDetail
$symbolChecks = [ordered]@{
    perf_direct_peer = [bool]($profileText -match "perf_direct_peer\.exe!_R")
    perf_rust_source = [bool]($profileText -match "perf_rust_source\.exe!_R")
    wp8_interop_server = [bool]($profileText -match "wp8_interop_server\.exe!_R")
}
$symbolsReadable = -not ($symbolChecks.Values -contains $false)
$integrityReport = [ordered]@{
    schema = "nbsr-b2-v2-wpr-trace-integrity-v1"
    trace_bytes = (Get-Item -LiteralPath $TracePath).Length
    lost_events = $lostEvents
    zero_lost_events = ($lostEvents -eq 0)
    rust_symbols_readable = $symbolsReadable
    symbol_checks = $symbolChecks
}
$integrityReport | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputRoot "trace-integrity.json") -Encoding utf8

$gitSha = (& git -C $RepoRoot rev-parse HEAD).Trim()
$gitBranch = (& git -C $RepoRoot branch --show-current).Trim()
$symbols = Get-ChildItem -LiteralPath "C:\NBSR-build\b2-v2-profile\release" -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in @(".exe", ".pdb") -and $_.BaseName -in @("perf_direct_peer", "perf_rust_source", "wp8_interop_server") } |
    ForEach-Object {
        [ordered]@{ path = $_.FullName; bytes = $_.Length; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant() }
    }

[ordered]@{
    schema = "nbsr-b2-v2-wpr-capture-v1"
    timestamp_utc = (Get-Date).ToUniversalTime().ToString("o")
    git = [ordered]@{ branch = $gitBranch; sha = $gitSha }
    workload = [ordered]@{
        warmup_seconds = $WarmupSeconds
        duration_seconds = $DurationSeconds
        repeats = $Repeats
        maximum_repeats = $MaxRepeats
        streams = $Streams
        payloads = $Payloads
        paths = $Paths
        affinities = $Affinities
    }
    capture_mode = "xperf-sampled-cpu-only"
    blocked_time = "not-captured"
    xperf_start_arguments = $XperfStartArguments
    tools = [ordered]@{ python = $Python; wpr = $Wpr; wpa = $Wpa; wpaexporter = $WpaExporter; xperf = $Xperf }
    trace = $TracePath
    control = $controlRun
    profiled = $profiledRun
    symbols = @($symbols)
} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $OutputRoot "metadata.json") -Encoding utf8

if ($lostEvents -ne 0 -or -not $symbolsReadable) {
    throw "TRACE_INTEGRITY_FAILED: lost_events=$lostEvents rust_symbols_readable=$symbolsReadable"
}
if (-not $overheadReport.all_cells_within_five_percent) {
    throw "PROFILE_OVERHEAD_FAILED: see $(Join-Path $OutputRoot 'profile-overhead.json')"
}

Write-Host "Capture completed: $TracePath"
Write-Host "Open the trace with:"
Write-Host "& '$Wpa' '$TracePath'"
Write-Host "Inspect CPU Usage (Sampled) by Process/Thread/Stack. Blocked time is not captured by this trace."
