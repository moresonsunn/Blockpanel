from fastapi import FastAPI, HTTPException, UploadFile, Form, Body, Query, Depends, Request, File
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel
from typing import Optional
from docker_manager import DockerManager
import server_providers  # noqa: F401 - ensure providers register
from server_providers.providers import get_provider_names, get_provider
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
import os
from file_manager import (
    list_dir as fm_list_dir,
    read_file as fm_read_file,
    write_file as fm_write_file,
    delete_path as fm_delete_path,
    upload_file as fm_upload_file,
    upload_files as fm_upload_files,
    rename_path as fm_rename_path,
    zip_path as fm_zip_path,
    unzip_path as fm_unzip_path,
)
from backup_manager import list_backups as bk_list, create_backup as bk_create, restore_backup as bk_restore
import requests
from bs4 import BeautifulSoup
import threading
import logging

# New imports for enhanced features
from database import init_db
from routers import (
    auth_router,
    scheduler_router,
    player_router,
    world_router,
    plugin_router,
    user_router,
    monitoring_router,
    health_router,
    modpack_router,
    catalog_router,
    integrations_router,
)
from auth import require_auth, get_current_user, require_admin, require_moderator
from scheduler import get_scheduler
from models import User
from config import SERVERS_ROOT, APP_NAME

def get_forge_loader_versions(mc_version: str) -> list[str]:
    url = f"https://files.minecraftforge.net/net/minecraftforge/forge/index_{mc_version}.html"
    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    versions = [
        tr.find_all("td")[0].get_text(strip=True)
        for tr in soup.select("table.downloads-table tbody tr")
        if tr.find_all("td")
    ]
    return versions


def get_fabric_loader_versions(minecraft_version: str):
    url = f"https://meta.fabricmc.net/v2/versions/loader/{minecraft_version}"
    resp = requests.get(url)
    if resp.status_code != 200:
        raise Exception(f"Failed to fetch loader versions from FabricMC meta for version {minecraft_version}")

    data = resp.json()
    # Each entry: {"loader": {"version": "<ver>", ...}, ...}
    loader_versions = [entry["loader"]["version"] for entry in data if "loader" in entry and "version" in entry["loader"]]
    return loader_versions

def get_neoforge_loader_versions():
    url = "https://neoforged.net/"
    resp = requests.get(url)
    if resp.status_code != 200:
        raise Exception("Failed to load NeoForged main page")
    soup = BeautifulSoup(resp.content, "html.parser")
    versions = []
    # Adjust the selector when you inspect the NeoForge page structure
    for row in soup.select("table.versions-table tbody tr"):
        tds = row.find_all("td")
        if tds and len(tds) > 0:
            ver = tds[0].get_text(strip=True)
            if ver:
                versions.append(ver)
    return versions


app = FastAPI()

# Enable gzip compression for API responses and static assets
try:
    from starlette.middleware.gzip import GZipMiddleware
    app.add_middleware(GZipMiddleware, minimum_size=1000)
except Exception:
    # If starlette version lacks middleware or import fails, continue without compression
    pass

# Include all routers
app.include_router(auth_router)
app.include_router(scheduler_router)
app.include_router(player_router)
app.include_router(world_router)
app.include_router(plugin_router)
app.include_router(user_router)
app.include_router(monitoring_router)
app.include_router(health_router)
app.include_router(modpack_router)
app.include_router(catalog_router)
app.include_router(integrations_router)


