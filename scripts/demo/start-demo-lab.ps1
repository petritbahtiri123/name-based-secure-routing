[CmdletBinding()]
param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$arguments = @((Join-Path $root 'tools/demo-lab/demo.py'), 'serve')
if ($NoBrowser) { $arguments += '--no-browser' }
& python @arguments
exit $LASTEXITCODE
