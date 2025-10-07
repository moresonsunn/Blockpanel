param(
  [Parameter(Mandatory=$true)][string]$Version
)
$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) '..')
$mainApp = Join-Path $repoRoot 'casaos-appstore/Apps/blockpanel/app.json'
(Get-Content $mainApp -Raw) -replace 'v\d+\.\d+\.\d+', $Version | Set-Content $mainApp -NoNewline
# Update full app manifest
$content = Get-Content $mainApp -Raw | ConvertFrom-Json
$content.version = $Version
$content.container_list[0].envs | Where-Object { $_.name -eq 'APP_VERSION' } | ForEach-Object { $_.value = $Version }
$content.container_list[0].image = "moresonsun/blockypanel:$Version"
$content.container_list[2].image = "moresonsun/blockypanel-runtime:$Version"
$content | ConvertTo-Json -Depth 8 | Set-Content $mainApp -NoNewline

# Update unified manifest (keeps :latest by default unless versioned release desired)
$unifiedApp = Join-Path $repoRoot 'casaos-appstore/Apps/blockpanel-unified/app.json'
if (Test-Path $unifiedApp) {
  $ucontent = Get-Content $unifiedApp -Raw | ConvertFrom-Json
  $ucontent.version = $Version
  # Optionally pin image tag to version for deterministic installs
  $ucontent.container_list[0].image = "moresonsun/blockpanel-unified:$Version"
  ($ucontent.container_list[0].envs | Where-Object { $_.name -eq 'APP_VERSION' }).value = $Version
  $ucontent | ConvertTo-Json -Depth 8 | Set-Content $unifiedApp -NoNewline
}

Write-Host "Updated CasaOS app manifests to $Version" -ForegroundColor Green
