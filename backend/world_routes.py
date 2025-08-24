from fastapi import APIRouter, Depends, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path
import shutil
import tempfile
import time
from typing import List

from database import get_db
from auth import get_current_active_user, require_moderator
from models import User
from config import SERVERS_ROOT

router = APIRouter(prefix="/worlds", tags=["worlds"])


def _server_dir(server_name: str) -> Path:
    server_dir = (SERVERS_ROOT / server_name).resolve()
    if not server_dir.exists():
        raise HTTPException(status_code=404, detail="Server not found")
    return server_dir


def _detect_world_dirs(server_dir: Path) -> List[Path]:
    worlds: List[Path] = []
    for p in server_dir.iterdir():
        if p.is_dir():
            # A Minecraft world contains level.dat
            if (p / "level.dat").exists():
                worlds.append(p)
    # Fallback to known names if not detected
    for name in ["world", "world_nether", "world_the_end"]:
        p = server_dir / name
        if p.is_dir() and p not in worlds:
            worlds.append(p)
    return worlds


@router.get("/{server_name}")
async def list_worlds(
    server_name: str,
    current_user: User = Depends(get_current_active_user),
):
    server_dir = _server_dir(server_name)
    worlds = _detect_world_dirs(server_dir)
    items = []
    for w in worlds:
        size = 0
        try:
            for f in w.rglob('*'):
                if f.is_file():
                    size += f.stat().st_size
        except Exception:
            pass
        items.append({
            "name": w.name,
            "path": str(w.relative_to(server_dir)),
            "size": size,
        })
    return {"worlds": items}


@router.get("/{server_name}/download")
async def download_world(
    server_name: str,
    world: str = Query("world"),
    current_user: User = Depends(get_current_active_user),
):
    server_dir = _server_dir(server_name)
    world_dir = (server_dir / world).resolve()
    if not str(world_dir).startswith(str(server_dir)) or not world_dir.exists():
        raise HTTPException(status_code=404, detail="World not found")

    ts = time.strftime("%Y%m%d-%H%M%S")
    tmpdir = Path(tempfile.mkdtemp(prefix="worlddl_"))
    archive_base = tmpdir / f"{server_name}-{world}-{ts}"
    archive_path = shutil.make_archive(str(archive_base), 'zip', root_dir=str(world_dir))
    return FileResponse(archive_path, filename=f"{server_name}-{world}-{ts}.zip")


@router.post("/{server_name}/upload")
async def upload_world(
    server_name: str,
    file: UploadFile | None = None,
    world_name: str = Query("world"),
    current_user: User = Depends(require_moderator),
):
    if file is None:
        raise HTTPException(status_code=400, detail="No file provided")
    if not (file.filename.lower().endswith('.zip') or file.filename.lower().endswith('.tar') or file.filename.lower().endswith('.tar.gz')):
        raise HTTPException(status_code=400, detail="Only .zip/.tar(.gz) archives are allowed")
    # Ensure safe world name
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]+", world_name):
        raise HTTPException(status_code=400, detail="Invalid world name")

    server_dir = _server_dir(server_name)
    target_dir = (server_dir / world_name).resolve()
    if not str(target_dir).startswith(str(server_dir)):
        raise HTTPException(status_code=400, detail="Invalid target path")
    target_dir.mkdir(parents=True, exist_ok=True)

    # Save upload to temp and extract
    tmpdir = Path(tempfile.mkdtemp(prefix="worldup_"))
    tmpfile = tmpdir / file.filename
    with tmpfile.open('wb') as f:
        f.write(file.file.read())

    fmt = 'zip'
    if tmpfile.suffix == '.zip':
        fmt = 'zip'
    elif tmpfile.suffixes[-2:] == ['.tar', '.gz']:
        fmt = 'gztar'
    elif tmpfile.suffix == '.tar':
        fmt = 'tar'

    shutil.unpack_archive(str(tmpfile), str(target_dir), format=None)
    return {"ok": True, "world": world_name}


@router.post("/{server_name}/backup")
async def backup_world(
    server_name: str,
    world: str = Query("world"),
    compression: str = Query("zip"),
    current_user: User = Depends(require_moderator),
):
    server_dir = _server_dir(server_name)
    world_dir = (server_dir / world).resolve()
    if not str(world_dir).startswith(str(server_dir)) or not world_dir.exists():
        raise HTTPException(status_code=404, detail="World not found")

    ts = time.strftime("%Y%m%d-%H%M%S")
    from config import SERVERS_ROOT
    backups_root = SERVERS_ROOT.parent / "backups" / server_name
    backups_root.mkdir(parents=True, exist_ok=True)
    archive_base = backups_root / f"{server_name}-world-{world}-{ts}"

    fmt = compression if compression in {"zip", "gztar", "bztar", "tar"} else "zip"
    archive_path = shutil.make_archive(str(archive_base), fmt, root_dir=str(world_dir))
    p = Path(archive_path)
    return {"file": p.name, "size": p.stat().st_size}