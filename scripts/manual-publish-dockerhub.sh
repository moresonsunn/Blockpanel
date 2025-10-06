#!/usr/bin/env bash
set -euo pipefail
# Manual multi-arch publisher for BlockPanel images when CI has not yet pushed them.
# Requirements: docker buildx with a builder supporting linux/amd64,linux/arm64 and DOCKERHUB_USERNAME/DOCKERHUB_TOKEN exported.
# Usage:
#   export DOCKERHUB_USERNAME=...; export DOCKERHUB_TOKEN=...
#   ./scripts/manual-publish-dockerhub.sh v0.1.1
#   (or omit version to default to latest commit short SHA)

VERSION_TAG="${1:-}"
DOCKER_NS="${DOCKERHUB_NAMESPACE:-${DOCKERHUB_USERNAME:-moresonsun}}"
CONTROLLER_REPO="${DOCKER_NS}/blockypanel"
RUNTIME_REPO="${DOCKER_NS}/blockypanel-runtime"

if [[ -z "${DOCKERHUB_USERNAME:-}" || -z "${DOCKERHUB_TOKEN:-}" ]]; then
  echo "Docker Hub credentials missing (DOCKERHUB_USERNAME / DOCKERHUB_TOKEN)" >&2
  exit 1
fi

echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USERNAME" --password-stdin

if ! docker buildx ls | grep -q blockpanel-publisher; then
  docker buildx create --name blockpanel-publisher --use
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

echo "Building runtime -> ${RUNTIME_REPO}:{latest,$VERSION_TAG,$SHORT_SHA,$DATE_TAG}";
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -f docker/runtime.Dockerfile \
  -t ${RUNTIME_REPO}:latest \
  -t ${RUNTIME_REPO}:${VERSION_TAG} \
  -t ${RUNTIME_REPO}:${SHORT_SHA} \
  -t ${RUNTIME_REPO}:${DATE_TAG} \
  --build-arg APP_VERSION=${APP_VERSION} \
  --build-arg GIT_COMMIT=$(git rev-parse HEAD) \
  --push .

# Build & push controller

echo "Building controller -> ${CONTROLLER_REPO}:{latest,$VERSION_TAG,$SHORT_SHA,$DATE_TAG}";
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -f docker/controller.Dockerfile \
  -t ${CONTROLLER_REPO}:latest \
  -t ${CONTROLLER_REPO}:${VERSION_TAG} \
  -t ${CONTROLLER_REPO}:${SHORT_SHA} \
  -t ${CONTROLLER_REPO}:${DATE_TAG} \
  --build-arg APP_VERSION=${APP_VERSION} \
  --build-arg GIT_COMMIT=$(git rev-parse HEAD) \
  --push .

echo "Publish complete. Inspect manifests with:"
echo "  docker buildx imagetools inspect ${CONTROLLER_REPO}:${VERSION_TAG}"