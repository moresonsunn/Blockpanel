<#!
.SYNOPSIS
  Quick multi-arch build & push for the unified BlockPanel image.
.DESCRIPTION
  Builds docker/controller-unified.Dockerfile for linux/amd64 + linux/arm64 and pushes
  tags (latest + provided tag + short sha + date) to Docker Hub.

  Environment variables used:
    DOCKERHUB_USERNAME  (required unless -Namespace provided AND you are already logged in)
    DOCKERHUB_TOKEN     (optional if you are already logged in)
    DOCKERHUB_NAMESPACE (optional override for repo namespace)

.PARAMETER Tag
  Version-style tag (e.g. v0.1.0). If omitted uses current commit short SHA.
.PARAMETER Namespace
  Docker Hub namespace override. Falls back to DOCKERHUB_NAMESPACE, then DOCKERHUB_USERNAME, then 'moresonsun'.

.EXAMPLE
  ./scripts/quick-push-unified.ps1 -Tag v0.1.0

.EXAMPLE
  $env:DOCKERHUB_USERNAME='moresonsun'; $env:DOCKERHUB_TOKEN='***'; ./scripts/quick-push-unified.ps1
!#>
[CmdletBinding()] param(
  [string]$Tag,
  [string]$Namespace
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Step($m){ Write-Host "[STEP] $m" -ForegroundColor Cyan }
function Info($m){ Write-Host "[INFO] $m" -ForegroundColor Gray }
function Warn($m){ Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Fail($m){ Write-Host "[ERROR] $m" -ForegroundColor Red; exit 1 }

# Resolve namespace
if (-not $Namespace -or $Namespace -eq '') {
  if ($env:DOCKERHUB_NAMESPACE) { $Namespace = $env:DOCKERHUB_NAMESPACE }
  elseif ($env:DOCKERHUB_USERNAME) { $Namespace = $env:DOCKERHUB_USERNAME }
  else { $Namespace = 'moresonsun' }
}

# Gather git meta
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail 'git not found in PATH' }
$shortSha = (git rev-parse --short HEAD).Trim()
$fullSha  = (git rev-parse HEAD).Trim()
$dateTag  = (Get-Date -Format 'yyyyMMdd')
if (-not $Tag -or $Tag -eq '') { $Tag = $shortSha; Warn "No -Tag provided; using commit short SHA '$Tag'" }

$repo = "$Namespace/blockpanel-unified"
Info "Repository: $repo | Tag: $Tag | Short: $shortSha | Date: $dateTag"

# Login if token provided (skip if already logged in)
try {
  $loggedIn = docker info 2>$null | Select-String -Pattern 'Username:' -ErrorAction SilentlyContinue
} catch { $loggedIn = $null }
if (-not $loggedIn -or $loggedIn -eq '') {
  if ($env:DOCKERHUB_USERNAME -and $env:DOCKERHUB_TOKEN) {
    Step "Docker login ($($env:DOCKERHUB_USERNAME))"
    $env:DOCKERHUB_TOKEN | docker login -u $env:DOCKERHUB_USERNAME --password-stdin | Out-Null
  } else {
    Warn 'No DOCKERHUB_USERNAME / DOCKERHUB_TOKEN provided and not logged in; attempting interactive login.'
    docker login | Out-Null
  }
}

Step 'Ensure buildx builder'
$builderName = 'bp-unified-builder'
$existing = docker buildx ls | Select-String $builderName -ErrorAction SilentlyContinue
if (-not $existing) {
  docker buildx create --name $builderName --use | Out-Null
} else {
  docker buildx use $builderName | Out-Null
}
docker buildx inspect --bootstrap | Out-Null

Step 'Build & push multi-arch image'
$buildArgs = @(
  'buildx','build',
  '--platform','linux/amd64,linux/arm64',
  '-f','docker/controller-unified.Dockerfile',
  '-t',"${repo}:latest",
  '-t',"${repo}:$Tag",
  '-t',"${repo}:$shortSha",
  '-t',"${repo}:$dateTag",
  '--build-arg',"APP_VERSION=$Tag",
  '--build-arg',"GIT_COMMIT=$fullSha",
  '--push','.'
)
& docker @buildArgs
if ($LASTEXITCODE -ne 0) { Fail "Buildx build failed (exit code $LASTEXITCODE). Not pushing tags." }

Step 'Inspect primary tag'
docker buildx imagetools inspect ${repo}:$Tag | Select-String -Pattern 'Digest:' -Context 0,0 2>$null
if ($LASTEXITCODE -ne 0) { Write-Warn "Unable to inspect image digest for ${repo}:$Tag (may not have pushed)." }

Write-Host "\nSUCCESS: Pushed $repo (tags: latest,$Tag,$shortSha,$dateTag)" -ForegroundColor Green
