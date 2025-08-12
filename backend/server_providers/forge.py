import requests
from typing import List
from .providers import register_provider
from .vanilla import VanillaProvider

PROMOTIONS_URL = "https://maven.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
MAVEN_BASE = "https://maven.minecraftforge.net/net/minecraftforge/forge"

class ForgeProvider:
    name = "forge"

    def list_versions(self) -> List[str]:
        return VanillaProvider().list_versions()

    def get_download_url(self, version: str) -> str:
        resp = requests.get(PROMOTIONS_URL, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        promos = data.get("promos", {})
        forge_version = promos.get(f"{version}-recommended") or promos.get(f"{version}-latest")
        if not forge_version:
            raise ValueError(f"No Forge build found for Minecraft {version}")
        path = f"{version}-{forge_version}"
        filename = f"forge-{version}-{forge_version}-installer.jar"
        return f"{MAVEN_BASE}/{path}/{filename}"

register_provider(ForgeProvider())
