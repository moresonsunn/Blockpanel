from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from pathlib import Path

from database import get_db
from auth import require_auth, require_moderator
from models import User
from file_manager import upload_file as fm_upload_file, delete_path as fm_delete_path
from docker_manager import DockerManager
from config import SERVERS_ROOT

router = APIRouter(prefix="/plugins", tags=["plugins"])


def _server_dir(server_name: str) -> Path:
    server_dir = (SERVERS_ROOT / server_name).resolve()
    if not server_dir.exists():
        raise HTTPException(status_code=404, detail="Server not found")
    return server_dir


def _plugins_dir(server_name: str) -> Path:
    base = _server_dir(server_name)
    pdir = base / "plugins"
    pdir.mkdir(parents=True, exist_ok=True)
    return pdir


def _get_docker_manager() -> DockerManager:
    return DockerManager()


@router.get("/{server_name}")
async def list_plugins(
    server_name: str,
    current_user: User = Depends(require_auth),
):
    """List plugin JARs in the server's plugins directory."""
    pdir = _plugins_dir(server_name)
    items: List[dict] = []
    for p in sorted(pdir.glob("*.jar")):
        items.append({
            "name": p.name,
            "size": p.stat().st_size,
            "modified": int(p.stat().st_mtime),
        })
    return {"plugins": items}


@router.post("/{server_name}/upload")
async def upload_plugin(
    server_name: str,
    file: UploadFile = File(...),
    current_user: User = Depends(require_auth),
):
    """Upload a plugin JAR into the plugins directory."""
    if file is None or not getattr(file, "filename", None):
        raise HTTPException(status_code=400, detail="No file provided")
    if not (file.filename and file.filename.lower().endswith(".jar")):
        raise HTTPException(status_code=400, detail="Only .jar files are allowed")
    # Reuse file manager to handle safe write
    fm_upload_file(server_name, "plugins", file)
    return {"ok": True}


@router.delete("/{server_name}/{plugin_file}")
async def delete_plugin(
    server_name: str,
    plugin_file: str,
    current_user: User = Depends(require_moderator),
):
    """Delete a plugin JAR from the plugins directory."""
    # Prevent path traversal
    if "/" in plugin_file or ".." in plugin_file:
        raise HTTPException(status_code=400, detail="Invalid plugin file")
    path = f"plugins/{plugin_file}"
    fm_delete_path(server_name, path)
    return {"ok": True}


@router.post("/{server_name}/reload")
async def reload_plugins(
    server_name: str,
    current_user: User = Depends(require_moderator),
):
    """Reload plugins by issuing a server reload command."""
    dm = _get_docker_manager()
    servers = dm.list_servers()
    container_id = None
    for s in servers:
        if s.get("name") == server_name:
            container_id = s.get("id")
            break
    if not container_id:
        raise HTTPException(status_code=404, detail="Server container not found")
    # Paper supports `reload confirm`; fallback to `reload`
    resp = dm.send_command(container_id, "reload confirm")
    if resp.get("exit_code", 1) != 0:
        resp = dm.send_command(container_id, "reload")
    return {"ok": True, "method": resp.get("method"), "output": resp.get("output", "")}