@app.on_event("startup")
async def startup_event():
    """Initialize the application when it starts."""
    print("Starting up application...")
    logging.basicConfig(level=logging.INFO)
    try:
        # Initialize database
        print("Initializing database...")
        logging.info("Initializing database...")
        init_db()
        print("Database initialized successfully")
        logging.info("Database initialized")
        
        # Start task scheduler
        logging.info("Starting task scheduler...")
        scheduler = get_scheduler()
        scheduler.start()
        logging.info("Task scheduler started")
        
    except Exception as e:
        logging.error(f"Error during startup: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up when the application shuts down."""
    try:
        # Stop task scheduler
        scheduler = get_scheduler()
        scheduler.stop()
        logging.info("Task scheduler stopped")
        
    except Exception as e:
        logging.error(f"Error during shutdown: {e}")

_docker_manager: DockerManager | None = None

def get_docker_manager() -> DockerManager:
    global _docker_manager
    if _docker_manager is None:
        ## AI Error Fixer feature has been removed.
            "loader_site_url": loader_site_url,
        }
        payload.update(extra)
        return payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/servers")
def list_servers(current_user: User = Depends(require_auth)):
    try:
        return get_docker_manager().list_servers()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")

@app.get("/ports/used")
def list_used_ports(from_port: int | None = Query(None), to_port: int | None = Query(None), current_user: User = Depends(require_auth)):
    """
    List host ports currently used by Docker containers.
    Optionally filter by range [from_port, to_port].
    """
    try:
        dm = get_docker_manager()
        used = dm.get_used_host_ports(only_minecraft=False)
        if from_port is not None and to_port is not None and from_port <= to_port:
            used = {p for p in used if from_port <= p <= to_port}
        return {"ports": sorted(list(used))}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")

@app.get("/ports/validate")
def validate_port(port: int = Query(..., ge=1, le=65535), current_user: User = Depends(require_auth)):
    """
    Validate if a given host port is available (not used by Docker containers).
    Note: Does not detect non-Docker processes bound to the host.
    """
    try:
        dm = get_docker_manager()
        used = dm.get_used_host_ports(only_minecraft=False)
        return {"port": port, "available": int(port) not in used}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")

@app.get("/ports/suggest")
def suggest_port(
    start: int = Query(25565, ge=1, le=65535),
    end: int = Query(25999, ge=1, le=65535),
    preferred: int | None = Query(None, ge=1, le=65535),
    current_user: User = Depends(require_auth)
):
    """
    Suggest an available host port by scanning Docker port mappings.
    """
    try:
        dm = get_docker_manager()
        port = dm.pick_available_port(preferred=preferred, start=start, end=end)
        return {"port": port}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/servers")
