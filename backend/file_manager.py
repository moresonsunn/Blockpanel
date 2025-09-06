from pathlib import Path
from typing import List
from fastapi import HTTPException, UploadFile
from config import SERVERS_ROOT
import zipfile


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


def upload_files(name: str, rel_dir: str, files: List[UploadFile]) -> int:
    """Upload multiple files into a directory. Returns number of files uploaded."""
    count = 0
    for up in files:
        if up is None:
            continue
        upload_file(name, rel_dir, up)
        count += 1
    return count


def rename_path(name: str, src_rel: str, dest_rel: str) -> None:
    base = _server_path(name)
    src = _safe_join(base, src_rel)
    if not src.exists():
        raise HTTPException(status_code=404, detail="Source not found")
    dest = _safe_join(base, dest_rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dest)


def zip_path(name: str, rel: str, dest_rel: str | None = None) -> str:
    """Create a zip archive of a file or directory. Returns the archive relative path."""
    base = _server_path(name)
    target = _safe_join(base, rel)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")

    if dest_rel is None:
        # Default to current path + .zip
        if target.is_dir():
            dest_rel = f"{rel.rstrip('/')}" + ".zip"
        else:
            dest_rel = f"{rel}" + ".zip"
    archive_path = _safe_join(base, dest_rel)
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        if target.is_dir():
            for p in target.rglob('*'):
                if p.is_file():
                    # write with relative arcname from target
                    arcname = p.relative_to(base)
                    zf.write(p, arcname)
        else:
            zf.write(target, target.relative_to(base))
    return str(archive_path.relative_to(base))


def unzip_path(name: str, rel: str, dest_rel: str | None = None) -> str:
    """Extract a zip archive to destination directory. Returns the destination relative path."""
    base = _server_path(name)
    archive = _safe_join(base, rel)
    if not archive.exists() or not archive.is_file():
        raise HTTPException(status_code=404, detail="Archive not found")

    # Default destination is current directory (same folder as archive) or provided dest
    if dest_rel is None:
        dest_rel = str(Path(rel).with_suffix(''))
    dest_dir = _safe_join(base, dest_rel)
    dest_dir.mkdir(parents=True, exist_ok=True)

    def _safe_extract(zipf: zipfile.ZipFile, path: Path):
        for member in zipf.infolist():
            member_path = path / member.filename
            # Prevent directory traversal
            resolved = member_path.resolve()
            if not str(resolved).startswith(str(path.resolve())):
                raise HTTPException(status_code=400, detail="Unsafe zip entry path")
            if member.is_dir():
                resolved.mkdir(parents=True, exist_ok=True)
            else:
                resolved.parent.mkdir(parents=True, exist_ok=True)
                with zipf.open(member) as src, resolved.open('wb') as dst:
                    dst.write(src.read())

    with zipfile.ZipFile(archive, 'r') as zf:
        _safe_extract(zf, dest_dir)

    return str(dest_dir.relative_to(base))
