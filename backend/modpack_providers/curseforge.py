from __future__ import annotations
import requests
from typing import Any, Dict, List, Optional
from .base import PackSummary, PackDetail, PackVersion

CURSE_API_BASE = "https://api.curseforge.com/v1"
GAME_ID_MINECRAFT = 432
CLASS_ID_MODPACKS = 4471

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
        params = {
            "gameId": GAME_ID_MINECRAFT,
            "classId": CLASS_ID_MODPACKS,
            "pageSize": min(max(limit, 1), 50),
            "index": max(int(offset), 0),
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
        for m in arr:
            out.append({
                "id": m.get("id"),
                "slug": m.get("slug"),
                "name": m.get("name"),
                "description": m.get("summary"),
                "downloads": m.get("downloadCount"),
                "updated": m.get("dateModified"),
                "icon_url": (m.get("logo") or {}).get("url"),
                "categories": [c.get("name") for c in (m.get("categories") or [])],
                "provider": self.id,
            })
        return out

    def get_pack(self, pack_id: str) -> PackDetail:
        r = requests.get(f"{CURSE_API_BASE}/mods/{pack_id}", headers=self._headers(), timeout=15)
        r.raise_for_status()
        m = r.json().get("data") or {}
        return {
            "id": m.get("id"),
            "slug": m.get("slug"),
            "name": m.get("name"),
            "description": m.get("summary"),
            "icon_url": (m.get("logo") or {}).get("url"),
            "categories": [c.get("name") for c in (m.get("categories") or [])],
            "provider": self.id,
        }

    def get_versions(self, pack_id: str, *, limit: int = 50) -> List[PackVersion]:
        # Files endpoint
        r = requests.get(f"{CURSE_API_BASE}/mods/{pack_id}/files", headers=self._headers(), timeout=15)
        r.raise_for_status()
        arr = r.json().get("data", [])
        out: List[PackVersion] = []
        for f in arr[:limit]:
            out.append({
                "id": f.get("id"),
                "name": f.get("displayName"),
                "version_number": f.get("fileName"),
                "game_versions": f.get("gameVersions", []),
                "date_published": f.get("fileDate"),
                "files": [{"filename": f.get("fileName"), "url": f.get("downloadUrl"), "primary": True}],
            })
        return out

