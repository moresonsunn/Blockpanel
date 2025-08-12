import requests
from typing import List
from .providers import register_provider

API_BASE = "https://api.purpurmc.org/v2/purpur"

class PurpurProvider:
    name = "purpur"

    def list_versions(self) -> List[str]:
        resp = requests.get(API_BASE, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        versions = data.get("versions", [])
        return versions

    def get_download_url(self, version: str) -> str:
        # Purpur supports latest build download endpoint
        # Validate version exists
        vresp = requests.get(f"{API_BASE}/{version}", timeout=20)
        if vresp.status_code == 404:
            raise ValueError(f"Unknown Purpur version: {version}")
        return f"{API_BASE}/{version}/latest/download"

# Register on import
register_provider(PurpurProvider())
