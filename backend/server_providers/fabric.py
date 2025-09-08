import requests
from typing import List, Optional, Dict, Any
from .providers import register_provider
import logging

logger = logging.getLogger(__name__)

API_BASE = "https://meta.fabricmc.net/v2"
GAME_VERSIONS_URL = f"{API_BASE}/versions/game"
LOADER_VERSIONS_URL = f"{API_BASE}/versions/loader"
INSTALLER_VERSIONS_URL = f"{API_BASE}/versions/installer"

class FabricProvider:
    """Official Fabric server provider using Fabric Meta API.
    
    Fabric servers use a launcher JAR that downloads the actual server on first run.
    The launcher is obtained from: https://meta.fabricmc.net/v2/versions/loader/{game_version}/{loader_version}/{installer_version}/server/jar
    
    API Documentation: https://fabricmc.net/develop/
    """
    name = "fabric"

    def __init__(self):
        self._cached_versions = None
        self._cached_loaders = {}
        self._cached_installers = None

    def list_versions(self) -> List[str]:
        """Get all stable Minecraft versions supported by Fabric."""
        if self._cached_versions:
            return self._cached_versions
            
        try:
            logger.info("Fetching Fabric game versions from API")
            resp = requests.get(GAME_VERSIONS_URL, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            versions = []
            for version_info in data:
                if version_info.get("stable", False):
                    versions.append(version_info["version"])
            
            self._cached_versions = versions
            logger.info(f"Found {len(versions)} stable Fabric-compatible versions")
            return versions
            
        except Exception as e:
            logger.error(f"Failed to fetch Fabric versions: {e}")
            raise ValueError(f"Could not fetch Fabric versions: {e}")

    def get_loader_versions(self, game_version: str) -> List[Dict[str, Any]]:
        """Get all loader versions compatible with a specific game version."""
        if game_version in self._cached_loaders:
            return self._cached_loaders[game_version]
            
        try:
            logger.info(f"Fetching Fabric loader versions for {game_version}")
            resp = requests.get(f"{LOADER_VERSIONS_URL}/{game_version}", timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            self._cached_loaders[game_version] = data
            logger.info(f"Found {len(data)} loader versions for {game_version}")
            return data
            
        except Exception as e:
            logger.error(f"Failed to fetch Fabric loader versions for {game_version}: {e}")
            raise ValueError(f"Could not fetch Fabric loader versions for {game_version}: {e}")

    def get_installer_versions(self) -> List[Dict[str, Any]]:
        """Get all available installer versions."""
        if self._cached_installers:
            return self._cached_installers
            
        try:
            logger.info("Fetching Fabric installer versions")
            resp = requests.get(INSTALLER_VERSIONS_URL, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            self._cached_installers = data
            logger.info(f"Found {len(data)} installer versions")
            return data
            
        except Exception as e:
            logger.error(f"Failed to fetch Fabric installer versions: {e}")
            raise ValueError(f"Could not fetch Fabric installer versions: {e}")

    def get_latest_loader_version(self, game_version: str) -> str:
        """Get the latest loader version for a game version, preferring stable."""
        loaders = self.get_loader_versions(game_version)
        if not loaders:
            raise ValueError(f"No Fabric loaders available for {game_version}")
        
        # Prefer first stable entry
        for entry in loaders:
            if entry.get("loader", {}).get("stable", False):
                return entry["loader"]["version"]
        # Fallback to the first entry
        return loaders[0]["loader"]["version"]

    def get_latest_installer_version(self) -> str:
        """Get the latest stable installer version."""
        installers = self.get_installer_versions()
        if not installers:
            raise ValueError("No Fabric installers available")
        
        for installer in installers:
            if installer.get("stable", False):
                return installer["version"]
        
        return installers[0]["version"]

    def get_download_url(self, version: str) -> str:
        """Get download URL for Fabric server with latest loader and installer."""
        loader_version = self.get_latest_loader_version(version)
        installer_version = self.get_latest_installer_version()
        
        url = f"{API_BASE}/versions/loader/{version}/{loader_version}/{installer_version}/server/jar"
        logger.info(f"Fabric download URL: {url}")
        return url

    def get_download_url_with_loader(self, version: str, loader_version: Optional[str] = None, installer_version: Optional[str] = None) -> str:
        """Get download URL with specific loader and installer versions.
        
        Args:
            version: Minecraft version
            loader_version: Specific Fabric loader version (latest if None)
            installer_version: Specific installer version (latest stable if None)
        """
        if not loader_version:
            loader_version = self.get_latest_loader_version(version)
        else:
            loaders = self.get_loader_versions(version)
            if not any(l["loader"]["version"] == loader_version for l in loaders):
                raise ValueError(f"Fabric loader {loader_version} not available for Minecraft {version}")
        
        if not installer_version:
            installer_version = self.get_latest_installer_version()
        else:
            installers = self.get_installer_versions()
            if not any(i["version"] == installer_version for i in installers):
                raise ValueError(f"Fabric installer {installer_version} not available")
        
        url = f"{API_BASE}/versions/loader/{version}/{loader_version}/{installer_version}/server/jar"
        logger.info(f"Fabric download URL (custom): {url}")
        return url

    def list_loader_versions(self, game_version: str) -> List[str]:
        """Get list of loader version strings for a specific game version."""
        loaders = self.get_loader_versions(game_version)
        return [loader["loader"]["version"] for loader in loaders]

register_provider(FabricProvider())
