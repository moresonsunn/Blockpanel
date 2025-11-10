from fastapi import APIRouter, HTTPException, Depends
from typing import List
from pathlib import Path
import json, time, datetime
from auth import require_moderator
from models import User
from config import SERVERS_ROOT

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.post("/backfill-timestamps")
def backfill_timestamps(current_user: User = Depends(require_moderator)):
    """Scan server directories and populate created_ts/created_iso when missing.

    Uses directory mtime as a reasonable proxy when metadata is absent.
    """
    scanned = 0
    updated = 0
    errors: List[str] = []
    now = int(time.time())
    try:
        for child in SERVERS_ROOT.iterdir():
            try:
                if not child.is_dir():
                    continue
                scanned += 1
                meta_path = child / "server_meta.json"
                meta = {}
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8") or "{}")
                    except Exception:
                        meta = {}
                if "created_ts" not in meta:
                    try:
                        st = child.stat()
                        ts = int(st.st_mtime)
                    except Exception:
                        ts = now
                    meta["created_ts"] = ts
                    try:
                        meta["created_iso"] = datetime.datetime.utcfromtimestamp(ts).isoformat() + "Z"
                    except Exception:
                        pass
                    try:
                        meta.setdefault("name", child.name)
                        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
                        updated += 1
                    except Exception as werr:
                        errors.append(f"Failed to write meta for {child.name}: {werr}")
            except Exception as derr:
                errors.append(f"Error processing {child.name}: {derr}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {e}")
    return {"scanned": scanned, "updated": updated, "errors": errors[:50]}
