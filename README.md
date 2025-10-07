# BlockPanel (Minecraft Server Manager)

![GitLab CI](https://gitlab.com/kyzen4/blockpanel/badges/main/pipeline.svg)
![GitHub CI](https://github.com/blockypanel/Blockpanel/actions/workflows/ci.yml/badge.svg)
![Docker Pulls](https://img.shields.io/docker/pulls/moresonsun/blockypanel)
![Architecture](https://img.shields.io/badge/arch-amd64%20%7C%20arm64-blue)

BlockPanel is a modern web-based controller to create, manage, monitor, and automate multiple Minecraft servers using Docker containers. Inspired by Crafty but focused on:
- Fast, preload-first UI (React + Tailwind)
- Multi-provider support (Vanilla, Paper, Purpur, Fabric, Forge, NeoForge)
- Declarative server creation with loader + installer resolution
- Efficient file operations (streaming uploads, zip/unzip, optimistic UI, ETag cache busting)
- Colored live console with reset-on-power events
- Role & permission management (users, roles, audit logs)
- REST API + future extensibility

Single unified Docker image (multi-arch: linux/amd64 + linux/arm64) is published (default namespace: `moresonsun`):
- Unified (controller + UI + embedded multi-Java runtime): `moresonsun/blockpanel-unified:latest`

Brand / Org Override: If/when a dedicated Docker Hub org `blockypanel` is created, set `DOCKERHUB_NAMESPACE=blockypanel` (or explicitly set `DOCKERHUB_REPO` / `DOCKERHUB_RUNTIME_REPO`) in CI to publish under that namespace without code changes.

GitLab Container Registry (when pipeline runs with `GITLAB_PUSH=true`):
- Controller: `registry.gitlab.com/kyzen4/blockpanel/blockpanel:latest`
- Runtime: `registry.gitlab.com/kyzen4/blockpanel/blockpanel-runtime:latest`

Release tags (when pushing annotated git tags like `v0.1.0`) will also publish versioned images once available.

## Core Features
- Create / start / stop / restart / kill servers
- Multi server types & dynamic version/loader fetching
- Port suggestion & validation endpoints
- Live resource stats & player info (aggregated polling)
- Backup create/restore (zip snapshot)
- File manager: upload (files/folders), download, zip/unzip, rename, delete
- Automatic server-icon detection & normalization
- ANSI-colored console output with reset between power cycles
- User authentication, roles, permissions, audit logging
- Monitoring endpoints (system health, dashboard data, alerts)
<!-- AI error fixer removed during cleanup -->

## Tech Stack
- Backend: Python (FastAPI, SQLAlchemy, Docker SDK)
- Frontend: React 18 + Tailwind CSS
- Images: Multi-stage Docker builds (controller + runtime)
- Storage: Host bind or named volume at `data/servers/<server_name>`
- DB: Postgres (in CI) / can fallback to SQLite (if configured separately)

## Project Structure
```
minecraft-server/
  backend/
  frontend/
  docker/
  docker-compose.yml
```

## Local Dev
- Backend: `cd backend && pip install -r requirements.txt && uvicorn app:app --reload`
- Frontend: `cd frontend && npm install && npm start`

## Quick Start (Docker Compose)

1. Clone repo (optional if just using images):
```
git clone https://github.com/blockypanel/Blockpanel.git  # (Repo path stable even if Docker namespace differs)
cd Blockpanel
```
2. Pull image:
```
docker pull moresonsun/blockpanel-unified:latest
```
3. (Optional) Adjust `docker-compose.yml` to pin a version tag instead of :latest.
4. Launch (build locally if modifying sources):
```
docker compose up -d --build
```
5. Open: http://localhost:8000

Data persists under `./data/servers/` (or mapped volume). Each server runs in its own container created by the controller using the runtime image.

## Local Development
Build unified image locally:
```
docker build -t blockpanel-unified:dev -f docker/controller-unified.Dockerfile .
```
Run:
```
docker compose up -d --build
```

## Troubleshooting: `protocol not available` During `docker compose up --build`
On some Docker Desktop / Windows setups, especially when BuildKit or buildx integration is in a transient state, you may see an immediate `protocol not available` with a 0/0 build graph.

Common causes & fixes:
- BuildKit temporarily unhappy / stale builder context.
  Fix: Restart Docker Desktop OR run:
  ```
  docker buildx inspect --bootstrap
  docker buildx ls
  ```
- Disabled BuildKit via environment variables (`DOCKER_BUILDKIT=0` or `COMPOSE_DOCKER_CLI_BUILD=0`). These disable optimized builds and can surface obscure errors.
  Fix: Remove or unset those vars in your shell and retry.
- Outdated Docker Desktop (older Compose versions had occasional WSL2 socket glitches).
  Fix: Update Docker Desktop.
- Corrupted buildx builder instance.
  Fix:
  ```
  docker buildx rm blockpanelx  # or the failing builder name
  docker buildx create --name blockpanelx --use
  docker buildx inspect --bootstrap
  ```
- WSL2 backend networking hiccup (less common now).
  Fix: `wsl --shutdown` from an elevated PowerShell, then restart Docker Desktop.

If the error occurs only with the dev override + `--build` but manual `docker build` works:
1. Ensure BuildKit is enabled (unset `DOCKER_BUILDKIT` or set it to `1`).
2. Run a manual build once (as you did) to populate the local image, then `docker compose ... up -d` without `--build` while you diagnose.
3. Run `docker compose config` to confirm the merged file shows the expected `blockpanel-dev-controller:latest` image and not the remote one.

If problems persist, capture:
```
docker version
docker buildx ls
docker compose version
docker compose -f docker-compose.yml -f docker-compose.dev.yml config
```
And open an issue with that output.

## Environment Variables

## Environment Variables
| Variable | Purpose | Default |
|----------|---------|---------|
| APP_NAME | Branding for UI/backend `/branding` | BlockPanel |
| APP_VERSION | Optional version string exposed at `/branding` | 0.1.0 |
| SERVERS_CONTAINER_ROOT | Container path for servers data | /data/servers |
| SERVERS_HOST_ROOT | Absolute host path (for bind mapping) | (inferred) |
| SERVERS_VOLUME_NAME | Named volume (if using volumes) | minecraft-server_mc_servers_data |

Frontend build-time override: set `REACT_APP_APP_NAME` to change displayed branding.

## Branding Endpoint
`GET /branding` returns `{ "name": APP_NAME, "version": APP_VERSION }` to allow dynamic frontend adaptation.

## Building Image Manually
```
docker build -t blockpanel-unified:dev -f docker/controller-unified.Dockerfile .
```

## Multi-Arch Notes
The CI workflow uses `docker/setup-buildx-action` and `docker/build-push-action` to publish `linux/amd64, linux/arm64` manifests. Local multi-arch emulate build example:
```
docker buildx create --name bp --use
docker buildx build -f docker/controller-unified.Dockerfile -t moresonsun/blockpanel-unified:test --platform linux/amd64,linux/arm64 --push .
```

## Releasing
Push an annotated git tag starting with `v` (e.g. `v0.1.0`) to trigger version-tagged unified image publish:
```
git tag -a v0.1.0 -m "v0.1.0"
git push --tags
```

## GitLab Mirror / Dual-Registry Workflow

Push to GitHub (primary) and mirror to GitLab (or add GitLab as a second remote) to leverage both registries:
```
git remote add gitlab https://gitlab.com/kyzen4/blockpanel.git
git push gitlab main
```
Set GitLab CI/CD variables:
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`
- (optional) `GITLAB_PUSH=true` to publish images to `registry.gitlab.com/kyzen4/blockpanel/*`.

Run a tagged release on either platform (`vX.Y.Z`) to produce versioned images in both registries.

Pulling by version:
```
docker pull moresonsun/blockpanel-unified:v0.1.1
```

## Namespace & Branding Strategy

Current Docker Hub default namespace: `moresonsun`.

Future branding (planned): a dedicated `blockypanel` organization. When ready:
1. Create org + public repos `blockpanel` and `blockpanel-runtime`.
2. In CI/CD variables set `DOCKERHUB_NAMESPACE=blockypanel` (or explicit `DOCKERHUB_REPO` / `DOCKERHUB_RUNTIME_REPO`).
3. Tag a new release; images will appear under the new org while existing tags in `moresonsun/*` remain for backwards compatibility.

Consumers who want to stay on the old namespace need not change anything until you announce deprecation.

## Roadmap (Excerpt)
- Websocket or SSE live logs (reduce polling)
- Template/modpack catalog UI enhancements
- Advanced metrics (prometheus style endpoint)
- Plugin & mod marketplace integration
- Automatic port range reservation and conflict resolution

## Contributing
PRs and issues welcome. Keep changes small & focused. Include reproduction steps for bug reports.

## License
Currently unlicensed (all rights reserved) unless updated. Add a LICENSE file before public distribution if desired.

> Ultra-Quick Install (Controller only, ephemeral DB fallback)
>
> 1. Pull image (or rely on on-demand pull):
>    docker pull moresonsun/blockypanel:latest
> 2. Start with compose (build not required unless modifying source):
>    curl -L https://raw.githubusercontent.com/blockypanel/Blockpanel/main/docker-compose.min.yml -o docker-compose.yml
>    docker compose up -d controller
>
> Or if you cloned the repo already:
>    docker compose up -d controller
>
> Need Postgres + runtime prewarm? Use the full docker-compose.yml in the repo instead of docker-compose.min.yml.
