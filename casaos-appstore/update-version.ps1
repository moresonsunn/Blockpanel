param(
  [Parameter(Mandatory=$true)][string]$Version
)
$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) '..')
$mainApp = Join-Path $repoRoot 'casaos-appstore/Apps/lynx/app.json'
(Get-Content $mainApp -Raw) -replace 'v\d+\.\d+\.\d+', $Version | Set-Content $mainApp -NoNewline
# Update full app manifest
$content = Get-Content $mainApp -Raw | ConvertFrom-Json
$content.version = $Version
$content.container_list[0].envs | Where-Object { $_.name -eq 'APP_VERSION' } | ForEach-Object { $_.value = $Version }
$content.container_list[0].image = "moresonsun/lynx:$Version"
$content | ConvertTo-Json -Depth 8 | Set-Content $mainApp -NoNewline

Write-Host "Updated CasaOS app manifests to $Version" -ForegroundColor Green
