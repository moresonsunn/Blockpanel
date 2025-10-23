from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List, Optional
import time

import logging
from modpack_providers.modrinth import ModrinthProvider
from modpack_providers.curseforge import CurseForgeProvider
from integrations_store import get_integration_key

log = logging.getLogger(__name__)

# Track provider instantiation errors so the UI can surface diagnostics
_PROVIDER_ERRORS: Dict[str, str] = {}

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
            # Clear any previous error
            _PROVIDER_ERRORS.pop("curseforge", None)
        except Exception as e:
            # Record the error so list_providers can show diagnostics
            log.exception("Failed to instantiate CurseForgeProvider")
            _PROVIDER_ERRORS["curseforge"] = str(e)
    else:
        # No key configured: clear any previous error
        _PROVIDER_ERRORS.pop("curseforge", None)
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
    items = [
        {"id": "all", "name": "All", "configured": True, "requires_key": False},
        {"id": "modrinth", "name": "Modrinth", "configured": True, "requires_key": False},
        {"id": "curseforge", "name": "CurseForge", "configured": bool(cf_key), "requires_key": True, "error": _PROVIDER_ERRORS.get("curseforge")},
    ]
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
    if provider != "all" and provider not in prov:
        raise HTTPException(status_code=400, detail="Provider not configured or unknown")
    offset = (page - 1) * page_size
    key = f"search:{provider}:{q}:{mc_version}:{loader}:{page}:{page_size}"
    cached = _cache_get(key)
    if cached is not None:
        return {"results": cached, "page": page, "page_size": page_size}
    try:
        # Helper: rank results by relevance (normalized), popularity, recency
        import datetime as _dt, re as _re
        def _norm(s: str) -> str:
            s0 = (s or "").lower()
            s0 = _re.sub(r"[^a-z0-9]+", " ", s0)
            return " ".join(s0.split())
        qn = _norm(q or "")
        def score(item: Dict[str, Any]) -> float:
            name = str(item.get("name") or "")
            slug = str(item.get("slug") or "")
            nn = _norm(name)
            ns = _norm(slug)
            s = 0.0
            if qn:
                if nn == qn or ns == qn:
                    s += 10000.0
                elif nn.startswith(qn) or ns.startswith(qn):
                    s += 2500.0
                elif qn in nn or qn in ns:
                    s += 1000.0
            dl = float(item.get("downloads") or 0)
            s += min(dl / 1000.0, 1000.0)
            upd = item.get("updated")
            try:
                if isinstance(upd, str) and upd:
                    dt = _dt.datetime.fromisoformat(upd.replace("Z", "+00:00"))
                    age_days = max((_dt.datetime.now(_dt.timezone.utc) - dt).days, 0)
                    s += max(0.0, 365.0 - float(age_days))
            except Exception:
                pass
            return s

        if provider == "all":
            # Fetch enough items from both providers to cover the requested page,
            # then merge, dedupe, rank, and slice [offset:offset+page_size].
            desired = offset + page_size
            mr = prov.get("modrinth")
            cf = prov.get("curseforge")
            all_results: List[Dict[str, Any]] = []
            # Modrinth: single call, larger limit up to 100
            if mr:
                try:
                    mr_limit = min(desired, 100)
                    all_results.extend(mr.search(q, mc_version=mc_version, loader=loader, limit=mr_limit, offset=0))
                except Exception:
                    pass
            # CurseForge: accumulate multiple pages of 50 results until we have 'desired'
            if cf:
                try:
                    per_page = 50
                    pages = max(1, (desired + per_page - 1) // per_page)
                    for i in range(pages):
                        cf_off = i * per_page
                        chunk = cf.search(q, mc_version=mc_version, loader=loader, limit=per_page, offset=cf_off)
                        if not chunk:
                            break
                        all_results.extend(chunk)
                except Exception:
                    pass
            # Deduplicate by provider+id
            seen = set()
            deduped: List[Dict[str, Any]] = []
            for it in all_results:
                key2 = f"{it.get('provider')}:{it.get('id') or it.get('slug')}"
                if key2 in seen:
                    continue
                seen.add(key2)
                deduped.append(it)
            # Rank and then slice for the requested page
            deduped.sort(key=score, reverse=True)
            results = deduped[offset:offset + page_size]
        else:
            p = prov[provider]
            if provider == "curseforge":
                # Accumulate enough results from the top to rank globally, then slice.
                desired = offset + page_size
                per_page = 50
                pages = max(1, (desired + per_page - 1) // per_page)
                acc: List[Dict[str, Any]] = []
                for i in range(pages):
                    cf_off = i * per_page
                    try:
                        chunk = p.search(q, mc_version=mc_version, loader=loader, limit=per_page, offset=cf_off)
                        if not chunk:
                            break
                        acc.extend(chunk)
                    except Exception:
                        break
                # If a query is provided, try to pull additional pages until we include an exact normalized match
                # so it can be ranked onto earlier pages. Cap the extra pages to protect performance.
                if (q or "").strip():
                    import re as _re
                    def _norm(s: str) -> str:
                        s0 = (s or "").lower()
                        s0 = _re.sub(r"[^a-z0-9]+", " ", s0)
                        return " ".join(s0.split())
                    qn = _norm(q)
                    def _has_exact(items: List[Dict[str, Any]]) -> bool:
                        for it in items:
                            if _norm(str(it.get("name") or "")) == qn or _norm(str(it.get("slug") or "")) == qn:
                                return True
                        return False
                    if not _has_exact(acc):
                        seen_keys = {f"{it.get('provider')}:{it.get('id') or it.get('slug')}" for it in acc}
                        extra_cap = 8  # up to 8 more pages (400 items)
                        i = pages
                        while i < pages + extra_cap:
                            cf_off = i * per_page
                            try:
                                chunk = p.search(q, mc_version=mc_version, loader=loader, limit=per_page, offset=cf_off)
                            except Exception:
                                break
                            if not chunk:
                                break
                            added_any = False
                            for it in chunk:
                                key2 = f"{it.get('provider')}:{it.get('id') or it.get('slug')}"
                                if key2 not in seen_keys:
                                    acc.append(it)
                                    seen_keys.add(key2)
                                    added_any = True
                            if not added_any:
                                break
                            if _has_exact(acc):
                                break
                            i += 1
                # Deduplicate by provider+id (or slug fallback) before ranking
                seen_keys = set()
                dedup_acc: List[Dict[str, Any]] = []
                for it in acc:
                    k2 = f"{it.get('provider')}:{it.get('id') or it.get('slug')}"
                    if k2 in seen_keys:
                        continue
                    seen_keys.add(k2)
                    dedup_acc.append(it)
                dedup_acc.sort(key=score, reverse=True)
                results = dedup_acc[offset:offset + page_size]
            else:
                # Modrinth: fetch a larger slice then slice
                desired = min(offset + page_size, 100)
                raw = p.search(q, mc_version=mc_version, loader=loader, limit=desired, offset=0)
                raw.sort(key=score, reverse=True)
                results = raw[offset:offset + page_size]
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

