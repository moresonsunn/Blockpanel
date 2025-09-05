import requests
from typing import List
from .providers import register_provider
from .vanilla import VanillaProvider

# NeoForge API for version info
API_BASE = "https://api.neoforged.net/api/versions_info"
MAVEN_BASE = "https://maven.neoforged.net/releases/net/neoforged/neoforge"

class NeoForgeProvider:
    name = "neoforge"

    def list_versions(self) -> List[str]:
        return VanillaProvider().list_versions()

    def get_download_url(self, version: str) -> str:
        # First try to use the API to get the latest NeoForge version for this MC version
        try:
            resp = requests.get(API_BASE, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            
            # Look for NeoForge versions that support this MC version
            neoforge_version = None
            if "versions" in data:
                for nf_ver, info in data["versions"].items():
                    if info.get("mc_version") == version:
                        neoforge_version = nf_ver
                        break
            
            if not neoforge_version:
                # Fallback to maven metadata parsing
                meta_url = f"{MAVEN_BASE}/maven-metadata.xml"
                resp = requests.get(meta_url, timeout=20)
                resp.raise_for_status()
                text = resp.text
                
                candidates = []
                for line in text.splitlines():
                    if "<version>" in line:
                        v = line.strip().replace("<version>", "").replace("</version>", "")
                        # NeoForge version format is like 21.0.167 for MC 1.21
                        if version == "1.21" and v.startswith("21."):
                            candidates.append(v)
                        elif version == "1.20.1" and v.startswith("47."):
                            candidates.append(v)
                        elif version == "1.19.4" and v.startswith("47."):
                            candidates.append(v)
                
                if not candidates:
                    # Get latest version as fallback
                    if "<latest>" in text:
                        latest = text.split("<latest>")[1].split("</latest>")[0].strip()
                        candidates = [latest]
                
                if not candidates:
                    raise ValueError(f"No NeoForge build found for Minecraft {version}")
                    
                neoforge_version = sorted(candidates, key=lambda x: list(map(int, x.split('.'))))[-1]
            
            return f"{MAVEN_BASE}/{neoforge_version}/neoforge-{neoforge_version}-installer.jar"
            
        except Exception as e:
            # Final fallback - try maven metadata directly
            try:
                meta_url = f"{MAVEN_BASE}/maven-metadata.xml"
                resp = requests.get(meta_url, timeout=20)
                resp.raise_for_status()
                text = resp.text
                
                if "<latest>" in text:
                    latest = text.split("<latest>")[1].split("</latest>")[0].strip()
                    return f"{MAVEN_BASE}/{latest}/neoforge-{latest}-installer.jar"
                    
                raise ValueError(f"No NeoForge build found for Minecraft {version}: {e}")
            except Exception:
                raise ValueError(f"Failed to get NeoForge download URL for Minecraft {version}: {e}")

register_provider(NeoForgeProvider())
