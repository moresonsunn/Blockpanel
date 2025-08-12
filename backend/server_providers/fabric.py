import requests
from typing import List
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

    def get_download_url_with_loader(self, version: str, loader_version: str = None) -> str:
        # If loader_version is provided, use it; otherwise get the latest
        if loader_version:
            # Get installer version for the specific loader
            lresp = requests.get(f"{API_BASE}/versions/loader/{version}", timeout=20)
            lresp.raise_for_status()
            loaders = lresp.json()
            # Find the loader entry with the specified version
            loader_entry = None
            for entry in loaders:
                if entry["loader"]["version"] == loader_version:
                    loader_entry = entry
                    break
            if not loader_entry:
                raise ValueError(f"Fabric loader version {loader_version} not available for {version}")
        else:
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

register_provider(FabricProvider())
