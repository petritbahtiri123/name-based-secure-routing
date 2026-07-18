Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
python (Join-Path $PSScriptRoot "bootstrap.py")
if ($LASTEXITCODE -ne 0) { throw "Key bootstrap failed" }
