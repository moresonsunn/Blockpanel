import requests
from typing import List
from .providers import register_provider
from .vanilla import VanillaProvider

MAVEN_BASE = "https://maven.neoforged.net/releases/net/neoforged/neoforge"

class NeoForgeProvider:
    name = "neoforge"

    def list_versions(self) -> List[str]:
        return VanillaProvider().list_versions()

    def get_download_url(self, version: str) -> str:
        # NeoForge provides installer artifacts per neoforge version, not strictly per MC version mapping here.
        # Fetch maven metadata and pick latest version that starts with the MC version prefix when available.
        meta_url = f"{MAVEN_BASE}/maven-metadata.xml"
        resp = requests.get(meta_url, timeout=20)
        resp.raise_for_status()
        text = resp.text
        # very rough parse to extract latest versions; for robust parsing consider xml parsing
        candidates = []
        for line in text.splitlines():
            if "<version>" in line:
                v = line.strip().replace("<version>", "").replace("</version>", "")
                if v.startswith(version):
                    candidates.append(v)
        if not candidates:
            # fallback to latest overall
            latest_tag = "<latest>"
            if latest_tag in text:
                latest = text.split(latest_tag)[1].split("</latest>")[0].strip()
                candidates = [latest]
        if not candidates:
            raise ValueError(f"No NeoForge build found for Minecraft {version}")
        chosen = sorted(candidates)[-1]
        return f"{MAVEN_BASE}/{chosen}/neoforge-{chosen}-installer.jar"

register_provider(NeoForgeProvider())
