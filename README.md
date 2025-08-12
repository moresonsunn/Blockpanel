# Minecraft Server Manager (Crafty-like)

A web-based application to create, manage, and monitor Minecraft servers using Docker containers.

## Features (MVP)
- Web UI to manage Minecraft servers (create, start, stop, delete, view logs)
- Backend API for server management
- Supports Vanilla, Paper, Purpur, Fabric, Forge, NeoForge
- Docker integration for running servers with per-server data directories
- One-container controller image serving API + UI

## Tech Stack
- Backend: Python (FastAPI)
- Frontend: React
- Docker: Runtime container (Java 21) and Controller container
- Storage: Local `data/servers/<name>`

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

## Build and Run Controller (single container)
- Build runtime (for actual servers):
  - `docker build -t mc-runtime:latest -f docker/runtime.Dockerfile docker`
- Enable Docker Desktop TCP endpoint:
  - Docker Desktop → Settings → Docker Engine → set `{ "hosts": ["tcp://0.0.0.0:2375", "npipe://"] }` or enable “Expose daemon on tcp://localhost:2375 without TLS”
- Build and run controller:
  - `docker compose up -d --build`
- Open `http://localhost:8000` → UI served at `/ui`, API under `/`

Data persists in `data/servers/` on the host. The controller talks to Docker via `DOCKER_HOST=tcp://host.docker.internal:2375`.
