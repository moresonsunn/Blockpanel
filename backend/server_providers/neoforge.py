import requests
from typing import List, Optional, Dict, Any
from .providers import register_provider
from .vanilla import VanillaProvider
import logging
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# Official NeoForge API endpoints
API_BASE = "https://api.neoforged.net"
VERSIONS_API = f"{API_BASE}/versions"
MAVEN_BASE = "https://maven.neoforged.net/releases/net/neoforged/neoforge"

class NeoForgeProvider:
    """Official NeoForge server provider using NeoForge APIs.
    
    NeoForge servers require an installer that sets up the server environment.
    The installer is obtained from: https://maven.neoforged.net/releases/net/neoforged/neoforge/{neoforge_version}/neoforge-{neoforge_version}-installer.jar
    
    API Documentation: https://api.neoforged.net/
    """
    name = "neoforge"

    def __init__(self):
        self._cached_versions = None
        self._cached_neoforge_versions = None
        self._cached_mc_mappings = {}

    def list_versions(self) -> List[str]:
        """Get all Minecraft versions supported by NeoForge."""
        if self._cached_versions:
            return self._cached_versions
        
        try:
            # Get supported MC versions from NeoForge API
            logger.info("Fetching NeoForge supported versions from API")
            supported_versions = []
            
            # NeoForge typically supports recent versions, let's get from vanilla and filter
            vanilla_versions = VanillaProvider().list_versions()
            neoforge_data = self._get_neoforge_versions()
            
            # Extract supported MC versions from NeoForge data
            mc_versions = set()
            for version_info in neoforge_data:
                mc_version = version_info.get("minecraft_version")
                if mc_version:
                    mc_versions.add(mc_version)
            
            # Filter vanilla versions to only include NeoForge-supported ones
            for version in vanilla_versions:
                if version in mc_versions:
                    supported_versions.append(version)
            
            # Cache and return
            self._cached_versions = supported_versions
            logger.info(f"Found {len(supported_versions)} NeoForge-compatible versions")
            return supported_versions
            
        except Exception as e:
            logger.warning(f"Could not fetch NeoForge versions from API, using fallback: {e}")
            # Fallback: NeoForge generally supports recent versions
            vanilla_versions = VanillaProvider().list_versions()
            # Filter to recent versions (1.20+) as NeoForge is relatively new
            recent_versions = [v for v in vanilla_versions if self._is_recent_version(v)]
            self._cached_versions = recent_versions
            return recent_versions

    def _is_recent_version(self, version: str) -> bool:
        """Check if a Minecraft version is recent enough for NeoForge support."""
        try:
            parts = version.split('.')
            major = int(parts[0])
            minor = int(parts[1])
            
            # NeoForge started around 1.20.1
            return major > 1 or (major == 1 and minor >= 20)
        except:
            return False

    def _get_neoforge_versions(self) -> List[Dict[str, Any]]:
        """Get all NeoForge versions from API."""
        if self._cached_neoforge_versions:
            return self._cached_neoforge_versions
            
        try:
            logger.info("Fetching NeoForge versions from API")
            resp = requests.get(VERSIONS_API, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            # Cache the result
            self._cached_neoforge_versions = data
            logger.info(f"Cached {len(data)} NeoForge versions")
            return data
            
        except Exception as e:
            logger.error(f"Failed to fetch NeoForge versions from API: {e}")
            # Try maven metadata as fallback
            return self._get_versions_from_maven()

    def _get_versions_from_maven(self) -> List[Dict[str, Any]]:
        """Fallback: Get versions from Maven metadata."""
        try:
            logger.info("Fetching NeoForge versions from Maven metadata")
            meta_url = f"{MAVEN_BASE}/maven-metadata.xml"
            resp = requests.get(meta_url, timeout=30)
            resp.raise_for_status()
            
            root = ET.fromstring(resp.text)
            versions = []
            
            for version_elem in root.findall(".//version"):
                version = version_elem.text
                if version:
                    # Try to infer MC version from NeoForge version pattern
                    mc_version = self._infer_mc_version_from_neoforge(version)
                    versions.append({
                        "version": version,
                        "minecraft_version": mc_version,
                    })
            
            logger.info(f"Found {len(versions)} NeoForge versions from Maven")
            return versions
            
        except Exception as e:
            logger.error(f"Failed to fetch versions from Maven: {e}")
            return []

    def _infer_mc_version_from_neoforge(self, neoforge_version: str) -> Optional[str]:
        """Try to infer Minecraft version from NeoForge version."""
        # NeoForge version patterns (this is a heuristic)
        if neoforge_version.startswith("21."):
            return "1.21"
        elif neoforge_version.startswith("47."):
            return "1.20.1"
        elif neoforge_version.startswith("46."):
            return "1.19.4"
        return None

    def get_neoforge_versions_for_minecraft(self, minecraft_version: str) -> List[str]:
        """Get all available NeoForge versions for a specific Minecraft version."""
        if minecraft_version in self._cached_mc_mappings:
            return self._cached_mc_mappings[minecraft_version]
            
        try:
            neoforge_data = self._get_neoforge_versions()
            versions = []
            
            for version_info in neoforge_data:
                if version_info.get("minecraft_version") == minecraft_version:
                    versions.append(version_info["version"])
            
            # Sort versions (newest first)
            versions.sort(key=lambda x: [int(i) for i in x.split('.')], reverse=True)
            
            self._cached_mc_mappings[minecraft_version] = versions
            logger.info(f"Found {len(versions)} NeoForge versions for {minecraft_version}")
            return versions
            
        except Exception as e:
            logger.error(f"Failed to get NeoForge versions for {minecraft_version}: {e}")
            return []

    def get_latest_neoforge_version(self, minecraft_version: str) -> Optional[str]:
        """Get the latest NeoForge version for a Minecraft version."""
        versions = self.get_neoforge_versions_for_minecraft(minecraft_version)
        return versions[0] if versions else None

    def get_download_url(self, version: str) -> str:
        """Get download URL for NeoForge installer with the latest version."""
        neoforge_version = self.get_latest_neoforge_version(version)
        
        if not neoforge_version:
            raise ValueError(f"No NeoForge versions available for Minecraft {version}")
        
        url = f"{MAVEN_BASE}/{neoforge_version}/neoforge-{neoforge_version}-installer.jar"
        logger.info(f"NeoForge download URL: {url}")
        return url

    def get_download_url_with_loader(self, version: str, loader_version: Optional[str] = None, installer_version: Optional[str] = None) -> str:
        """Get download URL with specific NeoForge version.
        
        Args:
            version: Minecraft version
            loader_version: Specific NeoForge version (latest if None)
            installer_version: Ignored for NeoForge (compatibility parameter)
        """
        # For NeoForge, loader_version is the NeoForge version
        if not loader_version:
            neoforge_version = self.get_latest_neoforge_version(version)
            if not neoforge_version:
                raise ValueError(f"No NeoForge versions available for Minecraft {version}")
        else:
            # Validate the NeoForge version exists for this MC version
            available_versions = self.get_neoforge_versions_for_minecraft(version)
            if loader_version not in available_versions:
                raise ValueError(f"NeoForge version {loader_version} not available for Minecraft {version}")
            
            neoforge_version = loader_version
        
        url = f"{MAVEN_BASE}/{neoforge_version}/neoforge-{neoforge_version}-installer.jar"
        logger.info(f"NeoForge download URL (custom): {url}")
        return url

    def list_loader_versions(self, game_version: str) -> List[str]:
        """Get list of NeoForge version strings for a specific Minecraft version."""
        return self.get_neoforge_versions_for_minecraft(game_version)

register_provider(NeoForgeProvider())
