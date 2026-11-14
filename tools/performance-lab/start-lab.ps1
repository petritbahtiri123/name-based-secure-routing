$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
try {
    $health = Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/health' -TimeoutSec 2
} catch { $health = $null }
if ($null -ne $health) {
    if ($health.mode -notin @('offline-evidence','passive-inbox')) { throw 'Port 8765 belongs to another service.' }
    Write-Host 'NBSR Performance Lab is already running: http://127.0.0.1:8765'
    exit 0
}
$env:NBSR_LAB_INBOX = Join-Path $PSScriptRoot 'inbox'
$pythonPath = (Get-Command python.exe).Source
$process = Start-Process -FilePath $pythonPath -ArgumentList '-m','uvicorn','lab.app:create_app','--factory','--host','127.0.0.1','--port','8765' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'server.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'server.stderr.log') -PassThru
Write-Host "Starting NBSR Performance Lab (PID $($process.Id)): http://127.0.0.1:8765"
