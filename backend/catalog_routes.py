from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List, Optional
import json
import time
from functools import lru_cache
from pathlib import Path

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

_CURATED_PATH = Path(__file__).resolve().parent / "data" / "templates_marketplace.json"

_CURATED_PACK_CACHE: Dict[str, Dict[str, Any]] = {}
_CURATED_PACK_TTL = 1800

@lru_cache(maxsize=1)
def _load_curated_templates() -> List[Dict[str, Any]]:
    try:
        if not _CURATED_PATH.exists():
            log.warning("Curated templates file missing at %s", _CURATED_PATH)
            return []
        raw = _CURATED_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, list):
            cleaned: List[Dict[str, Any]] = []
            for item in data:
                if isinstance(item, dict):
                    cleaned.append(item)
            return cleaned
        log.warning("Curated templates file must contain a list")
        return []
    except Exception as exc:
        log.error("Failed to load curated templates: %s", exc)
        return []


def _validate_curated_pack(
    providers: Dict[str, Any],
    provider_id: str,
    pack_id: str,
    version_id: Optional[str]
) -> Dict[str, Any]:
    key = f"{provider_id}:{pack_id}:{version_id or ''}"
    now = time.time()
    cached = _CURATED_PACK_CACHE.get(key)
    if cached and now - cached["ts"] < _CURATED_PACK_TTL:
        return cached["data"]

    provider = providers.get(provider_id)
    if provider is None:
        result = {
            "status": "provider-unavailable",
            "message": "Provider is not configured or available on this instance."
        }
        _CURATED_PACK_CACHE[key] = {"ts": now, "data": result}
        return result

    try:
        provider.get_pack(pack_id)
    except Exception as exc:  # pragma: no cover - remote error surface
        result = {
            "status": "missing-pack",
            "message": f"Pack '{pack_id}' not found or inaccessible: {exc}"
        }
        _CURATED_PACK_CACHE[key] = {"ts": now, "data": result}
        return result

    resolved_version: Optional[str] = None
    available_versions: List[str] = []
    try:
        versions = provider.get_versions(pack_id, limit=50)
    except Exception as exc:  # pragma: no cover - remote error surface
        versions = []
        log.warning("Failed to fetch versions for %s:%s: %s", provider_id, pack_id, exc)

    for v in versions:
        vid = v.get("id")
        if vid:
            vid_str = str(vid)
            available_versions.append(vid_str)
            if resolved_version is None:
                resolved_version = vid_str
            if version_id and vid_str == str(version_id):
                resolved_version = vid_str

    status = "ok"
    message: Optional[str] = None

    if version_id and str(version_id) not in available_versions:
        if resolved_version:
            status = "latest-used"
            message = "Requested version not available; defaulting to latest release."
        else:
            status = "missing-version"
            message = "Pack has no installable versions right now."

    if not version_id and not resolved_version and available_versions:
        resolved_version = available_versions[0]

    if not available_versions:
        status = "missing-version"
        message = message or "Pack currently exposes no versions."

    result = {
        "status": status,
        "resolved_version": resolved_version,
        "available_versions": available_versions,
        **({"message": message} if message else {}),
    }

    _CURATED_PACK_CACHE[key] = {"ts": now, "data": result}
    return result


