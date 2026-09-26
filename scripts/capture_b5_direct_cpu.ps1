param()
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'ADMIN_REQUIRED: WPR CPU profiling requires an elevated process; no security policy is changed by this script.'
}
$branch = (& git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne 'codex/nbsr-v3-wp0-wp1') { throw 'Unexpected branch' }
$sha = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Source SHA unavailable' }
function Assert-CleanSource {
    $current = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $current -ne $sha) { throw 'Source SHA changed' }
    $dirty = & git status --porcelain
    if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Source must remain clean throughout capture' }
}
function Assert-NoWpr {
    $statusText = (& wpr -status 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0 -or $statusText -notmatch 'WPR is not recording') {
        throw 'WPR state unavailable or recording already active; existing sessions are never cancelled.'
    }
}
Assert-CleanSource
Assert-NoWpr
$wpr = (Get-Command wpr -ErrorAction Stop).Source
$xperf = (Get-Command xperf -ErrorAction Stop).Source
$root = Join-Path 'C:\NBSR-build' ('b5-direct-cpu-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
if (Test-Path -LiteralPath $root) { throw 'Output already exists' }
New-Item -ItemType Directory -Path $root | Out-Null
$definition = [ordered]@{
    classification = 'DIAGNOSTIC_ONLY_OBSERVER_QUALIFICATION_PENDING'
    repository_sha = $sha
    profile = 'CPU.light'
    attribution_scope = 'CPU/scheduling events; no call-stack attribution; observer impact remains unqualified'
    wpr_executable = $wpr
    xperf_executable = $xperf
    capture_script_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    workload = 'Direct secure QUIC; one shared physical-core representative,32streams,1KiB,depth1'
    fixed_rate = @(5206274500000, 150044089)
    rate_scope = 'Historical 2d7525f3 NBSR 70-percent rate, held fixed to diagnose Direct pacing; not current capacity'
    duration_seconds = 120
    repeats_per_arm = 5
    order = 'off/on odd;on/off even'
    failure_policy = 'Stop first failed cell; no replacement; preserve all artifacts'
    observer_gate = 'After capture: absolute median goodput/p99 impact <=5%; report five-repeat CV; reject causal attribution if distorted'
    privacy = 'Raw ETL may contain unrelated system process metadata; retain locally, export only owned peer PID/time windows'
}
$definition | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $root 'definition.json') -Encoding utf8
$failure = $null
try {
    if ((Get-PSDrive -Name C).Free -lt 5GB) { throw 'Insufficient free space for release preparation; no evidence deleted' }
    # Complete release preparation before starting any WPR recording.
    & python -c "from pathlib import Path; from scripts.run_p2a_established import build; build(Path('C:/NBSR-build/b4b-task4k'))" *> (Join-Path $root 'prepare.log')
    if ($LASTEXITCODE -ne 0) { throw 'Release preparation failed' }
    for ($repeat = 1; $repeat -le 5; $repeat++) {
        $arms = if ($repeat % 2) { @('off', 'cpu') } else { @('cpu', 'off') }
        foreach ($arm in $arms) {
            Assert-CleanSource
            Assert-NoWpr
            if ((Get-PSDrive -Name C).Free -lt 5GB) { throw 'Insufficient free space for bounded capture; no evidence deleted' }
            $name = "$arm-r$repeat"
            $cell = Join-Path $root $name
            $recording = $false
            $benchExit = $null
            try {
                if ($arm -eq 'cpu') {
                    & $wpr -start CPU.light -filemode *> (Join-Path $root "$name-start.log")
                    if ($LASTEXITCODE -ne 0) { throw 'WPR CPU start failed; no benchmark launched for this cell' }
                    $recording = $true
                }
                & python (Join-Path $PSScriptRoot 'run_b5_v2.py') --output $cell --diagnostic --paths direct --rate 5206274500000 150044089 --cores 1 --groups 1 --streams 32 --depth 1 --payload 1024 --warmup 3 --duration 120 --progress 30 *> (Join-Path $root "$name.log")
                $benchExit = $LASTEXITCODE
            } finally {
                if ($recording) {
                    & $wpr -stop (Join-Path $root "$name.etl") *> (Join-Path $root "$name-stop.log")
                    if ($LASTEXITCODE -ne 0) { throw 'Owned WPR stop failed; retain output and inspect recording state before any later capture' }
                }
            }
            if ($benchExit -ne 0) { throw "Diagnostic cell failed: $name; no replacement" }
            Assert-NoWpr
            if ($arm -eq 'cpu') {
                $header = Join-Path $root "$name-trace-header.txt"
                & $xperf -i (Join-Path $root "$name.etl") -o $header -a tracestats *> (Join-Path $root "$name-trace-check.log")
                if ($LASTEXITCODE -ne 0) { throw "Trace unreadable or lossy: $name; no replacement" }
                & python -m scripts.performance.wpr_trace_quality $header *> (Join-Path $root "$name-trace-quality.log")
                if ($LASTEXITCODE -ne 0) { throw "Trace loss check failed: $name; no replacement" }
            }
            Assert-CleanSource
            Write-Host "$name complete"
        }
    }
} catch {
    $failure = $_.Exception.Message
    @{ classification = 'INVALID_PARTIAL'; error = $failure } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'failure.json') -Encoding utf8
} finally {
    $index = Join-Path $root 'checksums.sha256'
    Get-ChildItem -LiteralPath $root -Recurse -File | Where-Object { $_.FullName -ne $index } | Sort-Object FullName | ForEach-Object {
        $relative = [IO.Path]::GetRelativePath($root, $_.FullName).Replace('\', '/')
        '{0}  {1}' -f (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(), $relative
    } | Set-Content -LiteralPath $index -Encoding ascii
}
if ($failure) { throw "$failure; retained evidence: $root" }
Write-Host "CAPTURE_READY: $root"
