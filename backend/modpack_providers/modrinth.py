from __future__ import annotations
import requests
from typing import Any, Dict, List, Optional
from .base import ModpackProvider, PackSummary, PackDetail, PackVersion

API_BASE = "https://api.modrinth.com/v2"

class ModrinthProvider:
    id = "modrinth"
    name = "Modrinth"

    def search(self, query: str, *, mc_version: Optional[str] = None, loader: Optional[str] = None, limit: int = 24, offset: int = 0) -> List[PackSummary]:
        # Build facets for modpacks
        facets = [["project_type:modpack"]]
        if mc_version:
            facets.append([f"versions:{mc_version}"])
        if loader:
            facets.append([f"categories:{loader.lower()}"])  # modrinth uses categories like 'forge', 'fabric'
        params = {
            "query": query or "",
            "limit": min(max(limit, 1), 100),
            "offset": max(int(offset), 0),
            "facets": str(facets).replace("'", '"'),
        }
        r = requests.get(f"{API_BASE}/search", params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        results: List[PackSummary] = []
        for hit in data.get("hits", []):
            results.append({
                "id": hit.get("project_id") or hit.get("slug"),
                "slug": hit.get("slug"),
                "name": hit.get("title"),
                "description": hit.get("description"),
                "downloads": hit.get("downloads"),
                "updated": hit.get("date_modified"),
                "icon_url": hit.get("icon_url"),
                "categories": hit.get("categories", []),
                "client_side": hit.get("client_side"),
                "server_side": hit.get("server_side"),
                "provider": self.id,
            })
        return results

    def get_pack(self, pack_id: str) -> PackDetail:
        # pack_id can be slug or ID
        r = requests.get(f"{API_BASE}/project/{pack_id}", timeout=10)
        r.raise_for_status()
        p = r.json()
        return {
            "id": p.get("id"),
            "slug": p.get("slug"),
            "name": p.get("title"),
            "description": p.get("description"),
            "icon_url": p.get("icon_url"),
            "categories": p.get("categories", []),
            "loaders": p.get("loaders", []),
            "game_versions": p.get("game_versions", []),
            "provider": self.id,
            "project_type": p.get("project_type"),
        }

    def get_versions(self, pack_id: str, *, limit: int = 50) -> List[PackVersion]:
        r = requests.get(f"{API_BASE}/project/{pack_id}/version", timeout=10)
        r.raise_for_status()
        arr = r.json()
        versions: List[PackVersion] = []
        for v in arr[:limit]:
            versions.append({
                "id": v.get("id"),
                "name": v.get("name"),
                "version_number": v.get("version_number"),
                "game_versions": v.get("game_versions", []),
                "loaders": v.get("loaders", []),
                "date_published": v.get("date_published"),
                "files": v.get("files", []),
            })
        return versions

