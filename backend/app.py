from fastapi import FastAPI, HTTPException, UploadFile, Form, Body, Query, Depends
from pydantic import BaseModel
from docker_manager import DockerManager
import server_providers  # noqa: F401 - ensure providers register
from server_providers.providers import get_provider_names, get_provider
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from file_manager import list_dir as fm_list_dir, read_file as fm_read_file, write_file as fm_write_file, delete_path as fm_delete_path, upload_file as fm_upload_file
from backup_manager import list_backups as bk_list, create_backup as bk_create, restore_backup as bk_restore
from ai_error_fixer import start_ai_monitoring, stop_ai_monitoring, get_ai_status, manual_fix, upload_to_docker
import requests
from bs4 import BeautifulSoup
import threading
import logging

# New imports for enhanced features
from database import init_db
from auth_routes import router as auth_router
from scheduler_routes import router as scheduler_router
from player_routes import router as player_router
from template_routes import router as template_router
from world_routes import router as world_router
from plugin_routes import router as plugin_router
from api.user_routes import router as user_router
from monitoring_routes import router as monitoring_router
from health_routes import router as health_router
from modpack_routes import router as modpack_router
from auth import require_auth, get_current_user, require_admin, require_moderator
from scheduler import get_scheduler
from models import User
from server_templates import get_template_manager

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

# Include all routers
app.include_router(auth_router)
app.include_router(scheduler_router)
app.include_router(player_router)
app.include_router(template_router)
app.include_router(world_router)
app.include_router(plugin_router)
app.include_router(user_router)
app.include_router(monitoring_router)
app.include_router(health_router)
app.include_router(modpack_router)

try:
    app.mount("/ui", StaticFiles(directory="static", html=True), name="ui")
except Exception:
    pass

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
        
        # Check if AI auto-startup is enabled
        import json
        from pathlib import Path
        
        config_path = Path("ai_config.json")
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
                auto_startup = config.get("ai_error_fixer", {}).get("auto_startup", True)
        else:
            auto_startup = True  # Default to enabled if config doesn't exist
        
        if not auto_startup:
            logging.info("AI error monitoring auto-startup is disabled")
            return
        
        # Start AI monitoring in a background thread to avoid blocking startup
        def start_ai_background():
            try:
                start_ai_monitoring()
            except Exception as e:
                logging.error(f"Failed to start AI monitoring: {e}")
        
        ai_thread = threading.Thread(target=start_ai_background, daemon=True)
        ai_thread.start()
        logging.info("AI error monitoring started in background")
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
        
        # Stop AI monitoring
        stop_ai_monitoring()
        logging.info("AI error monitoring stopped")
    except Exception as e:
        logging.error(f"Error during shutdown: {e}")

_docker_manager: DockerManager | None = None

def get_docker_manager() -> DockerManager:
    global _docker_manager
    if _docker_manager is None:
        _docker_manager = DockerManager()
    return _docker_manager

class ServerCreateRequest(BaseModel):
    name: str
    type: str
    version: str
    loader_version: str | None = None  # Allow specifying loader version
    installer_version: str | None = None  # Fabric installer version
    host_port: int | None = None
    min_ram: int | str = 1024  # Minimum RAM (MB as int, or string like "1G")
    max_ram: int | str = 2048  # Maximum RAM (MB as int, or string like "2G")

@app.get("/")
def root_redirect():
    return RedirectResponse(url="/ui")

@app.get("/health")
def healthz():
    return {"status": "ok"}

@app.get("/server-types")
def list_server_types():
    """
    Returns a list of available server types.
    """
    return {"types": get_provider_names()}

