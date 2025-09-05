import requests
from typing import List, Optional
from .providers import register_provider

# Fabric meta API
# Game versions: https://meta.fabricmc.net/v2/versions/game
# Loader by version: https://meta.fabricmc.net/v2/versions/loader/{game_version}
# Server launcher: https://meta.fabricmc.net/v2/versions/loader/{game_version}/{loader_version}/{installer_version}/server/jar

API_BASE = "https://meta.fabricmc.net/v2"

class FabricProvider:
    name = "fabric"

    def list_versions(self) -> List[str]:
        resp = requests.get(f"{API_BASE}/versions/game", timeout=20)
        resp.raise_for_status()
        data = resp.json()
        # Filter release and stable entries only
        return [v["version"] for v in data if v.get("stable")]

    def get_download_url(self, version: str) -> str:
        # Get latest loader for the game version
        lresp = requests.get(f"{API_BASE}/versions/loader/{version}", timeout=20)
        lresp.raise_for_status()
        loaders = lresp.json()
        # Find the first loader entry (usually sorted newest first)
        if not loaders:
            raise ValueError(f"No Fabric loader available for {version}")
        loader_entry = loaders[0]
        loader_version = loader_entry["loader"]["version"]
        
        # Get stable installer version
        iresp = requests.get(f"{API_BASE}/versions/installer", timeout=20)
        iresp.raise_for_status()
        installers = iresp.json()
        # Find the stable installer
        stable_installer = None
        for installer in installers:
            if installer.get("stable"):
                stable_installer = installer
                break
        if not stable_installer:
            raise ValueError(f"No stable Fabric installer available")
        installer_version = stable_installer["version"]
        
        # Compose the download URL using loader version and stable installer version
        return f"{API_BASE}/versions/loader/{version}/{loader_version}/{installer_version}/server/jar"

    def get_download_url_with_loader(self, version: str, loader_version: Optional[str] = None, installer_version: Optional[str] = None) -> str:
        """Return the Fabric server jar URL using explicit loader and optionally installer version.
        If loader_version is None, choose the latest for the game version.
        If installer_version is None, choose the latest stable installer.
        """
        # Resolve loader version if not provided
        if loader_version:
            # Validate loader exists for this game version
            lresp = requests.get(f"{API_BASE}/versions/loader/{version}", timeout=20)
            lresp.raise_for_status()
            loaders = lresp.json()
            if not any(entry.get("loader", {}).get("version") == loader_version for entry in loaders):
                raise ValueError(f"Fabric loader {loader_version} not available for {version}")
        else:
            # Get latest loader for the game version
            lresp = requests.get(f"{API_BASE}/versions/loader/{version}", timeout=20)
            lresp.raise_for_status()
            loaders = lresp.json()
            if not loaders:
                raise ValueError(f"No Fabric loader available for {version}")
            loader_version = loaders[0]["loader"]["version"]
        
        # Resolve installer version if not provided
        if installer_version:
            # Optionally validate the installer exists
            try:
                iresp = requests.get(f"{API_BASE}/versions/installer", timeout=20)
                iresp.raise_for_status()
                installers = [i.get("version") for i in iresp.json()]
                if installer_version not in installers:
                    # If not found, still allow as meta endpoint might still accept it
                    pass
            except Exception:
                # Best-effort validation only
                pass
        else:
            iresp = requests.get(f"{API_BASE}/versions/installer", timeout=20)
            iresp.raise_for_status()
            installers = iresp.json()
            stable_installer = next((i for i in installers if i.get("stable")), None)
            if not stable_installer:
                raise ValueError("No stable Fabric installer available")
            installer_version = stable_installer["version"]
        
        # Compose the exact download URL
        return f"{API_BASE}/versions/loader/{version}/{loader_version}/{installer_version}/server/jar"

register_provider(FabricProvider())
