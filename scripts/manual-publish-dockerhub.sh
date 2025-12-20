#!/usr/bin/env bash
set -euo pipefail
# Manual multi-arch publisher for Lynx images when CI has not yet pushed them.
# Requirements: docker buildx with a builder supporting linux/amd64,linux/arm64 and DOCKERHUB_USERNAME/DOCKERHUB_TOKEN exported.
# Usage:
#   export DOCKERHUB_USERNAME=...; export DOCKERHUB_TOKEN=...
#   ./scripts/manual-publish-dockerhub.sh v0.1.1
#   (or omit version to default to latest commit short SHA)

VERSION_TAG="${1:-}"
DOCKER_NS="${DOCKERHUB_NAMESPACE:-${DOCKERHUB_USERNAME:-moresonsun}}"
UNIFIED_REPO="${DOCKER_NS}/lynx"

if [[ -z "${DOCKERHUB_USERNAME:-}" || -z "${DOCKERHUB_TOKEN:-}" ]]; then
  echo "Docker Hub credentials missing (DOCKERHUB_USERNAME / DOCKERHUB_TOKEN)" >&2
  exit 1
fi

echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USERNAME" --password-stdin

if ! docker buildx ls | grep -q lynx-publisher; then
  docker buildx create --name lynx-publisher --use
fi

docker buildx inspect --bootstrap >/dev/null

SHORT_SHA=$(git rev-parse --short HEAD)
DATE_TAG=$(date -u +%Y%m%d)
if [[ -z "$VERSION_TAG" ]]; then
  VERSION_TAG="${SHORT_SHA}"
  echo "No version provided; using commit short SHA ${VERSION_TAG}"
fi

APP_VERSION="$VERSION_TAG"

# Build & push runtime

echo "Building unified -> ${UNIFIED_REPO}:{latest,$VERSION_TAG,$SHORT_SHA,$DATE_TAG}";
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -f docker/controller-unified.Dockerfile \
  -t ${UNIFIED_REPO}:latest \
  -t ${UNIFIED_REPO}:${VERSION_TAG} \
  -t ${UNIFIED_REPO}:${SHORT_SHA} \
  -t ${UNIFIED_REPO}:${DATE_TAG} \
  --build-arg APP_VERSION=${APP_VERSION} \
  --build-arg GIT_COMMIT=$(git rev-parse HEAD) \
  --push .

echo "Publish complete. Inspect manifests with:"
echo "  docker buildx imagetools inspect ${UNIFIED_REPO}:${VERSION_TAG}"