import requests
from typing import List
from .providers import register_provider

VERSION_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"

class VanillaProvider:
    name = "vanilla"

    def _manifest(self):
        resp = requests.get(VERSION_MANIFEST, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def list_versions(self) -> List[str]:
        data = self._manifest()
        return [v["id"] for v in data.get("versions", [])]

    def get_download_url(self, version: str) -> str:
        data = self._manifest()
        versions = {v["id"]: v for v in data.get("versions", [])}
        if version not in versions:
            raise ValueError(f"Unknown vanilla version: {version}")
        version_meta_url = versions[version]["url"]
        vresp = requests.get(version_meta_url, timeout=20)
        vresp.raise_for_status()
        vdata = vresp.json()
        server_info = vdata.get("downloads", {}).get("server")
        if not server_info or not server_info.get("url"):
            raise ValueError(f"No server jar for vanilla version: {version}")
        return server_info["url"]

# Register on import
register_provider(VanillaProvider())