def _enrich_curated_templates(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    providers = get_providers_live()
    enriched: List[Dict[str, Any]] = []
    for entry in entries:
        data = dict(entry)
        install_info = dict(entry.get("install") or {})
        provider_id = str(install_info.get("provider") or entry.get("provider") or "modrinth").lower()
        pack_id = install_info.get("pack_id")
        version_id = install_info.get("version_id")

        if not pack_id:
            data["availability"] = "invalid-metadata"
            data["availability_message"] = "Curated template is missing install.pack_id."
            data["provider_configured"] = provider_id in providers
            data["install"] = install_info
            enriched.append(data)
            continue

        validation = _validate_curated_pack(providers, provider_id, str(pack_id), str(version_id) if version_id else None)

        data["availability"] = validation.get("status", "unknown")
        if "message" in validation:
            data["availability_message"] = validation["message"]

        install_info.setdefault("provider", provider_id)
        install_info.setdefault("pack_id", pack_id)

        resolved_version = validation.get("resolved_version")
        if resolved_version:
            install_info["version_id"] = resolved_version
        elif version_id is None:
            install_info["version_id"] = None

        if validation.get("available_versions") is not None:
            data["available_versions"] = validation.get("available_versions")

        data["provider_configured"] = provider_id in providers
        data["install"] = install_info
        enriched.append(data)

    return enriched

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


@router.get("/curated")
async def get_curated_templates(tag: Optional[str] = Query(None, description="Filter by tag")):
    templates = _load_curated_templates()
    if tag:
        normalized = tag.strip().lower()
        filtered = []
        for item in templates:
            tags = item.get("tags")
            if isinstance(tags, list) and any(str(t).lower() == normalized for t in tags if isinstance(t, str)):
                filtered.append(item)
        templates = filtered
    enriched = _enrich_curated_templates(templates)
    return {"templates": enriched, "count": len(enriched)}

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
        def _acronym(s: str) -> str:
            """Compute a simple acronym preserving trailing digits (e.g., 'All the Mods 10' -> 'atm10')."""
            s0 = (s or "").lower()
            s0 = _re.sub(r"[^a-z0-9]+", " ", s0)
            parts = [p for p in s0.split() if p]
            # Gather letters from first char of alphabetic tokens; append any numeric token as-is
            letters = [p[0] for p in parts if p and p[0].isalpha()]
            digits = "".join([p for p in parts if p.isdigit()])
            return ("".join(letters) + digits).strip()
        qn = _norm(q or "")
        qa = _acronym(q or "") if (q or "").strip() else ""
        def score(item: Dict[str, Any]) -> float:
            name = str(item.get("name") or "")
            slug = str(item.get("slug") or "")
            nn = _norm(name)
            ns = _norm(slug)
            an = _acronym(name)
            asg = _acronym(slug)
            s = 0.0
            if qn:
                if nn == qn or ns == qn:
                    s += 10000.0
                elif nn.startswith(qn) or ns.startswith(qn):
                    s += 2500.0
                elif qn in nn or qn in ns:
                    s += 1000.0
            # Acronym-based boosting (helps queries like 'ATM10' or 'AOF5')
            if qa:
                if qa == an or qa == asg:
                    s += 9000.0
                elif an.startswith(qa) or asg.startswith(qa):
                    s += 2200.0
                elif qa in an or qa in asg:
                    s += 800.0
            # Alias boost if this item came from an alias-expanded query
            if item.get("_alias_match"):
                s += 3000.0
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
                    # Acronym alias expansion for popular modpacks (e.g., ATM10 -> All the Mods 10)
                    import re as _re_alias
                    alias_patterns = [
                        (r"^atm(\d+)$", "All the Mods {num}"),
                        (r"^aof(\d+)$", "All of Fabric {num}"),
                    ]
                    q_clean = (q or "").strip().lower()
                    for pat, template in alias_patterns:
                        try:
                            comp = _re_alias.compile(pat)
                            m = comp.match(q_clean)
                        except Exception:
                            m = None
                        if m:
                            num = m.group(1)
                            phrase = template.format(num=num)
                            try:
                                # fetch first page for phrase
                                alias_chunk = cf.search(phrase, mc_version=mc_version, loader=loader, limit=50, offset=0)
                                # Tag alias boost for scoring (lightweight adjustment by inflating downloads temporarily)
                                for it in alias_chunk:
                                    it.setdefault("_alias_match", True)
                                all_results.extend(alias_chunk)
                            except Exception:
                                pass
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
                # Alias expansion for single-provider curseforge searches
                import re as _re_alias2
                alias_patterns = [
                    (r"^atm(\d+)$", "All the Mods {num}"),
                    (r"^aof(\d+)$", "All of Fabric {num}"),
                ]
                q_clean = (q or "").strip().lower()
                for pat, template in alias_patterns:
                    try:
                        comp = _re_alias2.compile(pat)
                        m = comp.match(q_clean)
                    except Exception:
                        m = None
                    if m:
                        num = m.group(1)
                        phrase = template.format(num=num)
                        try:
                            alias_chunk = p.search(phrase, mc_version=mc_version, loader=loader, limit=50, offset=0)
                            for it in alias_chunk:
                                it.setdefault("_alias_match", True)
                            acc.extend(alias_chunk)
                        except Exception:
                            pass
                # If a query is provided, try to pull additional pages until we include an exact normalized match
                # so it can be ranked onto earlier pages. Cap the extra pages to protect performance.
                if (q or "").strip():
                    import re as _re
                    def _norm(s: str) -> str:
                        s0 = (s or "").lower()
                        s0 = _re.sub(r"[^a-z0-9]+", " ", s0)
                        return " ".join(s0.split())
                    def _acronym(s: str) -> str:
                        s0 = (s or "").lower()
                        s0 = _re.sub(r"[^a-z0-9]+", " ", s0)
                        parts = [p for p in s0.split() if p]
                        letters = [p[0] for p in parts if p and p[0].isalpha()]
                        digits = "".join([p for p in parts if p.isdigit()])
                        return ("".join(letters) + digits).strip()
                    qn = _norm(q)
                    qa = _acronym(q)
                    def _has_exact(items: List[Dict[str, Any]]) -> bool:
                        for it in items:
                            if _norm(str(it.get("name") or "")) == qn or _norm(str(it.get("slug") or "")) == qn:
                                return True
                            # Treat acronym match as exact for prefetch purposes
                            if qa and (_acronym(str(it.get("name") or "")) == qa or _acronym(str(it.get("slug") or "")) == qa):
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

