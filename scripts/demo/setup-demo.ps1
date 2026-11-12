[CmdletBinding()]
param([ValidateSet('check','prepare','build')][string]$Action='check', [switch]$AllowDownloads)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$arguments = @((Join-Path $root 'tools/demo-lab/demo.py'), $Action)
if ($AllowDownloads) {
    if ($Action -ne 'prepare') { throw '-AllowDownloads requires -Action prepare' }
    $arguments += '--allow-downloads'
}
& python @arguments
exit $LASTEXITCODE
