from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any, Dict
from auth import require_admin
from models import User
from integrations_store import get_integration_key, set_integration_key
from integrations_store import STORE_PATH

router = APIRouter(prefix="/integrations", tags=["integrations"])

@router.get("/status")
async def integrations_status():
    return {
        "curseforge": {
            "configured": bool(get_integration_key("curseforge"))
        }
    }

class CurseForgeKey(BaseModel):
    api_key: str

@router.post("/curseforge-key")
async def set_curseforge_key(payload: CurseForgeKey, current_user: User = Depends(require_admin)):
    if not payload.api_key or len(payload.api_key.strip()) < 10:
        raise HTTPException(status_code=400, detail="Invalid API key")
    set_integration_key("curseforge", payload.api_key.strip())
    return {"ok": True}

@router.get("/curseforge-test")
async def test_curseforge_connectivity(current_user: User = Depends(require_admin)):
    """Simple live test of the configured CurseForge API key.
    Makes a small search request and returns status details to help diagnose issues.
    """
    import requests
    key = get_integration_key("curseforge")
    if not key:
        return {"configured": False, "ok": False, "status": 400, "error": "CurseForge API key not configured"}
    url = "https://api.curseforge.com/v1/mods/search"
    params = {"gameId": 432, "classId": 4471, "pageSize": 1, "index": 0, "searchFilter": "all the mods"}
    headers = {"x-api-key": key, "Accept": "application/json", "User-Agent": "minecraft-controller/1.0"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        info = {
            "configured": True,
            "ok": r.ok,
            "status": r.status_code,
        }
        if not r.ok:
            # Try to extract error body and include response headers for diagnostics
            try:
                info["error"] = r.json()
            except Exception:
                info["error_text"] = (r.text or '')[:500]
            try:
                # Include a truncated set of response headers to surface hints (rate limits, messages)
                hdrs = {k: (v if len(v) < 200 else v[:200] + '...') for k, v in r.headers.items()} if r.headers else {}
                info["response_headers"] = hdrs
            except Exception:
                pass
        else:
            try:
                data = r.json().get("data", [])
                info["sample_count"] = len(data)
            except Exception:
                info["sample_count"] = None
        return info
    except Exception as e:
        return {"configured": True, "ok": False, "status": None, "error": str(e)}


@router.get("/curseforge-info")
async def curseforge_info(current_user: User = Depends(require_admin)):
    """Return non-sensitive diagnostics about the stored CurseForge API key and storage path.
    Does NOT return the full key. Helps verify the backend is reading the same store file.
    """
    key = get_integration_key("curseforge")
    configured = bool(key)
    masked = None
    if configured:
        # show only last 4 chars and length
        masked = f"{'*' * max(0, len(key) - 4)}{key[-4:]}"
    try:
        path = str(STORE_PATH)
        exists = STORE_PATH.exists()
    except Exception:
        path = '/data/servers/integrations.json'
        exists = False
    return {"configured": configured, "key_masked": masked, "store_path": path, "store_exists": exists}

