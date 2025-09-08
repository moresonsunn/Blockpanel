from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List, Optional
import time

from modpack_providers.modrinth import ModrinthProvider
from modpack_providers.curseforge import CurseForgeProvider
from integrations_store import get_integration_key

router = APIRouter(prefix="/catalog", tags=["catalog"])

# Simple in-memory TTL cache
_CACHE: Dict[str, Dict[str, Any]] = {}
_TTL_SECONDS = 600

# Build providers dynamically so newly saved keys take effect immediately

def get_providers_live() -> Dict[str, Any]:
    prov: Dict[str, Any] = {"modrinth": ModrinthProvider()}
    cf_key = get_integration_key("curseforge")
    if cf_key:
        try:
            prov["curseforge"] = CurseForgeProvider(cf_key)
        except Exception:
            # Ignore bad keys
            pass
    return prov

def _cache_get(key: str):
    entry = _CACHE.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > _TTL_SECONDS:
        _CACHE.pop(key, None)
        return None
    return entry["data"]

def _cache_set(key: str, data: Any):
    _CACHE[key] = {"ts": time.time(), "data": data}

@router.get("/providers")
async def list_providers():
    cf_key = get_integration_key("curseforge")
    items = [{"id": "modrinth", "name": "Modrinth", "configured": True, "requires_key": False}]
    items.append({"id": "curseforge", "name": "CurseForge", "configured": bool(cf_key), "requires_key": True})
    return {"providers": items}

@router.get("/search")
async def search_catalog(
    provider: str = Query("modrinth"),
    q: str = Query(""),
    mc_version: Optional[str] = None,
    loader: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
):
    prov = get_providers_live()
    if provider not in prov:
        raise HTTPException(status_code=400, detail="Provider not configured or unknown")
    offset = (page - 1) * page_size
    key = f"search:{provider}:{q}:{mc_version}:{loader}:{page}:{page_size}"
    cached = _cache_get(key)
    if cached is not None:
        return {"results": cached, "page": page, "page_size": page_size}
    try:
        p = prov[provider]
        results = p.search(q, mc_version=mc_version, loader=loader, limit=page_size, offset=offset)
        _cache_set(key, results)
        return {"results": results, "page": page, "page_size": page_size}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

@router.get("/{provider}/packs/{pack_id}")
async def get_pack(provider: str, pack_id: str):
    prov = get_providers_live()
    if provider not in prov:
        raise HTTPException(status_code=400, detail="Unknown provider")
    key = f"pack:{provider}:{pack_id}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        p = prov[provider]
        data = p.get_pack(pack_id)
        _cache_set(key, data)
        return data
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

@router.get("/{provider}/packs/{pack_id}/versions")
async def get_pack_versions(provider: str, pack_id: str, limit: int = 50):
    prov = get_providers_live()
    if provider not in prov:
        raise HTTPException(status_code=400, detail="Unknown provider")
    key = f"versions:{provider}:{pack_id}:{limit}"
    cached = _cache_get(key)
    if cached is not None:
        return {"versions": cached}
    try:
        p = prov[provider]
        versions = p.get_versions(pack_id, limit=limit)
        _cache_set(key, versions)
        return {"versions": versions}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

