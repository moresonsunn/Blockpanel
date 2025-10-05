# BlockPanel (Minecraft Server Manager)

![GitLab CI](https://gitlab.com/kyzen4/blockpanel/badges/main/pipeline.svg)
![GitHub CI](https://github.com/blockypanel/Blockpanel/actions/workflows/ci.yml/badge.svg)
![Docker Pulls](https://img.shields.io/docker/pulls/blockypanel/blockpanel)
![Architecture](https://img.shields.io/badge/arch-amd64%20%7C%20arm64-blue)

BlockPanel is a modern web-based controller to create, manage, monitor, and automate multiple Minecraft servers using Docker containers. Inspired by Crafty but focused on:
- Fast, preload-first UI (React + Tailwind)
- Multi-provider support (Vanilla, Paper, Purpur, Fabric, Forge, NeoForge)
- Declarative server creation with loader + installer resolution
- Efficient file operations (streaming uploads, zip/unzip, optimistic UI, ETag cache busting)
- Colored live console with reset-on-power events
- Role & permission management (users, roles, audit logs)
- REST API + future extensibility

Docker images (multi-arch: linux/amd64 + linux/arm64) are automatically published:
- Controller UI/API: `blockypanel/blockpanel:latest`
- Runtime (Java server runner base): `blockypanel/blockpanel-runtime:latest`

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
git clone https://github.com/blockypanel/Blockpanel.git
cd Blockpanel
```
2. Pull images:
```
docker pull blockypanel/blockpanel:latest
docker pull blockypanel/blockpanel-runtime:latest
```
  Or from GitLab registry (if enabled & pushed):
```
docker pull registry.gitlab.com/kyzen4/blockpanel/blockpanel:latest
docker pull registry.gitlab.com/kyzen4/blockpanel/blockpanel-runtime:latest
```
3. (Optional) Adjust `docker-compose.yml` to use `blockypanel/blockpanel` & `blockypanel/blockpanel-runtime` if not already.
4. Launch:
```
docker compose up -d
```
5. Open: http://localhost:8000

Data persists under `./data/servers/` (or mapped volume). Each server runs in its own container created by the controller using the runtime image.

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

## Building Images Manually
```
docker build -t blockpanel-runtime:dev -f docker/runtime.Dockerfile .
docker build -t blockpanel:dev -f docker/controller.Dockerfile .
```

## Multi-Arch Notes
The CI workflow uses `docker/setup-buildx-action` and `docker/build-push-action` to publish `linux/amd64, linux/arm64` manifests. Local multi-arch emulate build example:
```
docker buildx create --name bp --use
docker buildx build -f docker/runtime.Dockerfile -t blockypanel/blockpanel-runtime:test --platform linux/amd64,linux/arm64 --push .
```

## Releasing
Push an annotated git tag starting with `v` (e.g. `v0.1.0`) to trigger version-tagged image publishes:
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
docker pull blockypanel/blockpanel:v0.1.1
docker pull registry.gitlab.com/kyzen4/blockpanel/blockpanel:v0.1.1
```

## Migration Notice (Repository & Image Renaming)

The project repository moved to `blockypanel/Blockpanel` and Docker images were renamed from the `moresonsun/*` namespace to `blockypanel/*`.

Old image names still work only until deprecation (if tags remain); update any scripts:
```
sed -i 's/moresonsun\/blockpanel/blockypanel\/blockpanel/g' docker-compose.yml
sed -i 's/moresonsun\/blockpanel-runtime/blockypanel\/blockpanel-runtime/g' docker-compose.yml
```
If using the installation script, pull a fresh copy (it now points to the new repo and image names).

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
