Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

[switch]$NoPause = $false
[switch]$Rehearsal = $false
foreach ($Argument in $args) {
  switch ($Argument) {
    "-NoPause" { $NoPause = $true }
    "-Rehearsal" { $Rehearsal = $true }
    default { throw "Unknown option: $Argument" }
  }
}

$Root = Split-Path -Parent $PSScriptRoot
$RequiredServices = @("control-plane", "opa", "gateway", "ticket-verifier", "payments-service")
$ScenarioNames = @(
  "Authorized request",
  "Unauthorized identity",
  "Unknown service",
  "Missing ticket",
  "Tampered ticket",
  "Method/path escalation",
  "Direct backend access",
  "Expired ticket"
)

function Invoke-VideoPause {
  if ($NoPause) { return }
  Start-Sleep -Seconds $(if ($Rehearsal) { 2 } else { 1 })
}

function Assert-Command {
  param([string]$Name)
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Required command '$Name' was not found."
  }
}

Push-Location $Root
try {
  Assert-Command "docker"
  docker compose version *> $null
  if ($LASTEXITCODE -ne 0) { throw "Docker Compose is unavailable." }
  docker info *> $null
  if ($LASTEXITCODE -ne 0) { throw "Docker Desktop is not running." }

  & (Join-Path $PSScriptRoot "bootstrap.ps1")
  $env:NBSR_TICKET_TTL_SECONDS = "2"
  docker compose up -d --no-build --wait --wait-timeout 120
  if ($LASTEXITCODE -ne 0) { throw "Could not prepare the Compose stack for the short-lived ticket demonstration." }

  $Services = @(docker compose ps --format json | ConvertFrom-Json)
  foreach ($Required in $RequiredServices) {
    $Service = $Services | Where-Object { $_.Service -eq $Required }
    if (-not $Service) { throw "Required Compose service '$Required' does not exist." }
    if ($Service.State -ne "running") { throw "Required service '$Required' is not running." }
    if ($Service.Health -and $Service.Health -ne "healthy") {
      throw "Required service '$Required' is not healthy: $($Service.Health)."
    }
  }

  if (-not $NoPause) { Clear-Host }
  Write-Host "NAME-BASED SECURE ROUTING — LIVE VALIDATED DEMO" -ForegroundColor Cyan
  Write-Host "Real Docker Compose services. No mocked results." -ForegroundColor DarkGray
  Write-Host ""
  Write-Host "Preflight: 5/5 required services running and ready." -ForegroundColor Green
  Invoke-VideoPause

  $DemoOutput = @(& python (Join-Path $PSScriptRoot "demo.py") 2>&1)
  $DemoExit = $LASTEXITCODE
  $Rows = @()
  foreach ($Line in $DemoOutput) {
    if ($Line -match "^(?<Name>Authorized request|Unauthorized identity|Unknown service|Missing ticket|Tampered ticket|Method/path escalation|Direct backend access|Expired ticket)\s+(?<Expected>ALLOW|DENY)\s+(?<Actual>ALLOW|DENY)\s+(?<Result>PASS|FAIL)$") {
      $Rows += [pscustomobject]@{
        Name = $Matches.Name
        Expected = $Matches.Expected
        Actual = $Matches.Actual
        Result = $Matches.Result
      }
    }
  }
  if ($Rows.Count -ne 8) {
    $DemoOutput | ForEach-Object { Write-Host $_ }
    throw "Expected eight scenario results but parsed $($Rows.Count)."
  }

  for ($Index = 0; $Index -lt $Rows.Count; $Index++) {
    $Row = $Rows[$Index]
    Write-Host ""
    Write-Host "[$($Index + 1)/8] $($Row.Name)" -ForegroundColor Cyan
    Write-Host "Expected: $($Row.Expected)"
    Write-Host "Actual:   $($Row.Actual)"
    Write-Host "Result:   $($Row.Result)" -ForegroundColor $(if ($Row.Result -eq "PASS") { "Green" } else { "Red" })
    Invoke-VideoPause
  }

  Write-Host ""
  Write-Host "FINAL SUMMARY" -ForegroundColor Cyan
  $DemoOutput | Select-Object -Last 9 | ForEach-Object { Write-Host $_ }
  if ($DemoExit -ne 0 -or ($Rows | Where-Object Result -ne "PASS")) {
    throw "One or more mandatory scenarios failed."
  }
} finally {
  Pop-Location
}
