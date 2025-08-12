from pathlib import Path
from typing import List
from fastapi import HTTPException, UploadFile
from config import SERVERS_ROOT


def _server_path(name: str) -> Path:
    server_dir = (SERVERS_ROOT / name).resolve()
    if not server_dir.exists():
        raise HTTPException(status_code=404, detail="Server not found")
    return server_dir


def _safe_join(base: Path, rel: str) -> Path:
    target = (base / rel).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid path")
    return target


def list_dir(name: str, rel: str = ".") -> List[dict]:
    base = _server_path(name)
    target = _safe_join(base, rel)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    items = []
    for p in sorted(target.iterdir(), key=lambda x: x.name.lower()):
        items.append({
            "name": p.name,
            "is_dir": p.is_dir(),
            "size": p.stat().st_size,
        })
    return items


def read_file(name: str, rel: str) -> str:
    base = _server_path(name)
    target = _safe_join(base, rel)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return target.read_text(encoding="utf-8", errors="ignore")


def write_file(name: str, rel: str, content: str) -> None:
    base = _server_path(name)
    target = _safe_join(base, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def delete_path(name: str, rel: str) -> None:
    base = _server_path(name)
    target = _safe_join(base, rel)
    if target.is_dir():
        for p in target.rglob("*"):
            if p.is_file():
                p.unlink()
        target.rmdir()
    elif target.exists():
        target.unlink()


def upload_file(name: str, rel_dir: str, up: UploadFile) -> None:
    base = _server_path(name)
    target_dir = _safe_join(base, rel_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / up.filename
    with dest.open("wb") as f:
        f.write(up.file.read())
