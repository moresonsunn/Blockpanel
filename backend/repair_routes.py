from fastapi import APIRouter, HTTPException, Depends
from pathlib import Path
import json, time, hashlib
from auth import require_moderator
from models import User
from config import SERVERS_ROOT
from docker_manager import fix_server_jar

router = APIRouter(prefix="/servers", tags=["server_maintenance"])

def _detect_type_version(server_dir: Path) -> tuple[str | None, str | None]:
    """Best-effort detection of server type and version from existing files."""
    stype = None
    sver = None
    try:
        # Check server_meta.json first
        meta_path = server_dir / "server_meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8", errors="ignore"))
                stype = meta.get("detected_type") or meta.get("server_type") or stype
                sver = meta.get("detected_version") or meta.get("server_version") or meta.get("version") or sver
            except Exception:
                pass
        # Inspect jars
        jar_files = [p for p in server_dir.glob("*.jar") if p.is_file()]
        # Prefer server.jar
        jar_files.sort(key=lambda p: (p.name != "server.jar", -p.stat().st_size))
        import re
        patterns = [
            ("paper", re.compile(r"paper-(?P<ver>\d+(?:\.\d+)+)-(?P<build>\d+)\.jar", re.IGNORECASE)),
            ("purpur", re.compile(r"purpur-(?P<ver>\d+(?:\.\d+)+)-(?P<build>\d+)\.jar", re.IGNORECASE)),
            ("fabric", re.compile(r"fabric-server-launch\.jar", re.IGNORECASE)),
            ("forge", re.compile(r"forge-(?P<ver>\d+(?:\.\d+)+).*\.jar", re.IGNORECASE)),
            ("neoforge", re.compile(r"neoforge-(?P<ver>\d+(?:\.\d+)+).*\.jar", re.IGNORECASE)),
        ]
        for jf in jar_files:
            lower = jf.name.lower()
            for t, rgx in patterns:
                m = rgx.search(lower)
                if m:
                    stype = stype or t
                    v = m.groupdict().get("ver")
                    if v:
                        sver = sver or v
                    break
            if stype:
                break
        # Fallback vanilla if jar exists and no type detected
        if not stype and (server_dir / "server.jar").exists() and (server_dir / "server.jar").stat().st_size > 50_000:
            stype = "vanilla"
    except Exception:
        pass
    return stype, sver

def _sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None

@router.post("/{server_name}/repair-jar")
def repair_server_jar(server_name: str, current_user: User = Depends(require_moderator)):
    server_dir = SERVERS_ROOT / server_name
    if not server_dir.exists():
        raise HTTPException(status_code=404, detail="Server directory not found")

    jar_path = server_dir / "server.jar"
    before_size = jar_path.stat().st_size if jar_path.exists() else 0
    stype, sver = _detect_type_version(server_dir)
    if not stype or not sver:
        raise HTTPException(status_code=400, detail="Cannot repair: missing detected server type/version")

    try:
        fix_server_jar(server_dir, stype, sver)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Repair attempt failed: {e}")

    if not jar_path.exists() or jar_path.stat().st_size < 100*1024:
        raise HTTPException(status_code=500, detail="Repaired jar still invalid (size below threshold)")

    # Update meta
    meta_path = server_dir / "server_meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            meta = {}
    meta.update({
        "detected_type": stype,
        "detected_version": sver,
        "jar_size_bytes": jar_path.stat().st_size,
        "jar_sha256": _sha256(jar_path),
        "last_repair_ts": int(time.time()),
    })
    try:
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except Exception:
        pass

    return {
        "message": "server.jar repaired",
        "server": server_name,
        "type": stype,
        "version": sver,
        "previous_size": before_size,
        "new_size": jar_path.stat().st_size,
        "sha256": meta.get("jar_sha256"),
    }
