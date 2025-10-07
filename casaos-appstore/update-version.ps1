param(
  [Parameter(Mandatory=$true)][string]$Version
)
$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) '..')
$appFile = Join-Path $repoRoot 'casaos-appstore/Apps/blockpanel/app.json'
(Get-Content $appFile -Raw) -replace 'v\d+\.\d+\.\d+', $Version | Set-Content $appFile -NoNewline
# Also update version field (explicit property) if present
$content = Get-Content $appFile -Raw | ConvertFrom-Json
$content.version = $Version
$content.container_list[0].envs | Where-Object { $_.name -eq 'APP_VERSION' } | ForEach-Object { $_.value = $Version }
$content.container_list[0].image = "moresonsun/blockypanel:$Version"
$content.container_list[2].image = "moresonsun/blockypanel-runtime:$Version"
$content | ConvertTo-Json -Depth 8 | Set-Content $appFile -NoNewline
Write-Host "Updated CasaOS app store BlockPanel to $Version" -ForegroundColor Green
