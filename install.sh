#!/usr/bin/env bash
set -euo pipefail

# BlockPanel quick installer (Linux/macOS) - pulls a specified or latest version and launches via docker compose.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/moresonsunn/minecraft-server/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/moresonsunn/minecraft-server/main/install.sh | bash -s -- -v v0.1.1
# Options:
#   -v|--version <tag>   Use a specific released tag (defaults to latest)
#   -d|--dir <path>      Target directory (default: ./blockpanel)
#   --no-start           Download assets but do not run docker compose up
#   --edge               Use :latest images instead of a tagged release
#   --dry-run            Show actions only
#   --skip-chown         Skip ownership adjustment on data dir

VERSION=""
TARGET_DIR="blockpanel"
NO_START="false"
EDGE="false"
DRY="false"
SKIP_CHOWN="false"
GITHUB_REPO="moresonsunn/minecraft-server"
RAW_BASE="https://raw.githubusercontent.com/${GITHUB_REPO}"
BRANCH="main"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -v|--version) VERSION="$2"; shift 2;;
    -d|--dir) TARGET_DIR="$2"; shift 2;;
    --no-start) NO_START="true"; shift;;
    --edge) EDGE="true"; shift;;
    --dry-run) DRY="true"; shift;;
    --skip-chown) SKIP_CHOWN="true"; shift;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# //'; exit 0;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

run() { echo "+ $*"; [[ "$DRY" == "true" ]] || eval "$*"; }

if [[ -z "$VERSION" && "$EDGE" != "true" ]]; then
  echo "Resolving latest release tag from GitHub..."
  VERSION=$(curl -fsSL https://api.github.com/repos/${GITHUB_REPO}/releases/latest | grep '"tag_name"' | head -1 | cut -d '"' -f4 || true)
  if [[ -z "$VERSION" ]]; then
    echo "Could not determine latest release (falling back to edge).";
    EDGE="true"
  fi
fi

if [[ "$EDGE" == "true" ]]; then
  echo "Using edge (latest) images instead of tagged release."
fi

echo "Target directory: $TARGET_DIR"
run mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

# Fetch docker-compose.yml template
COMPOSE_URL="${RAW_BASE}/${BRANCH}/docker-compose.yml"
run curl -fsSL "$COMPOSE_URL" -o docker-compose.yml

if [[ "$EDGE" == "false" && -n "$VERSION" ]]; then
  echo "Pinning images to $VERSION"
  # Replace :latest with :$VERSION for controller and runtime images
  run sed -i.bak "s#moresonsun/blockpanel:latest#moresonsun/blockpanel:${VERSION}#" docker-compose.yml
  run sed -i.bak "s#moresonsun/blockpanel-runtime:latest#moresonsun/blockpanel-runtime:${VERSION}#" docker-compose.yml
  # Replace APP_VERSION env if present
  run sed -i.bak "s#APP_VERSION=v[^\n]*#APP_VERSION=${VERSION}#" docker-compose.yml || true
fi

# Data directory ownership (Linux)
if [[ "$SKIP_CHOWN" != "true" && "$DRY" != "true" && -d mc_servers_data ]]; then
  if command -v id >/dev/null 2>&1; then
    sudo chown -R $(id -u):$(id -g) mc_servers_data || true
  fi
fi

if [[ "$NO_START" == "true" ]]; then
  echo "Download complete. Skipping start due to --no-start."
  exit 0
fi

# Launch
if [[ "$DRY" == "true" ]]; then
  echo "(dry-run) Would run: docker compose pull && docker compose up -d"
  exit 0
fi

run docker compose pull
run docker compose up -d

echo "\nBlockPanel is starting. Access it at: http://localhost:8000"
[[ "$EDGE" == "true" ]] && echo "(Edge build: using :latest images)" || echo "(Pinned release: ${VERSION})"
