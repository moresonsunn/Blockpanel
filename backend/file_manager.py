from pathlib import Path
from typing import List
import os
import time
from fastapi import HTTPException, UploadFile
from config import SERVERS_ROOT
import zipfile
import re
from typing import Optional

# Optional Pillow import (installed via requirements). Import lazily in function to avoid module load cost.


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


_DIR_CACHE_TTL = 3.0
_DIR_CACHE: dict[tuple[str, str], tuple[float, float, list[dict]]] = {}

def _invalidate_cache(name: str, rel: str | None = None) -> None:
    if rel is None:
        keys = [k for k in _DIR_CACHE.keys() if k[0] == name]
    else:
        # Invalidate all cached entries for this server; simple and safe
        keys = [k for k in _DIR_CACHE.keys() if k[0] == name]
    for k in keys:
        _DIR_CACHE.pop(k, None)


def list_dir(name: str, rel: str = ".") -> List[dict]:
    base = _server_path(name)
    target = _safe_join(base, rel)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    # Cache by (server, rel) and dir mtime; refresh if TTL expired or mtime changed
    try:
        st = target.stat()
        mtime = st.st_mtime
    except Exception:
        mtime = 0.0
    cache_key = (name, rel)
    cached = _DIR_CACHE.get(cache_key)
    now = time.time()
    if cached:
        cached_mtime, ts, data = cached
        if cached_mtime == mtime and (now - ts) <= _DIR_CACHE_TTL:
            return data

    items: list[dict] = []
    try:
        with os.scandir(target) as it:
            entries = sorted(list(it), key=lambda e: e.name.lower())
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    is_dir = True
                    size = 0
                else:
                    is_dir = False
                    try:
                        size = entry.stat(follow_symlinks=False).st_size
                    except Exception:
                        size = 0
                items.append({
                    "name": entry.name,
                    "is_dir": is_dir,
                    "size": size,
                })
            except Exception:
                continue
    except Exception:
        # Fallback to pathlib if scandir fails
        for p in sorted(target.iterdir(), key=lambda x: x.name.lower()):
            items.append({
                "name": p.name,
                "is_dir": p.is_dir(),
                "size": p.stat().st_size if p.is_file() else 0,
            })

    _DIR_CACHE[cache_key] = (mtime, now, items)
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
    _invalidate_cache(name)


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
    _invalidate_cache(name)


def upload_file(name: str, rel_dir: str, up: UploadFile) -> None:
    base = _server_path(name)
    target_dir = _safe_join(base, rel_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = up.filename or "uploaded"
    # Sanitize filename: strip path components and allow safe chars only
    filename = Path(filename).name
    filename = re.sub(r"[^A-Za-z0-9._\- ]+", "_", filename)
    if not filename:
        filename = "uploaded"
    dest = target_dir / filename
    # Stream to disk in chunks to avoid loading entire file in memory
    with dest.open("wb") as f:
        while True:
            chunk = up.file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    _invalidate_cache(name)

def sanitize_filename(filename: str) -> str:
    filename = Path(filename).name
    filename = re.sub(r"[^A-Za-z0-9._\- ]+", "_", filename)
    return filename or "uploaded"

def get_upload_dest(name: str, rel_dir: str, filename: str) -> Path:
    base = _server_path(name)
    target_dir = _safe_join(base, rel_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    safe = sanitize_filename(filename or "uploaded")
    return target_dir / safe


_ICON_CANDIDATE_RE = re.compile(r"^(server[-_ ]?icon)(\.[A-Za-z0-9]+)?$", re.IGNORECASE)
_IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif'}

def _is_server_icon_candidate(filename: str) -> bool:
    base = Path(filename).name
    if _ICON_CANDIDATE_RE.match(base):
        return True
    # Also accept exact 'server-icon.png'
    return base.lower() == 'server-icon.png'

def maybe_process_server_icon(name: str, saved_path: Path, original_filename: str) -> bool:
    """If the uploaded file looks like a server icon, convert/resize it to 64x64 PNG
    and save as server-icon.png in the server root. Returns True if processed.
    """
    try:
        # Only process image files
        ext = saved_path.suffix.lower()
        if ext not in _IMAGE_EXTS:
            return False
        if not _is_server_icon_candidate(original_filename) and saved_path.name.lower() != 'server-icon.png':
            return False

        try:
            from PIL import Image
        except Exception:
            # Pillow not available
            return False

        base = _server_path(name)
        dest_path = base / 'server-icon.png'

        with Image.open(saved_path) as im:
            # Convert to RGBA to preserve transparency if present
            if im.mode not in ('RGB', 'RGBA'):
                im = im.convert('RGBA')
            # Resize to 64x64 if needed
            if im.size != (64, 64):
                try:
                    resample = Image.Resampling.LANCZOS  # Pillow >= 9
                except Exception:
                    resample = getattr(Image, 'LANCZOS', getattr(Image, 'BICUBIC', 3))
                im = im.resize((64, 64), resample)
            # Save as PNG
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            im.save(dest_path, format='PNG')

        # If uploaded to a different path/name, remove the original to avoid duplicates
        try:
            if saved_path.exists() and saved_path.resolve() != dest_path.resolve():
                saved_path.unlink(missing_ok=True)
        except Exception:
            pass

        _invalidate_cache(name)
        return True
    except Exception:
        # On any processing error, leave the original file as-is
        return False


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
    _invalidate_cache(name)


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
    _invalidate_cache(name)
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
    _invalidate_cache(name)
    return str(dest_dir.relative_to(base))