def create_server(req: ServerCreateRequest, current_user: User = Depends(require_auth)):
    try:
        # Convert RAM values to proper format
        def format_ram(ram_value):
            if isinstance(ram_value, int):
                # Convert MB to G format
                if ram_value >= 1024:
                    return f"{ram_value // 1024}G"
                else:
                    return f"{ram_value}M"
            else:
                # Already a string, return as is
                return str(ram_value)
        
        min_ram = format_ram(req.min_ram)
        max_ram = format_ram(req.max_ram)
        
        # Pass loader_version if present, otherwise None
        return get_docker_manager().create_server(
            req.name, req.type, req.version, req.host_port, req.loader_version, min_ram, max_ram, req.installer_version
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")

@app.post("/servers/{container_id}/start")
def start_server(container_id: str):
    try:
        return get_docker_manager().start_server(container_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")

@app.post("/servers/{container_id}/stop")
def stop_server(container_id: str):
    try:
        return get_docker_manager().stop_server(container_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")

from pydantic import BaseModel

class PowerSignal(BaseModel):
    signal: str  # start | stop | restart | kill

class MkdirRequest(BaseModel):
    path: str

@app.post("/servers/{container_id}/power")
def power_server(container_id: str, payload: PowerSignal, current_user: User = Depends(require_moderator)):
    try:
        signal = payload.signal.lower().strip()
        dm = get_docker_manager()
        if signal == "start":
            return dm.start_server(container_id)
        elif signal == "stop":
            return dm.stop_server(container_id)
        elif signal == "restart":
            return dm.restart_server(container_id)
        elif signal == "kill":
            return dm.kill_server(container_id)
        else:
            raise HTTPException(status_code=400, detail="Invalid signal. Must be one of: start, stop, restart, kill")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")

@app.get("/servers/{container_id}/resources")
def get_server_resources(container_id: str, current_user: User = Depends(require_auth)):
    try:
        dm = get_docker_manager()
        stats = dm.get_server_stats(container_id)
        players = dm.get_player_info(container_id)
        # Backward-compatible flat fields plus structured payload
        response = {
            "id": stats.get("id", container_id),
            "cpu_percent": stats.get("cpu_percent", 0.0),
            "memory_usage_mb": stats.get("memory_usage_mb", 0.0),
            "memory_limit_mb": stats.get("memory_limit_mb", 0.0),
            "memory_percent": stats.get("memory_percent", 0.0),
            "network_rx_mb": stats.get("network_rx_mb", 0.0),
            "network_tx_mb": stats.get("network_tx_mb", 0.0),
            "player_count": players.get("online", 0),
            "resources": {
                "cpu_percent": stats.get("cpu_percent", 0.0),
                "memory": {
                    "used_mb": stats.get("memory_usage_mb", 0.0),
                    "limit_mb": stats.get("memory_limit_mb", 0.0),
                    "percent": stats.get("memory_percent", 0.0),
                },
                "network": {
                    "rx_mb": stats.get("network_rx_mb", 0.0),
                    "tx_mb": stats.get("network_tx_mb", 0.0),
                },
            },
            "players": {
                "online": players.get("online", 0),
                "max": players.get("max", 0),
                "names": players.get("names", []),
            },
        }
        return response
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")

@app.delete("/servers/{container_id}")
def delete_server(container_id: str, current_user: User = Depends(require_moderator)):
    try:
        return get_docker_manager().delete_server(container_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")

# Simple directory creation endpoint for Files panel
@app.post("/servers/{name}/mkdir")
def mkdir_path(name: str, req: MkdirRequest, current_user: User = Depends(require_moderator)):
    try:
        base = SERVERS_ROOT.resolve() / name
        target = (base / req.path).resolve()
        if not str(target).startswith(str(base)):
            raise HTTPException(status_code=400, detail="Invalid path")
        target.mkdir(parents=True, exist_ok=True)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/servers/{container_id}/logs")
def get_server_logs(container_id: str):
    try:
        return get_docker_manager().get_server_logs(container_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")

@app.post("/servers/{container_id}/command")
def send_command(container_id: str, command: str = Body(..., embed=True)):
    try:
        if not command or not command.strip():
            raise HTTPException(status_code=400, detail="Command cannot be empty")
        if command.startswith("/"):
            command = command[1:]
        return get_docker_manager().send_command(container_id, command)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")

@app.get("/servers/{container_id}/stats")
def get_server_stats(container_id: str):
    try:
        return get_docker_manager().get_server_stats(container_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Stats unavailable: {e}")

@app.get("/servers/stats")
def get_bulk_stats(ttl: int = Query(3, ge=0, le=60), current_user: User = Depends(require_auth)):
    """Return stats for all servers in one response (cached briefly)."""
    try:
        dm = get_docker_manager()
        return dm.get_bulk_server_stats(ttl_seconds=ttl)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Stats unavailable: {e}")

@app.get("/servers/{container_id}/info")
def get_server_info(container_id: str, request: Request):
    try:
        info = get_docker_manager().get_server_info(container_id)
        # Attach top-level directory snapshot and common subdirs for instant files panel
        try:
            name = info.get("name") or info.get("container_name") or info.get("server_name")
            if name:
                snap = fm_list_dir(name, ".")
                info["dir_snapshot"] = snap[:200]
                # Deep snapshot for common subdirs
                deep = {}
                for sub in ["world", "world_nether", "world_the_end", "plugins", "mods", "config", "datapacks"]:
                    try:
                        items = fm_list_dir(name, sub)
                        if isinstance(items, list) and items:
                            deep[sub] = items[:100]
                    except Exception:
                        continue
                info["dir_snapshot_deep"] = deep
        except Exception:
            info.setdefault("dir_snapshot", [])
            info.setdefault("dir_snapshot_deep", {})
        
        # Generate a simple ETag using dir mtime and java_version if present
        etag = None
        try:
            from pathlib import Path
            import hashlib
            base = (SERVERS_ROOT.resolve() / (info.get("name") or "")).resolve()
            st = base.stat() if base.exists() else None
            sig = f"{info.get('java_version','')}-{int(st.st_mtime) if st else 0}"
            etag = 'W/"info-' + hashlib.md5(sig.encode()).hexdigest() + '"'
        except Exception:
            etag = None

        inm = request.headers.get("if-none-match") if request else None
        headers = {"ETag": etag} if etag else {}
        if etag and inm == etag:
            from starlette.responses import Response
            return Response(status_code=304, headers=headers)
        return JSONResponse(content=info, headers=headers)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Server info unavailable: {e}")

@app.get("/servers/{container_id}/console")
def get_server_console(container_id: str, tail: int = 100):
    try:
        return get_docker_manager().get_server_terminal(container_id, tail=tail)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Console unavailable: {e}")

#

@app.get("/servers/{name}/files")
def files_list(name: str, request: Request, path: str = "."):
    # Compute a simple ETag based on directory mtime to enable client caching
    try:
        from pathlib import Path
        base = (SERVERS_ROOT.resolve() / name / path).resolve()
        # Prevent path traversal
        root = SERVERS_ROOT.resolve() / name
        if not str(base).startswith(str(root)):
            raise HTTPException(status_code=400, detail="Invalid path")
        if base.exists() and base.is_dir():
            # Combine mtime with entry count for better change detection
            try:
                with os.scandir(base) as it:
                    count = sum(1 for _ in it)
            except Exception:
                count = 0
            st = base.stat()
            etag = f'W/"dir-{count}-{int(st.st_mtime)}"'
        elif base.exists():
            st = base.stat()
            etag = f'W/"dirfile-{st.st_size}-{int(st.st_mtime)}"'
        else:
            etag = 'W/"dir-0"'
    except Exception:
        etag = None

    inm = request.headers.get("if-none-match") if request else None
    if etag and inm == etag:
        from starlette.responses import Response
        return Response(status_code=304, headers={"ETag": etag})

    items = fm_list_dir(name, path)
    headers = {"ETag": etag} if etag else {}
    return JSONResponse(content={"items": items}, headers=headers)

@app.get("/servers/{name}/file")
def file_read(name: str, request: Request, path: str):
    # ETag based on file size and mtime
    try:
        from pathlib import Path
        p = (SERVERS_ROOT.resolve() / name / path).resolve()
        root = SERVERS_ROOT.resolve() / name
        if not str(p).startswith(str(root)):
            raise HTTPException(status_code=400, detail="Invalid path")
        if p.exists() and p.is_file():
            st = p.stat()
            etag = f'W/"file-{st.st_size}-{int(st.st_mtime)}"'
        else:
            etag = 'W/"file-0-0"'
    except Exception:
        etag = None

    inm = request.headers.get("if-none-match") if request else None
    if etag and inm == etag:
        from starlette.responses import Response
        return Response(status_code=304, headers={"ETag": etag})

    content = fm_read_file(name, path)
    headers = {"ETag": etag} if etag else {}
    return JSONResponse(content={"content": content}, headers=headers)

@app.post("/servers/{name}/file")
def file_write(name: str, path: str, content: str = Form(...)):
    fm_write_file(name, path, content)
    return {"ok": True}

@app.delete("/servers/{name}/file")
def file_delete(name: str, path: str):
    fm_delete_path(name, path)
    return {"ok": True}

@app.get("/servers/{name}/download")
def file_or_folder_download(name: str, path: str = Query(".")):
    """
    Download a single file directly, or if a directory is requested, return a zipped archive on the fly.
    """
    from pathlib import Path
    base = (SERVERS_ROOT / name).resolve()
    target = (base / path).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")

    if target.is_file():
        return FileResponse(str(target), filename=target.name)
    # It's a directory: create a temporary zip and send it
    import tempfile, shutil
    tmpdir = Path(tempfile.mkdtemp(prefix="dl_zip_"))
    archive_base = tmpdir / (Path(path).name or "folder")
    # shutil.make_archive adds extension automatically
    archive_path = shutil.make_archive(str(archive_base), 'zip', root_dir=str(target))
    fname = f"{(Path(path).name or 'folder')}.zip"
    return FileResponse(archive_path, filename=fname)

@app.post("/servers/{name}/upload")
async def file_upload(
    name: str,
    path: str = Query("."),
    file: UploadFile = File(...),
    current_user: User = Depends(require_auth),
):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")
    # Stream upload to disk asynchronously to improve throughput and reduce memory
    from file_manager import get_upload_dest, sanitize_filename
    from pathlib import Path
    dest = get_upload_dest(name, path, file.filename or "uploaded")
    try:
        with dest.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    finally:
        try:
            await file.close()
        except Exception:
            pass
    # Post-process potential server icon uploads
    try:
        from file_manager import maybe_process_server_icon
        maybe_process_server_icon(name, dest, file.filename or dest.name)
    except Exception:
        pass
    # Invalidate caches for this server after upload
    try:
        from file_manager import _invalidate_cache
        _invalidate_cache(name)
    except Exception:
        pass
    return {"ok": True}

class RenameRequest(BaseModel):
    src: str
    dest: str

@app.post("/servers/{name}/rename")
def file_rename(name: str, req: RenameRequest, current_user: User = Depends(require_moderator)):
    fm_rename_path(name, req.src, req.dest)
    return {"ok": True}

@app.post("/servers/{name}/upload-multiple")
async def files_upload(
    name: str,
    path: str = Form("."),
    files: list[UploadFile] = File(...),
    current_user: User = Depends(require_auth),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    count = fm_upload_files(name, path, files)
    return {"ok": True, "count": count}

class ZipRequest(BaseModel):
    path: str
    dest: str | None = None

class UnzipRequest(BaseModel):
    path: str
    dest: str | None = None

@app.post("/servers/{name}/zip")
def make_zip(name: str, req: ZipRequest, current_user: User = Depends(require_moderator)):
    archive_rel = fm_zip_path(name, req.path, req.dest)
    return {"ok": True, "archive": archive_rel}

@app.post("/servers/{name}/unzip")
def do_unzip(name: str, req: UnzipRequest, current_user: User = Depends(require_moderator)):
    dest_rel = fm_unzip_path(name, req.path, req.dest)
    return {"ok": True, "dest": dest_rel}

@app.get("/servers/{name}/backups")
def backups_list(name: str):
    return {"items": bk_list(name)}

@app.post("/servers/{name}/backups")
def backups_create(name: str):
    return bk_create(name)

@app.post("/servers/{name}/restore")
def backups_restore(name: str, file: str):
    bk_restore(name, file)
    return {"ok": True}

@app.get("/servers/{name}/players")
def players_list(name: str):
    return {"players": []}

@app.get("/servers/{name}/configs")
def configs_list(name: str):
    return {"configs": ["server.properties", "bukkit.yml", "spigot.yml"]}
@app.get("/servers/{name}/config-bundle")
def get_server_config_bundle(name: str, container_id: str | None = Query(None)):
    """Return a bundle of server.properties (parsed) and EULA state.
    This reduces multiple round-trips for the Config panel.
    """
    try:
        # Read server.properties
        props_text = fm_read_file(name, "server.properties")
    except Exception:
        props_text = ""
    try:
        eula_text = fm_read_file(name, "eula.txt")
    except Exception:
        eula_text = ""

    # Parse properties into dict
    props_map = {}
    try:
        for line in (props_text or "").splitlines():
            if not line or line.strip().startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                props_map[k.strip()] = v.strip()
    except Exception:
        pass

    eula_accepted = False
    try:
        eula_accepted = any(
            part.strip().lower() == "eula=true" for part in (eula_text or "").splitlines()
        )
    except Exception:
        eula_accepted = False

    # Java info (if container_id provided)
    java = None
    try:
        if container_id:
            dm = get_docker_manager()
            info = dm.get_server_info(container_id)
            java_version = info.get("java_version", "unknown")
            java = {
                "current_version": java_version,
                "available_versions": ["8", "11", "17", "21"]
            }
    except Exception:
        java = None

    return {
        "properties": props_map,
        "eula_accepted": eula_accepted,
        "java": java,
    }

@app.get("/servers/{container_id}/java-versions")
def get_server_java_version(container_id: str):
    """Get the current Java version for a server."""
    try:
        docker_manager = get_docker_manager()
        container_info = docker_manager.get_server_info(container_id)
        
        # Get Java version from container environment or labels
        java_version = container_info.get("java_version", "unknown")
        java_bin = container_info.get("java_bin", "/usr/local/bin/java21")
        
        return {
            "java_version": java_version,
            "java_bin": java_bin,
            "available_versions": ["8", "11", "17", "21"]
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Java version info unavailable: {e}")
        raise HTTPException(status_code=404, detail=f"Java version info unavailable: {e}")

@app.post("/servers/{container_id}/java-version")
def set_server_java_version(container_id: str, request: dict = Body(...)):
    """Set the Java version for a server."""
    try:
        docker_manager = get_docker_manager()
        
        # Extract java_version from request
        java_version = request.get("java_version")
        if not java_version:
            raise HTTPException(status_code=400, detail="java_version is required")
        
        # Validate Java version
        if java_version not in ["8", "11", "17", "21"]:
            raise HTTPException(status_code=400, detail="Invalid Java version. Must be 8, 11, 17, or 21")
        
        # Update container environment variables
        result = docker_manager.update_server_java_version(container_id, java_version)
        
        return {
            "success": True,
            "message": f"Java version updated to {java_version}",
            "java_version": java_version,
            "java_bin": f"/usr/local/bin/java{java_version}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update Java version: {e}")

@app.get("/servers/{container_id}/java-versions")
def get_available_java_versions(container_id: str):
    """Get available Java versions and current selection."""
    try:
        docker_manager = get_docker_manager()
        container_info = docker_manager.get_server_info(container_id)
        
        # Get current Java version
        current_version = container_info.get("java_version", "21")
        current_bin = container_info.get("java_bin", "/usr/local/bin/java21")
        
        # Available versions with descriptions
        available_versions = [
            {"version": "8", "name": "Java 8", "description": "Legacy support (1.8-1.16)", "bin": "/usr/local/bin/java8"},
            {"version": "11", "name": "Java 11", "description": "Intermediate support", "bin": "/usr/local/bin/java11"},
            {"version": "17", "name": "Java 17", "description": "Modern support (1.17+)", "bin": "/usr/local/bin/java17"},
            {"version": "21", "name": "Java 21", "description": "Latest performance (1.19+)", "bin": "/usr/local/bin/java21"}
        ]
        
        return {
            "current_version": current_version,
            "current_bin": current_bin,
            "available_versions": available_versions
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Java versions info unavailable: {e}")

"""(AI error fixer routes removed)"""

# Mount the React UI at root as the last route so it doesn't shadow API endpoints
try:
    app.mount("/", StaticFiles(directory="static", html=True), name="ui")
except Exception:
    # Static directory may not exist in some environments (e.g., dev without build)
    pass

