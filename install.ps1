<#!
.SYNOPSIS
  BlockPanel quick installer for Windows PowerShell.
  Example (PowerShell 5+):
    irm https://raw.githubusercontent.com/moresonsunn/minecraft-server/main/install.ps1 | iex
    irm https://raw.githubusercontent.com/moresonsunn/minecraft-server/main/install.ps1 | iex -v v0.1.1
.PARAMETER Version
  Optional tag (e.g. v0.1.1). If omitted uses latest GitHub release; fallback to :latest edge.
.PARAMETER Path
  Target directory (default ./blockpanel)
.PARAMETER Edge
  Use :latest images ignoring releases.
.PARAMETER NoStart
  Download compose file but do not start containers.
.PARAMETER DryRun
  Show actions only.
!#>
[CmdletBinding()]
param(
  [string]$Version,
  [string]$Path = "blockpanel",
  [switch]$Edge,
  [switch]$NoStart,
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$repo = 'moresonsunn/minecraft-server'
$branch = 'main'
$rawBase = "https://raw.githubusercontent.com/$repo/$branch"

function Invoke-Step($msg, [scriptblock]$action) {
  Write-Host "+ $msg" -ForegroundColor Cyan
  if (-not $DryRun) { & $action }
}

if (-not $Version -and -not $Edge) {
  try {
    Write-Host 'Resolving latest GitHub release tag...' -ForegroundColor Yellow
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases/latest" -UseBasicParsing
    $Version = $rel.tag_name
  } catch { Write-Warning 'Failed to fetch latest release; using edge (:latest).'; $Edge = $true }
}

if ($Edge) { Write-Host 'Using edge (latest) images.' -ForegroundColor Yellow }

Invoke-Step "Create target dir $Path" { New-Item -ItemType Directory -Path $Path -Force | Out-Null }
Set-Location $Path

$composeUrl = "$rawBase/docker-compose.yml"
Invoke-Step 'Download docker-compose.yml' { Invoke-WebRequest -Uri $composeUrl -OutFile 'docker-compose.yml' }

if (-not $Edge -and $Version) {
  Write-Host "Pinning images to $Version" -ForegroundColor Green
  Invoke-Step 'Replace controller image tag' {
    (Get-Content docker-compose.yml) -replace 'moresonsun/blockpanel:latest', "moresonsun/blockpanel:$Version" | Set-Content docker-compose.yml
  }
  Invoke-Step 'Replace runtime image tag' {
    (Get-Content docker-compose.yml) -replace 'moresonsun/blockpanel-runtime:latest', "moresonsun/blockpanel-runtime:$Version" | Set-Content docker-compose.yml
  }
  Invoke-Step 'Replace APP_VERSION env' {
    (Get-Content docker-compose.yml) -replace 'APP_VERSION=v[0-9A-Za-z\.\-]+', "APP_VERSION=$Version" | Set-Content docker-compose.yml
  }
}

if ($NoStart) { Write-Host 'Download complete (no start).'; exit 0 }
if ($DryRun) { Write-Host '(dry-run) Would run docker compose pull + up'; exit 0 }

Invoke-Step 'docker compose pull' { docker compose pull }
Invoke-Step 'docker compose up -d' { docker compose up -d }

Write-Host "BlockPanel is starting at http://localhost:8000" -ForegroundColor Green
if ($Edge) { Write-Host '(Edge build using :latest images)' } else { Write-Host "(Pinned release: $Version)" }