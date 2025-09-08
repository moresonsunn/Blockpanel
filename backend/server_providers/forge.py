import requests
from typing import List, Optional, Dict, Any
from .providers import register_provider
from .vanilla import VanillaProvider
import logging
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# Official MinecraftForge API endpoints
PROMOTIONS_URL = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
MAVEN_BASE = "https://maven.minecraftforge.net/net/minecraftforge/forge"
FORGE_FILES_API = "https://files.minecraftforge.net/net/minecraftforge/forge"

class ForgeProvider:
    """Official MinecraftForge server provider using Forge APIs.
    
    Forge servers require an installer that sets up the server environment.
    The installer is obtained from: https://maven.minecraftforge.net/net/minecraftforge/forge/{maven_coord}/forge-{maven_coord}-installer.jar
    Where maven_coord is usually "{mc_version}-{forge_version}", but for legacy versions (e.g., 1.7.10)
    it is "{mc_version}-{forge_version}-{mc_version}".
    
    API Documentation: https://files.minecraftforge.net/
    """
    name = "forge"

    def __init__(self):
        self._cached_versions = None
        self._cached_promotions = None
        self._cached_forge_versions = {}

    def list_versions(self) -> List[str]:
        """Get all Minecraft versions supported by Forge."""
        if self._cached_versions:
            return self._cached_versions
        
        # Use vanilla versions as base, but filter for Forge compatibility
        vanilla_versions = VanillaProvider().list_versions()
        
        # Get promotions to see which versions have Forge builds
        try:
            promotions = self._get_promotions()
            supported_versions = []
            
            for version in vanilla_versions:
                # Check if this version has recommended or latest forge builds
                if f"{version}-recommended" in promotions or f"{version}-latest" in promotions:
                    supported_versions.append(version)
            
            # Cache and return
            self._cached_versions = supported_versions
            logger.info(f"Found {len(supported_versions)} Forge-compatible versions")
            return supported_versions
            
        except Exception as e:
            logger.warning(f"Could not filter Forge versions, using vanilla list: {e}")
            return vanilla_versions

    def _get_promotions(self) -> Dict[str, Any]:
        """Get the promotions data (recommended/latest versions)."""
        if self._cached_promotions:
            return self._cached_promotions
            
        try:
            logger.info("Fetching Forge promotions from API")
            resp = requests.get(PROMOTIONS_URL, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            promotions = data.get("promos", {})
            self._cached_promotions = promotions
            logger.info(f"Cached {len(promotions)} Forge promotions")
            return promotions
            
        except Exception as e:
            logger.error(f"Failed to fetch Forge promotions: {e}")
            raise ValueError(f"Could not fetch Forge promotions: {e}")

    def get_forge_versions_for_minecraft(self, minecraft_version: str) -> List[str]:
        """Get all available Forge versions for a specific Minecraft version."""
        if minecraft_version in self._cached_forge_versions:
            return self._cached_forge_versions[minecraft_version]
            
        try:
            # Try to get version list from Files API
            logger.info(f"Fetching Forge versions for {minecraft_version}")
            versions_url = f"{FORGE_FILES_API}/index_{minecraft_version}.html"
            
            resp = requests.get(versions_url, timeout=30)
            if resp.status_code == 404:
                # This Minecraft version doesn't have Forge support
                self._cached_forge_versions[minecraft_version] = []
                return []
                
            resp.raise_for_status()
            
            # Parse HTML to extract version numbers
            # This is a fallback method as the Files site doesn't have a clean API
            import re
            forge_versions = []
            
            # Look for version patterns in the HTML
            version_pattern = rf'{re.escape(minecraft_version)}-(\d+\.\d+\.\d+(?:\.\d+)?)'
            matches = re.findall(version_pattern, resp.text)
            
            forge_versions = list(set(matches))  # Remove duplicates
            forge_versions.sort(key=lambda x: [int(i) for i in x.split('.')], reverse=True)  # Sort by version
            
            self._cached_forge_versions[minecraft_version] = forge_versions
            logger.info(f"Found {len(forge_versions)} Forge versions for {minecraft_version}")
            return forge_versions
            
        except Exception as e:
            logger.error(f"Failed to fetch Forge versions for {minecraft_version}: {e}")
            # Return empty list rather than failing
            self._cached_forge_versions[minecraft_version] = []
            return []

    def get_recommended_forge_version(self, minecraft_version: str) -> Optional[str]:
        """Get the recommended Forge version for a Minecraft version."""
        promotions = self._get_promotions()
        return promotions.get(f"{minecraft_version}-recommended")

    def get_latest_forge_version(self, minecraft_version: str) -> Optional[str]:
        """Get the latest Forge version for a Minecraft version."""
        promotions = self._get_promotions()
        return promotions.get(f"{minecraft_version}-latest")

    def get_best_forge_version(self, minecraft_version: str) -> str:
        """Get the best available Forge version (recommended > latest > newest available)."""
        # Try recommended first
        recommended = self.get_recommended_forge_version(minecraft_version)
        if recommended:
            return recommended
            
        # Try latest
        latest = self.get_latest_forge_version(minecraft_version)
        if latest:
            return latest
            
        # Try getting from version list
        versions = self.get_forge_versions_for_minecraft(minecraft_version)
        if versions:
            return versions[0]  # First one should be newest
            
        raise ValueError(f"No Forge versions available for Minecraft {minecraft_version}")

    def _resolve_installer_url(self, mc_version: str, forge_version: str) -> str:
        """
        Build a working installer URL by trying known coordinate patterns and fallbacks.
        Patterns tried in order:
          1) {mc}-{forge}
          2) {mc}-{forge}-{mc}  (legacy coordinates like 1.7.10)
        For each, try -installer.jar, then fallback to -universal.jar if installer is missing.
        """
        import requests
        candidates = []
        # pattern 1
        coord1 = f"{mc_version}-{forge_version}"
        candidates.append(f"{MAVEN_BASE}/{coord1}/forge-{coord1}-installer.jar")
        candidates.append(f"{MAVEN_BASE}/{coord1}/forge-{coord1}-universal.jar")
        # pattern 2 (legacy)
        coord2 = f"{mc_version}-{forge_version}-{mc_version}"
        candidates.append(f"{MAVEN_BASE}/{coord2}/forge-{coord2}-installer.jar")
        candidates.append(f"{MAVEN_BASE}/{coord2}/forge-{coord2}-universal.jar")
        
        last_err = None
        for url in candidates:
            try:
                r = requests.head(url, timeout=20)
                if r.status_code == 200:
                    return url
            except Exception as e:
                last_err = e
                continue
        if last_err:
            raise ValueError(f"No valid Forge installer/universal found for {mc_version} {forge_version}: {last_err}")
        raise ValueError(f"No valid Forge installer/universal found for {mc_version} {forge_version}")

    def get_download_url(self, version: str) -> str:
        """Get download URL for Forge installer with the best available version."""
        forge_version = self.get_best_forge_version(version)
        url = self._resolve_installer_url(version, forge_version)
        logger.info(f"Forge download URL: {url}")
        return url

    def get_download_url_with_loader(self, version: str, loader_version: Optional[str] = None, installer_version: Optional[str] = None) -> str:
        """Get download URL with specific Forge version.
        
        Args:
            version: Minecraft version
            loader_version: Specific Forge version (best available if None)
            installer_version: Ignored for Forge (compatibility parameter)
        """
        # For Forge, loader_version is the Forge version
        if not loader_version:
            forge_version = self.get_best_forge_version(version)
        else:
            # Validate the Forge version exists
            available_versions = self.get_forge_versions_for_minecraft(version)
            if loader_version not in available_versions:
                # Try promotions as fallback
                promotions = self._get_promotions()
                recommended = promotions.get(f"{version}-recommended")
                latest = promotions.get(f"{version}-latest")
                
                if loader_version not in [recommended, latest]:
                    raise ValueError(f"Forge version {loader_version} not available for Minecraft {version}")
            
            forge_version = loader_version
        
        url = self._resolve_installer_url(version, forge_version)
        logger.info(f"Forge download URL (custom): {url}")
        return url

    def list_loader_versions(self, game_version: str) -> List[str]:
        """Get list of Forge version strings for a specific Minecraft version."""
        return self.get_forge_versions_for_minecraft(game_version)

register_provider(ForgeProvider())
