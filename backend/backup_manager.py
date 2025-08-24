from pathlib import Path
import shutil
import time
from typing import List
from fastapi import HTTPException
from config import SERVERS_ROOT

BACKUPS_ROOT = SERVERS_ROOT.parent / "backups"
BACKUPS_ROOT.mkdir(parents=True, exist_ok=True)


def _server_path(name: str) -> Path:
    server_dir = (SERVERS_ROOT / name).resolve()
    if not server_dir.exists():
        raise HTTPException(status_code=404, detail="Server not found")
    return server_dir


def list_backups(name: str) -> List[dict]:
    server_dir = _server_path(name)
    dest_dir = BACKUPS_ROOT / name
    dest_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for p in sorted(dest_dir.glob("*.zip")):
        items.append({
            "file": p.name,
            "size": p.stat().st_size,
            "modified": int(p.stat().st_mtime),
        })
    return items


def create_backup(name: str, compression: str = 'zip') -> dict:
    server_dir = _server_path(name)
    ts = time.strftime("%Y%m%d-%H%M%S")
    dest_dir = BACKUPS_ROOT / name
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive_base = dest_dir / f"{name}-{ts}"
    fmt = compression if compression in {"zip", "gztar", "bztar", "tar"} else 'zip'
    archive_file = shutil.make_archive(str(archive_base), fmt, root_dir=str(server_dir))
    p = Path(archive_file)
    return {"file": p.name, "size": p.stat().st_size}


def restore_backup(name: str, backup_file: str) -> None:
    server_dir = _server_path(name)
    dest_dir = BACKUPS_ROOT / name
    archive = (dest_dir / backup_file).resolve()
    if not str(archive).startswith(str(dest_dir)) or not archive.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    # Extract into server directory (overwrite)
    shutil.unpack_archive(str(archive), str(server_dir))


def delete_backup(name: str, backup_file: str) -> None:
    server_dir = _server_path(name)
    dest_dir = BACKUPS_ROOT / name
    archive = (dest_dir / backup_file).resolve()
    if not str(archive).startswith(str(dest_dir)) or not archive.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    archive.unlink()
