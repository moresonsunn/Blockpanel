<#!
.SYNOPSIS
  Manual multi-arch publish of Lynx images to Docker Hub (PowerShell version).
.DESCRIPTION
  Builds and pushes both runtime and controller images for linux/amd64 and linux/arm64.
  Tags applied: latest, <Version>, <short_sha>, <date_tag>.

.PARAMETER Version
  Optional version / tag (e.g. v0.1.1). If omitted, falls back to current commit short SHA.
.PARAMETER Namespace
  Optional Docker Hub namespace override. If omitted: $env:DOCKERHUB_NAMESPACE -> $env:DOCKERHUB_USERNAME -> 'moresonsun'.

.REQUIREMENTS
  - Docker Desktop with buildx (default on recent versions)
  - Environment variables:
      DOCKERHUB_USERNAME
      DOCKERHUB_TOKEN (Docker Hub access token)
  - git in PATH

.EXAMPLE
  $env:DOCKERHUB_USERNAME="moresonsun"
  $env:DOCKERHUB_TOKEN="<token>"
  ./scripts/manual-publish-dockerhub.ps1 -Version v0.1.1

.EXAMPLE
  # Use commit short SHA as version tag automatically
  ./scripts/manual-publish-dockerhub.ps1
!#>
[CmdletBinding()]
param(
  [string]$Version,
  [string]$Namespace
)

$ErrorActionPreference = 'Stop'

function Write-Step($m) { Write-Host "[STEP] $m" -ForegroundColor Cyan }
function Write-Info($m) { Write-Host "[INFO] $m" -ForegroundColor Gray }
function Write-Warn($m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "[ERROR] $m" -ForegroundColor Red; exit 1 }

if (-not $env:DOCKERHUB_USERNAME -or -not $env:DOCKERHUB_TOKEN) {
  Fail "DOCKERHUB_USERNAME / DOCKERHUB_TOKEN must be set."
}

if (-not $Namespace -or $Namespace -eq '') {
  if ($env:DOCKERHUB_NAMESPACE) { $Namespace = $env:DOCKERHUB_NAMESPACE }
  elseif ($env:DOCKERHUB_USERNAME) { $Namespace = $env:DOCKERHUB_USERNAME }
  else { $Namespace = 'moresonsun' }
}

# Resolve git meta
$shortSha = (git rev-parse --short HEAD).Trim()
$fullSha  = (git rev-parse HEAD).Trim()
$dateTag  = (Get-Date -Format 'yyyyMMdd')
if (-not $Version -or $Version -eq '') { $Version = $shortSha; Write-Warn "No -Version provided; using commit short SHA '$Version'" }
$appVersion = $Version

$unifiedRepo = "$Namespace/lynx"

Write-Step "Docker Hub login ($($env:DOCKERHUB_USERNAME))"
$env:DOCKERHUB_TOKEN | docker login -u $env:DOCKERHUB_USERNAME --password-stdin | Out-Null

# Ensure buildx builder exists
$builderName = 'lynx-publisher'
$existing = docker buildx ls | Select-String $builderName -ErrorAction SilentlyContinue
if (-not $existing) {
  Write-Step "Creating buildx builder '$builderName'"
  docker buildx create --name $builderName --use | Out-Null
} else {
  Write-Info "Using existing builder '$builderName'"
  docker buildx use $builderName | Out-Null
}

docker buildx inspect --bootstrap | Out-Null

Write-Info "Version tag: $Version | short: $shortSha | date: $dateTag | namespace: $Namespace"

# Runtime build
Write-Step "Building & pushing unified image"
$unifiedArgs = @(
  'buildx','build',
  '--platform','linux/amd64,linux/arm64',
  '-f','docker/controller-unified.Dockerfile',
  '-t',"${unifiedRepo}:latest",
  '-t',"${unifiedRepo}:${Version}",
  '-t',"${unifiedRepo}:${shortSha}",
  '-t',"${unifiedRepo}:${dateTag}",
  '--build-arg',"APP_VERSION=$appVersion",
  '--build-arg',"GIT_COMMIT=$fullSha",
  '--push','.'
)
& docker @unifiedArgs

Write-Step "Inspect (optional)"
Write-Host "  docker buildx imagetools inspect ${unifiedRepo}:${Version}" -ForegroundColor DarkGray

Write-Host "Publish complete." -ForegroundColor Green
