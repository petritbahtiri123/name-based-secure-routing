[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Ref
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

python (Join-Path $PSScriptRoot "package_release.py") --repo-root $Root $Ref
if ($LASTEXITCODE -ne 0) {
    throw "NBSR release packaging failed."
}
