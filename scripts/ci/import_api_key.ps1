#Requires -Version 7.0
# Explicit owner-approved one-time import. Never emits credential material.
param([switch]$FromClipboard)
$ErrorActionPreference = 'Stop'
$plain = $null
$secure = $null
$clipboardAcquired = $false
try {
    if (-not $IsWindows -or -not $FromClipboard) { throw 'Explicit Windows clipboard import required.' }
    $directory = Join-Path $env:LOCALAPPDATA 'NBSR\credentials'
    $destination = Join-Path $directory 'openai-api-key.dpapi'
    if (Test-Path -LiteralPath $destination) { throw 'Existing credential must not be overwritten.' }
    $cursor = Get-Item -LiteralPath $env:LOCALAPPDATA
    while ($null -ne $cursor) {
        if ($cursor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked root rejected.' }
        $cursor = $cursor.Parent
    }
    foreach ($path in @((Join-Path $env:LOCALAPPDATA 'NBSR'), $directory)) {
        if (Test-Path -LiteralPath $path) {
            $entry = Get-Item -LiteralPath $path
            if (-not $entry.PSIsContainer -or ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw 'Unsafe credential directory.'
            }
        } else { [void][IO.Directory]::CreateDirectory($path) }
    }
    $plain = Get-Clipboard -Raw
    $clipboardAcquired = $true
    if ($plain -cnotmatch '^sk-[A-Za-z0-9_-]{20,500}$') { throw 'Clipboard is not a supported API key.' }
    $secure = ConvertTo-SecureString $plain -AsPlainText -Force
    $cipher = ConvertFrom-SecureString $secure
    $bytes = [Text.Encoding]::UTF8.GetBytes($cipher)
    $stream = [IO.File]::Open($destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) }
    finally { $stream.Dispose() }
    Write-Output 'NBSR credential encrypted for the current Windows user. No API request made.'
    exit 0
} catch {
    Write-Output 'Credential import failed closed. No key printed or API request made.'
    exit 1
} finally {
    if ($clipboardAcquired) { Set-Clipboard -Value '' }
    if ($null -ne $secure) { $secure.Dispose() }
    $plain = $null
}
