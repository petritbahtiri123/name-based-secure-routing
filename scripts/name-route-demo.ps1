Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
  python (Join-Path $Root "services/name-relay/app.py") demo
  if ($LASTEXITCODE -ne 0) { throw "Name-route demo failed" }
} finally { Pop-Location }
