Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
  & (Join-Path $PSScriptRoot "bootstrap.ps1")
  $env:NBSR_TICKET_TTL_SECONDS = "2"
  docker compose up -d --build
  python (Join-Path $PSScriptRoot "demo.py")
  if ($LASTEXITCODE -ne 0) { throw "One or more mandatory scenarios failed" }
} finally { Pop-Location }