@app.get("/server-types/{server_type}/versions")
def list_versions(server_type: str):
    try:
        provider = get_provider(server_type)
        return {"type": server_type, "versions": provider.list_versions()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/server-types/{server_type}/loader-versions")
def list_loader_versions(
    server_type: str,
    version: str = Query(..., description="Minecraft version to get loader versions for"),
):
    """
    Returns loader versions for a given server type and Minecraft version,
    and the URL to the loader site for that type/version.
    """
    try:
        if server_type.lower() == "fabric":
            loader_versions = get_fabric_loader_versions(version)
            loader_site_url = f"https://meta.fabricmc.net/v2/versions/loader/{version}/"
        elif server_type.lower() == "forge":
            loader_versions = get_forge_loader_versions(version)
            loader_site_url = f"https://files.minecraftforge.net/net/minecraftforge/forge/index_{version}.html"
        elif server_type.lower() == "neoforge":
            loader_versions = get_neoforge_loader_versions()  # or pass the version if needed
            loader_site_url = f"https://neoforged.net/"
        else:
            provider = get_provider(server_type)
            loader_versions = provider.list_loader_versions(version)
            loader_site_url = None

        return {
            "type": server_type,
            "version": version,
            "loader_versions": loader_versions,
            "loader_site_url": loader_site_url,
        }
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

@app.post("/servers")
def create_server(req: ServerCreateRequest, current_user: User = Depends(require_moderator)):
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
        base = Path("/data/servers").resolve() / name
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

@app.get("/servers/{container_id}/info")
def get_server_info(container_id: str):
    try:
        return get_docker_manager().get_server_info(container_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Server info unavailable: {e}")

@app.get("/servers/{container_id}/console")
def get_server_console(container_id: str, tail: int = 100):
    try:
        return get_docker_manager().get_server_terminal(container_id, tail=tail)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Console unavailable: {e}")

# Server Templates Endpoints
@app.get("/templates")
def list_templates(category: str = Query(None), popular: bool = Query(False)):
    """
    List all available server templates, optionally filtered by category or popularity
    """
    try:
        manager = get_template_manager()
        return {
            "templates": manager.list_templates(category=category, popular_only=popular),
            "categories": manager.get_categories()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/templates/{template_id}")
def get_template(template_id: str):
    """
    Get a specific template by ID
    """
    try:
        manager = get_template_manager()
        template = manager.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        return template.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/servers/from-template")
def create_server_from_template(
    template_id: str = Body(..., embed=True),
    name: str = Body(..., embed=True),
    host_port: int = Body(None, embed=True),
    current_user: User = Depends(require_moderator)
):
    """
    Create a server from a template
    """
    try:
        manager = get_template_manager()
        template = manager.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # Create server using template configuration
        return get_docker_manager().create_server(
            name=name,
            server_type=template.type,
            version=template.version,
            host_port=host_port,
            loader_version=template.loader_version,
            min_ram=template.min_ram,
            max_ram=template.max_ram,
            installer_version=template.installer_version
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to create server: {e}")

@app.get("/servers/{name}/files")
def files_list(name: str, path: str = "."):
    return {"items": fm_list_dir(name, path)}

@app.get("/servers/{name}/file")
def file_read(name: str, path: str):
    return {"content": fm_read_file(name, path)}

@app.post("/servers/{name}/file")
def file_write(name: str, path: str, content: str = Form(...)):
    fm_write_file(name, path, content)
    return {"ok": True}

@app.delete("/servers/{name}/file")
def file_delete(name: str, path: str):
    fm_delete_path(name, path)
    return {"ok": True}

@app.post("/servers/{name}/upload")
async def file_upload(name: str, path: str = ".", file: UploadFile | None = None):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")
    fm_upload_file(name, path, file)
    return {"ok": True}

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

@app.get("/servers/{container_id}/java-version")
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

# AI Error Fixer Endpoints
@app.post("/ai/start")
def start_ai_error_monitoring():
    """Start the AI error monitoring system."""
    try:
        start_ai_monitoring()
        return {"success": True, "message": "AI error monitoring started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start AI monitoring: {e}")

@app.post("/ai/stop")
def stop_ai_error_monitoring():
    """Stop the AI error monitoring system."""
    try:
        stop_ai_monitoring()
        return {"success": True, "message": "AI error monitoring stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop AI monitoring: {e}")

@app.get("/ai/status")
def get_ai_error_fixer_status():
    """Get the current status of the AI error fixer."""
    try:
        status = get_ai_status()
        # Add auto-startup configuration info
        import json
        from pathlib import Path
        
        config_path = Path("ai_config.json")
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
                auto_startup = config.get("ai_error_fixer", {}).get("auto_startup", True)
        else:
            auto_startup = True
        
        status["auto_startup_enabled"] = auto_startup
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get AI status: {e}")

@app.post("/ai/fix")
def trigger_manual_fix(error_type: str = Body(..., embed=True), container_id: str = Body(None, embed=True)):
    """Manually trigger a fix for a specific error type."""
    try:
        return manual_fix(error_type, container_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger manual fix: {e}")

@app.post("/ai/upload-docker")
def upload_application_to_docker(image_name: str = Body("minecraft-server-manager", embed=True)):
    """Upload the application to Docker Hub."""
    try:
        return upload_to_docker(image_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to Docker: {e}")

@app.post("/ai/rebuild-runtime")
def rebuild_runtime_image():
    """Rebuild the Docker runtime image with multiple Java versions."""
    try:
        import subprocess
        from pathlib import Path
        
        # Run docker build command
        cmd = [
            "docker", "build", "-t", "mc-runtime:latest", 
            "-f", "docker/runtime.Dockerfile", "docker"
        ]
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            cwd=Path.cwd().parent
        )
        
        if result.returncode == 0:
            return {"success": True, "message": "Runtime image rebuilt successfully"}
        else:
            return {"success": False, "error": f"Build failed: {result.stderr}"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rebuild runtime image: {e}")

@app.post("/ai/restart-containers")
def restart_all_containers():
    """Restart all Minecraft server containers."""
    try:
        docker_manager = get_docker_manager()
        servers = docker_manager.list_servers()
        
        results = []
        for server in servers:
            try:
                container_id = server.get("id")
                if container_id:
                    docker_manager.stop_server(container_id)
                    docker_manager.start_server(container_id)
                    results.append({"container": server.get("name"), "status": "restarted"})
            except Exception as e:
                results.append({"container": server.get("name"), "status": "failed", "error": str(e)})
        
        return {"success": True, "results": results}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restart containers: {e}")

@app.post("/ai/cleanup")
def cleanup_system():
    """Clean up the system by removing old containers, images, and files."""
    try:
        import subprocess
        from pathlib import Path
        
        results = []
        
        # Remove stopped containers
        cmd = ["docker", "container", "prune", "-f"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            results.append({"operation": "container_cleanup", "status": "success"})
        else:
            results.append({"operation": "container_cleanup", "status": "failed", "error": result.stderr})
        
        # Remove unused images
        cmd = ["docker", "image", "prune", "-f"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            results.append({"operation": "image_cleanup", "status": "success"})
        else:
            results.append({"operation": "image_cleanup", "status": "failed", "error": result.stderr})
        
        # Remove unused volumes
        cmd = ["docker", "volume", "prune", "-f"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            results.append({"operation": "volume_cleanup", "status": "success"})
        else:
            results.append({"operation": "volume_cleanup", "status": "failed", "error": result.stderr})
        
        # Clean up old log files
        log_dir = Path("logs")
        if log_dir.exists():
            for log_file in log_dir.glob("*.log"):
                if log_file.stat().st_size > 10 * 1024 * 1024:  # 10MB
                    log_file.unlink()
                    results.append({"operation": "log_cleanup", "file": log_file.name, "status": "removed"})
        
        return {"success": True, "results": results}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cleanup system: {e}")

