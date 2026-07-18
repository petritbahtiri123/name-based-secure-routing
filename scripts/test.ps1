Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
  python -m pytest -q
  if (Get-Command opa -ErrorAction SilentlyContinue) { opa test policy -v }
  if (Get-Command docker -ErrorAction SilentlyContinue) { docker compose config --quiet }
} finally { Pop-Location }
