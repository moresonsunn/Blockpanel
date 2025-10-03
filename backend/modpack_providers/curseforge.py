from __future__ import annotations
import requests
import os
import re
import logging
from typing import Any, Dict, List, Optional, cast
from .base import PackSummary, PackDetail, PackVersion

CURSE_API_BASE = "https://api.curseforge.com/v1"
GAME_ID_MINECRAFT = 432
CLASS_ID_MODPACKS = 4471

log = logging.getLogger(__name__)

def _norm(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', (s or '')).strip().lower()

def _extra_patterns() -> List[str]:
    raw = os.getenv("CLIENT_ONLY_MOD_PATTERNS", "")
    return [p.strip().lower() for p in raw.split(",") if p.strip()]

def _has_client_gameversion(cf_file: Dict[str, Any]) -> bool:
    """
    Prefer explicit CurseForge metadata: some files list 'Client' / 'Server'
    in gameVersions. Treat files with Client and not Server as client-only.
    """
    try:
        versions = [v.lower() for v in (cf_file.get("gameVersions") or [])]
        return "client" in versions and "server" not in versions
    except Exception:
        return False

def _collect_names(cf_file: Dict[str, Any], project: Dict[str, Any] | None) -> str:
    names = [
        cf_file.get("fileName"),
        cf_file.get("displayName"),
    ]
    if project:
        names += [project.get("name"), project.get("slug")]
    return _norm(" ".join([n for n in names if n]))

def is_client_only_cf(cf_file: Dict[str, Any], project: Dict[str, Any] | None = None) -> bool:
    """
    Decide if a CurseForge file is client-only without hardcoded patterns:
    - Use explicit metadata (gameVersions includes Client but not Server).
    - Optionally respect externally-supplied patterns via CLIENT_ONLY_MOD_PATTERNS.
    """
    # 1) explicit metadata
    if _has_client_gameversion(cf_file):
        return True

    # 2) optional external patterns (no built-in patterns)
    extras = _extra_patterns()
    if extras:
        joined = _collect_names(cf_file, project)
        if any(pat in joined for pat in extras):
            return True
        # check dependency hints (required only)
        try:
            for dep in cf_file.get("dependencies") or []:
                if dep.get("relationType") == 3:  # RequiredDependency
                    dep_name = _norm(dep.get("modName") or dep.get("slug") or "")
                    if dep_name and any(pat in dep_name for pat in extras):
                        return True
        except Exception:
            pass

    return False

class CurseForgeProvider:
    id = "curseforge"
    name = "CurseForge"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("CurseForge API key is required")
        self.api_key = api_key

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "minecraft-controller/1.0 (+https://localhost)"
        }

    def search(self, query: str, *, mc_version: Optional[str] = None, loader: Optional[str] = None, limit: int = 24, offset: int = 0) -> List[PackSummary]:
        page_size = min(max(limit, 1), 50)
        # CurseForge's 'index' is the zero-based ITEM OFFSET, not page number
        item_offset = max(int(offset or 0), 0)
        params: Dict[str, Any] = {
            "gameId": GAME_ID_MINECRAFT,
            "classId": CLASS_ID_MODPACKS,
            "pageSize": page_size,
            "index": item_offset,
        }
        if query:
            params["searchFilter"] = query
        # CurseForge supports gameVersion and modLoaderType filters
        if mc_version:
            params["gameVersion"] = mc_version
        if loader:
            # Best-effort mapping; subject to change
            ml_map = {"forge": 1, "fabric": 4, "neoforge": 6}
            mlt = ml_map.get(loader.lower())
            if mlt:
                params["modLoaderType"] = mlt
        r = requests.get(f"{CURSE_API_BASE}/mods/search", headers=self._headers(), params=params, timeout=15)
        r.raise_for_status()
        arr = r.json().get("data", [])
        out: List[PackSummary] = []
        ql = (query or "").strip().lower()

        def _has_source_link(mod: Dict[str, Any]) -> bool:
            links = mod.get("links") or {}
            src = links.get("sourceUrl") or links.get("sourceURL") or links.get("source")
            if not isinstance(src, str) or not src:
                return False
            try:
                from urllib.parse import urlparse
                host = (urlparse(src).netloc or '').lower()
                return any(h in host for h in ("github.com", "gitlab.com", "bitbucket.org", "codeberg.org"))
            except Exception:
                return False

        for m in arr:
            out.append(cast(PackSummary, {
                "id": m.get("id"),
                "slug": m.get("slug"),
                "name": m.get("name"),
                "description": m.get("summary"),
                "downloads": m.get("downloadCount"),
                "updated": m.get("dateModified"),
                "icon_url": (m.get("logo") or {}).get("url"),
                "categories": [c.get("name") for c in (m.get("categories") or [])],
                "provider": self.id,
                "source_url": (m.get("links") or {}).get("sourceUrl") or (m.get("links") or {}).get("sourceURL") or (m.get("links") or {}).get("source"),
            }))

        # Sort locally so exact matches float to top; then by downloads
        if ql:
            out.sort(key=lambda x: (
                3 if (str(x.get("name") or "").lower() == ql or str(x.get("slug") or "").lower() == ql) else 
                2 if (str(x.get("name") or "").lower().startswith(ql) or str(x.get("slug") or "").lower().startswith(ql)) else 
                1 if (ql in str(x.get("name") or "").lower() or ql in str(x.get("slug") or "").lower()) else 0,
                float(x.get("downloads") or 0)
            ), reverse=True)
        return out

    def get_pack(self, pack_id: str) -> PackDetail:
        r = requests.get(f"{CURSE_API_BASE}/mods/{pack_id}", headers=self._headers(), timeout=15)
        r.raise_for_status()
        m = r.json().get("data") or {}
        return cast(PackDetail, {
            "id": m.get("id"),
            "slug": m.get("slug"),
            "name": m.get("name"),
            "description": m.get("summary"),
            "icon_url": (m.get("logo") or {}).get("url"),
            "categories": [c.get("name") for c in (m.get("categories") or [])],
            "provider": self.id,
            "source_url": (m.get("links") or {}).get("sourceUrl") or (m.get("links") or {}).get("sourceURL") or (m.get("links") or {}).get("source"),
        })

    def get_versions(self, pack_id: str, *, limit: int = 50) -> List[PackVersion]:
        # Files endpoint
        r = requests.get(f"{CURSE_API_BASE}/mods/{pack_id}/files", headers=self._headers(), timeout=15)
        r.raise_for_status()
        arr = r.json().get("data", [])
        out: List[PackVersion] = []
        for f in arr[:limit]:
            file_id = f.get("id")
            file_name = f.get("fileName")
            dl_url = f.get("downloadUrl")
            # Prefer server pack if available
            spid = f.get("serverPackFileId") or f.get("serverPackFileID")
            files_list: List[Dict[str, Any]] = []
            if spid:
                try:
                    fr = requests.get(f"{CURSE_API_BASE}/mods/files/{spid}", headers=self._headers(), timeout=15)
                    if fr.ok:
                        fd = fr.json().get("data") or {}
                        sp_name = fd.get("fileName") or f"server-pack-{spid}.zip"
                        sp_url = fd.get("downloadUrl")
                        if sp_url:
                            files_list.append({"filename": sp_name, "url": sp_url, "primary": True})
                except Exception:
                    pass
            # Fallback to the regular file
            if not files_list:
                files_list.append({"filename": file_name, "url": dl_url, "primary": True})

            out.append(cast(PackVersion, {
                "id": file_id,
                "name": f.get("displayName"),
                "version_number": file_name,
                "game_versions": f.get("gameVersions", []),
                "date_published": f.get("fileDate"),
                "files": files_list,
            }))
        return out

    def _filter_client_only(self, files: list[dict]) -> list[dict]:
        """Filter out client-only files before download."""
        filtered = []
        for f in files:
            try:
                proj = f.get("__project__") if isinstance(f, dict) else None
                if is_client_only_cf(f, proj):
                    log.info("Skipping client-only CF file %s", f.get("displayName") or f.get("fileName"))
                    continue
            except Exception as e:
                log.warning("Client-only check failed for CF file %s: %s", f.get("fileName"), e)
            filtered.append(f)
        return filtered

    def expand_manifest_files(self, manifest: dict) -> list[dict]:
        """
        Given a CF manifest.json, resolve to concrete file objects to download.
        Apply client-only filtering before returning.
        """
        # ...existing code that fills resolved_files with file JSONs...
        resolved_files = []  # placeholder to show context
        # ...existing code...

        resolved_files = self._filter_client_only(resolved_files)
        return resolved_files

