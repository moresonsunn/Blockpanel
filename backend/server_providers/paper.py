import requests
from typing import List
from .providers import register_provider

API_BASE = "https://api.papermc.io/v2/projects/paper"

class PaperProvider:
    name = "paper"

    def list_versions(self) -> List[str]:
        resp = requests.get(API_BASE, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return data.get("versions", [])

    def get_download_url(self, version: str) -> str:
        # Get latest build for the version
        vresp = requests.get(f"{API_BASE}/versions/{version}", timeout=20)
        vresp.raise_for_status()
        vdata = vresp.json()
        builds = vdata.get("builds", [])
        if not builds:
            raise ValueError(f"No builds found for Paper version {version}")
        build = builds[-1]
        filename = f"paper-{version}-{build}.jar"
        return f"{API_BASE}/versions/{version}/builds/{build}/downloads/{filename}"

# Register on import
register_provider(PaperProvider())
