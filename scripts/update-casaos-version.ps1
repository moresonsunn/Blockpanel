<#!
.SYNOPSIS
  Update CasaOS distribution manifests (app.json, apps.json) from templates with a new version.
.DESCRIPTION
  Replaces __VERSION__ placeholders in template files and writes concrete JSON files.
.PARAMETER Version
  Version string (e.g. v0.1.1). Required.
.EXAMPLE
  ./scripts/update-casaos-version.ps1 -Version v0.1.1
!#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$Version
)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $root '..')
$casaDir = Join-Path $repoRoot 'distributions/casaos'

$appTemplate  = Join-Path $casaDir 'app.template.json'
$appsTemplate = Join-Path $casaDir 'apps.template.json'
$appOut       = Join-Path $casaDir 'app.json'
$appsOut      = Join-Path $casaDir 'apps.json'

if (-not (Test-Path $appTemplate) -or -not (Test-Path $appsTemplate)) {
  Write-Error "Template files not found."
  exit 1
}

(Get-Content $appTemplate -Raw)  -replace '__VERSION__', $Version | Set-Content $appOut -NoNewline
(Get-Content $appsTemplate -Raw) -replace '__VERSION__', $Version | Set-Content $appsOut -NoNewline

Write-Host "Updated CasaOS manifests to version $Version" -ForegroundColor Green
Write-Host "Generated: $appOut" -ForegroundColor Cyan
Write-Host "Generated: $appsOut" -ForegroundColor Cyan
