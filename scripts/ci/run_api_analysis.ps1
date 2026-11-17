#Requires -Version 7.0
param(
    [switch]$Live,
    [switch]$SelfTest,
    [ValidateSet('ci', 'overview')][string]$Scope = 'ci',
    [string]$Python = 'python',
    [string]$Model = '',
    [string]$InputRate = '',
    [string]$OutputRate = '',
    [string]$MaxUsd = '',
    [string]$ExpectedPythonSha256 = '',
    [string]$ExpectedClientSha256 = ''
)
$ErrorActionPreference = 'Stop'

function Unprotect-Key([string]$Ciphertext) {
    $secure = ConvertTo-SecureString -String $Ciphertext
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $secure.Dispose()
    }
}

$process = $null
$key = $null
$started = $false
try {
    if (-not $IsWindows) { throw 'Windows required.' }
    if ($SelfTest) {
        if ($Live) { throw 'Self-test cannot be live.' }
        $synthetic = ConvertTo-SecureString 'synthetic-not-a-real-key' -AsPlainText -Force
        try { $cipher = ConvertFrom-SecureString $synthetic }
        finally { $synthetic.Dispose() }
        if ((Unprotect-Key $cipher) -cne 'synthetic-not-a-real-key') { throw 'Roundtrip failed.' }
        Write-Output 'Synthetic DPAPI roundtrip passed; no process or API call.'
        exit 0
    }
    $root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $Python
    $info.WorkingDirectory = $root
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    [void]$info.Environment.Remove('OPENAI_API_KEY')
    foreach ($arg in @('-I', '-B', 'scripts/ci/api_analysis.py', '--scope', $Scope)) {
        $info.ArgumentList.Add($arg)
    }
    if ($Live) {
        if (-not [IO.Path]::IsPathFullyQualified($Python) -or
            $ExpectedPythonSha256 -notmatch '^[0-9a-fA-F]{64}$' -or
            $ExpectedClientSha256 -notmatch '^[0-9a-fA-F]{64}$') {
            throw 'Explicit reviewed interpreter and client identities required.'
        }
        if ((Get-FileHash -LiteralPath $Python -Algorithm SHA256).Hash -ine $ExpectedPythonSha256 -or
            (Get-FileHash -LiteralPath (Join-Path $root 'scripts/ci/api_analysis.py') -Algorithm SHA256).Hash -ine $ExpectedClientSha256) {
            throw 'Reviewed execution identity mismatch.'
        }
        if (-not ($Model -and $InputRate -and $OutputRate -and $MaxUsd)) {
            throw 'Explicit model, rates and budget required.'
        }
        $credential = Join-Path $env:LOCALAPPDATA 'NBSR\credentials\openai-api-key.dpapi'
        $item = Get-Item -LiteralPath $credential
        if ($item.PSIsContainer -or $item.Length -gt 65536) { throw 'Invalid credential file.' }
        $cursor = $item
        while ($null -ne $cursor) {
            if ($cursor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked credential rejected.' }
            $cursor = if ($cursor -is [IO.FileInfo]) { $cursor.Directory } else { $cursor.Parent }
        }
        $key = Unprotect-Key ([IO.File]::ReadAllText($credential))
        if ([string]::IsNullOrWhiteSpace($key)) { throw 'Empty credential.' }
        $info.Environment["OPENAI_API_KEY"] = $key
        $info.Environment['NBSR_ANALYSIS_MODEL'] = $Model
        $info.Environment['NBSR_INPUT_RATE'] = $InputRate
        $info.Environment['NBSR_OUTPUT_RATE'] = $OutputRate
        $info.Environment['NBSR_MAX_USD'] = $MaxUsd
        $info.ArgumentList.Add('--live')
    }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    if (-not $process.Start()) { throw 'Start failed.' }
    $started = $true
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    [void]$info.Environment.Remove('OPENAI_API_KEY')
    $key = $null
    if (-not $process.WaitForExit(90000)) {
        $process.Kill($true)
        if (-not $process.WaitForExit(5000)) { throw 'Cleanup incomplete.' }
        throw 'Timed out; do not retry automatically.'
    }
    # Do not forward arbitrary child diagnostics or tracebacks to a transcript.
    if ($process.ExitCode -ne 0) { throw 'Client failed closed.' }
    Write-Output 'Local analysis completed. Inspect ci-results/api-analysis.json; no automatic changes.'
    exit 0
} catch {
    Write-Output 'Local analysis failed closed. No automatic retry. Check configuration locally.'
    exit 1
} finally {
    $key = $null
    if ($null -ne $info) { [void]$info.Environment.Remove('OPENAI_API_KEY') }
    if ($null -ne $process) {
        try {
            if ($started -and -not $process.HasExited) {
                $process.Kill($true)
                if (-not $process.WaitForExit(5000)) { throw 'Cleanup incomplete.' }
            }
        } catch {
            Write-Output 'Owned-process cleanup incomplete; do not retry or reuse credential until resolved.'
            exit 2
        } finally { $process.Dispose() }
    }
}
