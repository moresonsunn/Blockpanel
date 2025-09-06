import os
import re
import shlex
import docker
from pathlib import Path
from typing import Optional, List, Dict
from config import SERVERS_ROOT, SERVERS_HOST_ROOT, SERVERS_VOLUME_NAME
from download_manager import prepare_server_files
import time
import logging
from mcrcon import MCRcon

import requests  # For direct jar download fallback

logger = logging.getLogger(__name__)

MINECRAFT_LABEL = "minecraft_server_manager"
RUNTIME_IMAGE = "mc-runtime:latest"
MINECRAFT_PORT = 25565

# --- Helper functions for direct jar download fallback ---

def download_file(url: str, dest: Path, min_size: int = 1024 * 100, max_retries: int = 3):
    """
    Download a file from a URL to a destination path.
    Ensures the file is at least min_size bytes (default 100KB).
    Retries up to max_retries times.
    Performs basic validation for JAR content (content-type and ZIP magic).
    """
    for attempt in range(max_retries):
        try:
            logger.info(f"Downloading {url} to {dest} (attempt {attempt+1})")
            with requests.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                content_type = r.headers.get("content-type", "").lower()
                
                # Read the first few bytes to check if it's a valid file
                first_chunk = next(r.iter_content(chunk_size=8192), b'')
                r.close()  # Close the first request
                
                # Check for valid file signatures
                is_jar = first_chunk.startswith(b'PK')  # ZIP/JAR signature
                is_gzip = first_chunk.startswith(b'\x1f\x8b')  # GZIP signature
                
                # Only reject if we're sure it's not a valid file
                if not is_jar and not is_gzip and ("text/html" in content_type or ("application/json" in content_type and len(first_chunk) > 0 and not first_chunk.startswith(b'{') and not first_chunk.startswith(b'['))): 
                    logger.warning(
                        f"Invalid file type for JAR download: {content_type}. First bytes: {first_chunk[:50]!r}"
                    )
                    raise ValueError(f"Invalid file type for JAR download: {content_type}")
                
                # Re-open the request for actual download
                with requests.get(url, stream=True, timeout=30) as r2:
                    r2.raise_for_status()
                    with open(dest, "wb") as f:
                        for chunk in r2.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
            if dest.exists() and dest.stat().st_size >= min_size:
                # Validate ZIP/JAR magic 'PK\x03\x04'
                try:
                    with open(dest, "rb") as f:
                        magic = f.read(4)
                    if magic[:2] != b"PK":
                        raise ValueError(f"Downloaded file does not appear to be a JAR (missing PK header): {magic!r}")
                except Exception as magic_err:
                    logger.warning(f"Validation failed for downloaded file {dest}: {magic_err}")
                    # Remove invalid file and retry
                    try:
                        dest.unlink()
                    except Exception:
                        pass
                    time.sleep(2)
                    continue
                logger.info(f"Downloaded {url} successfully ({dest.stat().st_size} bytes)")
                return True
            else:
                logger.warning(f"Downloaded file {dest} is too small or missing after download.")
        except Exception as e:
            logger.warning(f"Failed to download {url} to {dest}: {e}")
        # Remove incomplete file
        if dest.exists():
            try:
                dest.unlink()
            except Exception:
                pass
        time.sleep(2)
    return False

def get_paper_download_url(version: str) -> Optional[str]:
    # PaperMC API: https://papermc.io/api/v2/projects/paper
    try:
        resp = requests.get(f"https://api.papermc.io/v2/projects/paper/versions/{version}", timeout=10)
        resp.raise_for_status()
        builds = resp.json().get("builds", [])
        if not builds:
            return None
        latest_build = builds[-1]
        jar_name = f"paper-{version}-{latest_build}.jar"
        url = f"https://api.papermc.io/v2/projects/paper/versions/{version}/builds/{latest_build}/downloads/{jar_name}"
        return url
    except Exception as e:
        logger.warning(f"Failed to get PaperMC download url for {version}: {e}")
        return None

def get_purpur_download_url(version: str) -> Optional[str]:
    # Purpur API: https://api.purpurmc.org/v2/purpur
    try:
        resp = requests.get(f"https://api.purpurmc.org/v2/purpur/{version}", timeout=10)
        resp.raise_for_status()
        builds = resp.json().get("builds", [])
        if not builds:
            return None
        latest_build = builds[-1]
        url = f"https://api.purpurmc.org/v2/purpur/{version}/{latest_build}/download"
        return url
    except Exception as e:
        logger.warning(f"Failed to get Purpur download url for {version}: {e}")
        return None

def get_fabric_download_url(version: str, loader_version: Optional[str] = None) -> Optional[str]:
    # Fabric installer: https://meta.fabricmc.net/v2/versions/loader/<mc_version>
    # If loader_version is provided, use it to select the loader version.
    try:
        # Prefer "stable" alias for installer to avoid hard-coding installer versions
        installer_token = "stable"

        if loader_version:
            # Directly compose the server JAR URL; this endpoint returns a binary JAR, not JSON
            return f"https://meta.fabricmc.net/v2/versions/loader/{version}/{loader_version}/{installer_token}/server/jar"
        else:
            # Get latest loader for the game version
            lresp = requests.get(f"https://meta.fabricmc.net/v2/versions/loader/{version}", timeout=10)
            lresp.raise_for_status()
            loaders = lresp.json()
            if not loaders:
                logger.warning(f"No Fabric loader available for {version}")
                return None
            loader_entry = loaders[0]
            resolved_loader_version = loader_entry["loader"]["version"]

            # Compose the download URL using loader version and stable installer alias
            return f"https://meta.fabricmc.net/v2/versions/loader/{version}/{resolved_loader_version}/{installer_token}/server/jar"
    except Exception as e:
        logger.warning(f"Failed to get Fabric download url for {version} (loader {loader_version}): {e}")
        return None

def get_forge_download_url(version: str) -> Optional[str]:
    # Forge: https://files.minecraftforge.net/net/minecraftforge/forge/
    # Use https://maven.minecraftforge.net/net/minecraftforge/forge/<mc_version>-<forge_version>/forge-<mc_version>-<forge_version>-installer.jar
    # But for server, we want the universal/server jar, which is not always available via API.
    # We'll try to get the recommended installer, then extract/unpack it.
    # For now, fallback to using the installer jar.
    try:
        # Get latest forge version for this MC version
        resp = requests.get(f"https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json", timeout=10)
        resp.raise_for_status()
        promos = resp.json().get("promos", {})
        key = f"{version}-latest"
        forge_version = promos.get(key)
        if not forge_version:
            # Try recommended
            key = f"{version}-recommended"
            forge_version = promos.get(key)
        if not forge_version:
            return None
        # Compose URL
        url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{version}-{forge_version}/forge-{version}-{forge_version}-installer.jar"
        return url
    except Exception as e:
        logger.warning(f"Failed to get Forge download url for {version}: {e}")
        return None

def get_neoforge_download_url(version: str) -> Optional[str]:
    # NeoForge: https://maven.neoforged.net/releases/net/neoforged/neoforge/
    # No public API, so we try to guess the latest version
    try:
        # Try to get the latest version from the maven metadata
        meta_url = f"https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
        resp = requests.get(meta_url, timeout=10)
        resp.raise_for_status()
        # Parse XML for latest version for this MC version
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.text)
        versions = [v.text for v in root.findall(".//version")]
        # Find a version that starts with the MC version
        for v in reversed(versions):
            if v.startswith(version):
                # Compose jar url
                url = f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{v}/neoforge-{v}-installer.jar"
                return url
        return None
    except Exception as e:
        logger.warning(f"Failed to get NeoForge download url for {version}: {e}")
        return None

def fix_server_jar(server_dir: Path, server_type: str, version: str, loader_version: Optional[str] = None):
    """
    Ensures the correct server.jar is present and valid for the given server type.
    If not, attempts to download it directly from the official sources.
    Supports loader_version for Fabric.
    """
    jar_path = server_dir / "server.jar"
    min_jar_size = 1024 * 100  # 100KB minimum for a valid jar

    # If the jar does not exist or is too small, try to fix it
    if not jar_path.exists() or jar_path.stat().st_size < min_jar_size:
        logger.warning(f"{server_type} server.jar missing or too small in {server_dir}, attempting to re-download.")

        # Remove the bad/corrupt jar if it exists
        if jar_path.exists():
            try:
                jar_path.unlink()
            except Exception as e:
                logger.error(f"Could not remove corrupt server.jar: {e}")

        url = None
        if server_type.lower() == "paper":
            url = get_paper_download_url(version)
        elif server_type.lower() == "purpur":
            url = get_purpur_download_url(version)
        elif server_type.lower() == "fabric":
            url = get_fabric_download_url(version, loader_version=loader_version)
        elif server_type.lower() == "forge":
            url = get_forge_download_url(version)
        elif server_type.lower() == "neoforge":
            url = get_neoforge_download_url(version)

        if url:
            success = download_file(url, jar_path, min_size=min_jar_size)
            if not success:
                raise RuntimeError(f"Failed to download a valid {server_type} server.jar for {server_dir} from {url}.")
        else:
            # Fallback: try to re-prepare the server files using the download_manager
            try:
                # Try to pass loader_version if possible
                prepare_server_files(server_type, version, server_dir, loader_version=loader_version)
            except TypeError:
                # Fallback to old signature
                prepare_server_files(server_type, version, server_dir)
            # Check again
            if not jar_path.exists() or jar_path.stat().st_size < min_jar_size:
                raise RuntimeError(
                    f"Failed to download a valid {server_type} server.jar for {server_dir}. Please check your network or {server_type} version."
                )

class DockerManager:
    def __init__(self):
        self.client = self._init_client()

    def _init_client(self) -> docker.DockerClient:
        docker_host = os.environ.get("DOCKER_HOST")
        if docker_host:
            return docker.DockerClient(base_url=docker_host)
        try:
            return docker.from_env()
        except Exception:
            pass
        fallback_hosts = [
            "host.docker.internal",
            "gateway.docker.internal",
            "docker.for.win.localhost",
        ]
        last_exc = None
        for host in fallback_hosts:
            try:
                return docker.DockerClient(base_url=f"tcp://{host}:2375")
            except Exception as exc:
                last_exc = exc
        raise RuntimeError(
            "Cannot connect to Docker. Enable Docker Desktop TCP on 2375 and set DOCKER_HOST=tcp://host.docker.internal:2375, or mount //./pipe/docker_engine."
        ) from last_exc

    def list_servers(self):
        try:
            containers = self.client.containers.list(all=True, filters={"label": MINECRAFT_LABEL})
            result = []
            for c in containers:
                try:
                    attrs = c.attrs or {}
                    config = attrs.get("Config", {})
                    network = attrs.get("NetworkSettings", {})
                    # Extract server type and version from labels if present
                    labels = getattr(c, "labels", {})
                    server_type = labels.get("mc.type", None)
                    server_version = labels.get("mc.version", None)
                    # Optionally, extract loader version if present
                    loader_version = labels.get("mc.loader_version", None)
                    
                    # Extract actual host port mappings
                    port_mappings = {}
                    raw_ports = network.get("Ports", {})
                    for container_port, host_bindings in raw_ports.items():
                        if host_bindings and isinstance(host_bindings, list) and len(host_bindings) > 0:
                            # Take the first IPv4 binding (0.0.0.0)
                            for binding in host_bindings:
                                if binding.get("HostIp") == "0.0.0.0":
                                    port_mappings[container_port] = {
                                        "host_port": binding.get("HostPort"),
                                        "host_ip": binding.get("HostIp")
                                    }
                                    break
                            # Fallback to first binding if no 0.0.0.0 found
                            if container_port not in port_mappings:
                                port_mappings[container_port] = {
                                    "host_port": host_bindings[0].get("HostPort"),
                                    "host_ip": host_bindings[0].get("HostIp")
                                }
                        else:
                            port_mappings[container_port] = None
                    
                    result.append({
                        "id": c.id,
                        "name": c.name,
                        "status": getattr(c, "status", "unknown"),
                        "image": config.get("Image"),
                        "labels": labels,
                        "ports": raw_ports,  # Keep raw ports for backward compatibility
                        "port_mappings": port_mappings,  # New field with actual host port mappings
                        "mounts": attrs.get("Mounts", []),
                        "server_type": server_type,
                        "server_version": server_version,
                        "loader_version": loader_version,
                    })
                except docker.errors.NotFound:
                    logger.warning(f"Container {c.id} not found when listing servers, skipping")
                    continue
                except Exception as e:
                    logger.warning(f"Error processing container {c.id}: {e}")
                    continue
            return result
        except Exception as e:
            logger.error(f"Error listing servers: {e}")
            return []

    def get_server_type_and_version(self, container_id: str) -> dict:
        """
        Returns the server type and version for a given container.
        """
        try:
            container = self.client.containers.get(container_id)
            labels = getattr(container, "labels", {})
            server_type = labels.get("mc.type", None)
            server_version = labels.get("mc.version", None)
            loader_version = labels.get("mc.loader_version", None)
            return {
                "id": container.id,
                "server_type": server_type,
                "server_version": server_version,
                "loader_version": loader_version,
            }
        except docker.errors.NotFound:
            logger.warning(f"Container {container_id} not found when getting server type/version")
            return {
                "id": container_id,
                "error": "Container not found.",
                "server_type": None,
                "server_version": None,
                "loader_version": None,
            }
        except Exception as e:
            logger.error(f"Error getting server type/version for container {container_id}: {e}")
            return {
                "id": container_id,
                "error": str(e),
                "server_type": None,
                "server_version": None,
                "loader_version": None,
            }

    def get_server_info(self, container_id: str) -> dict:
        """
        Returns comprehensive server information for a given container.
        """
        try:
            container = self.client.containers.get(container_id)
            attrs = container.attrs or {}
            config = attrs.get("Config", {})
            network = attrs.get("NetworkSettings", {})
            labels = getattr(container, "labels", {})
            
            # Get server stats if container is running
            stats = None
            if container.status == "running":
                try:
                    stats = self.get_server_stats(container_id)
                except Exception as e:
                    logger.warning(f"Could not get stats for container {container_id}: {e}")
            
            # Get Java version from environment variables or labels
            env_vars = config.get("Env", [])
            java_version = "21"  # Default
            java_bin = "/usr/local/bin/java21"  # Default
            
            for env_var in env_vars:
                if env_var.startswith("JAVA_VERSION="):
                    java_version = env_var.split("=", 1)[1]
                elif env_var.startswith("JAVA_BIN="):
                    java_bin = env_var.split("=", 1)[1]
            
            # Override with label if present
            if "mc.java_version" in labels:
                java_version = labels["mc.java_version"]
                java_bin = f"/usr/local/bin/java{java_version}"
            
            # Extract actual host port mappings
            port_mappings = {}
            raw_ports = network.get("Ports", {})
            for container_port, host_bindings in raw_ports.items():
                if host_bindings and isinstance(host_bindings, list) and len(host_bindings) > 0:
                    # Take the first IPv4 binding (0.0.0.0)
                    for binding in host_bindings:
                        if binding.get("HostIp") == "0.0.0.0":
                            port_mappings[container_port] = {
                                "host_port": binding.get("HostPort"),
                                "host_ip": binding.get("HostIp")
                            }
                            break
                    # Fallback to first binding if no 0.0.0.0 found
                    if container_port not in port_mappings:
                        port_mappings[container_port] = {
                            "host_port": host_bindings[0].get("HostPort"),
                            "host_ip": host_bindings[0].get("HostIp")
                        }
                else:
                    port_mappings[container_port] = None
            
            return {
                "id": container.id,
                "name": container.name,
                "status": getattr(container, "status", "unknown"),
                "image": config.get("Image"),
                "labels": labels,
                "ports": raw_ports,
                "port_mappings": port_mappings,
                "mounts": attrs.get("Mounts", []),
                "server_type": labels.get("mc.type", None),
                "server_version": labels.get("mc.version", None),
                "loader_version": labels.get("mc.loader_version", None),
                "java_version": java_version,
                "java_bin": java_bin,
                "stats": stats,
                "created": attrs.get("Created", None),
                "state": attrs.get("State", {}),
            }
        except docker.errors.NotFound:
            logger.warning(f"Container {container_id} not found when getting server info")
            return {
                "id": container_id,
                "error": "Container not found.",
                "status": "not_found",
            }
        except Exception as e:
            logger.error(f"Error getting server info for container {container_id}: {e}")
            return {
                "id": container_id,
                "error": str(e),
                "status": "error",
            }

    def list_available_server_types_and_versions(self) -> dict:
        """
        Returns a dictionary of available server types and their versions.
        """
        # Fallback implementation: not available due to missing import
        logger.warning("list_available_server_types_and_versions: Not implemented because get_available_server_types_and_versions is not available.")
        return {"error": "Not implemented: get_available_server_types_and_versions is not available."}

    def _ensure_runtime_image(self) -> None:
        try:
            image = self.client.images.get(RUNTIME_IMAGE)
            logger.info(f"Runtime image {RUNTIME_IMAGE} found: {image.id}")
        except docker.errors.ImageNotFound as exc:
            logger.error(f"Runtime image '{RUNTIME_IMAGE}' not found")
            raise RuntimeError(
                "Runtime image '{}' not found. Build it with: docker build -t {} -f docker/runtime.Dockerfile docker".format(
                    RUNTIME_IMAGE, RUNTIME_IMAGE
                )
            ) from exc
        except Exception as e:
            logger.error(f"Error checking runtime image: {e}")
            raise RuntimeError(f"Error checking runtime image: {e}")

    def _get_bind_volume(self, server_dir: Path) -> dict:
        if SERVERS_HOST_ROOT:
            host_path = Path(SERVERS_HOST_ROOT) / server_dir.name
            return {str(host_path): {"bind": "/data", "mode": "rw"}}
        # Mount the entire servers volume to /data/servers, then the container will look for /data/servers/server_name/
        return {SERVERS_VOLUME_NAME: {"bind": "/data/servers", "mode": "rw"}}

    def _fix_fabric_server_jar(self, server_dir: Path, server_type: str, version: str, loader_version: Optional[str] = None):
        """
        For Fabric servers, ensure that the correct jar file is present and not corrupt.
        If a corrupt or zero-byte server.jar is found, try to re-download or fix it.
        """
        # Deprecated: replaced by fix_server_jar for all types
        fix_server_jar(server_dir, server_type, version, loader_version=loader_version)

    def _get_java_version(self, container) -> Optional[str]:
        """
        Runs 'java -version' inside the container and returns the Java version string.
        Returns None if Java is not found or error occurs.
        """
        try:
            # First check if the container still exists and is running
            container.reload()
            if container.status != "running":
                logger.warning(f"Container {container.id} is not running (status: {container.status})")
                return None
                
            exit_code, output = container.exec_run("java -version", stderr=True, stdout=False)
            if exit_code != 0:
                return None
            # java -version outputs to stderr in most cases, so:
            # we need to grab stderr
            output_bytes = container.exec_run("java -version", stderr=True, stdout=False)[1]
            output_text = output_bytes.decode(errors="ignore")
            # Example output lines:
            # openjdk version "17.0.4" 2022-07-19
            # openjdk version "1.8.0_292"
            # We extract version numbers using regex:
            match = re.search(r'version "(.*?)"', output_text)
            if match:
                return match.group(1)
            return None
        except docker.errors.NotFound:
            logger.warning(f"Container {container.id} not found when trying to get Java version")
            return None
        except docker.errors.APIError as e:
            logger.warning(f"Docker API error getting Java version from container {container.id}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Could not get Java version from container {container.id}: {e}")
            return None

    def _is_java_version_compatible(self, java_version: str, server_type: str, server_version: str) -> bool:
        """
        Checks if the detected Java version is compatible with the server type/version.
        Here you can define rules per server type.

        Example:
          - Fabric 1.19+ requires Java 17+
          - Forge 1.12 requires Java 8
          - Purple servers might have different requirements

        For demonstration, simple rules are implemented.
        """
        try:
            # Extract major version as int (handle '1.8.0_292' and '17.0.4' style)
            if java_version.startswith("1."):
                major = int(java_version.split('.')[1])
            else:
                major = int(java_version.split('.')[0])

            server_type = server_type.lower()
            if server_type == "fabric":
                # Assume Fabric 1.19+ requires Java 17+
                # For demo: if version >= 1.19, require Java 17+
                if server_version.startswith("1.19") or server_version > "1.18":
                    return major >= 17
                # Older Fabric can run on Java 8+
                return major >= 8

            elif server_type == "forge":
                # Forge 1.12 requires Java 8, newer might require Java 17+
                if server_version.startswith("1.12"):
                    return major >= 8
                else:
                    return major >= 17  # newer versions require Java 17

            elif server_type == "purple":
                # Just assume Java 17+ for Purple servers
                return major >= 17

            elif server_type == "neoforge":
                # NeoForge generally requires Java 17+
                return major >= 17

            elif server_type == "paper":
                # Paper 1.18+ requires Java 17+
                if server_version.startswith("1.18") or server_version > "1.17":
                    return major >= 17
                return major >= 8

            # Default allow Java 8+
            return major >= 8
        except Exception as e:
            logger.warning(f"Error checking Java version compatibility: {e}")
            # On error, assume incompatible
            return False

    def create_server(self, name, server_type, version, host_port=None, loader_version=None, min_ram="1G", max_ram="2G", installer_version=None):
        self._ensure_runtime_image()
        server_dir: Path = SERVERS_ROOT / name
        server_dir.mkdir(parents=True, exist_ok=True)
        
        # Try to prepare server files first
        try:
            prepare_server_files(server_type, version, server_dir, loader_version=loader_version, installer_version=installer_version)
            
            # For installer-based servers (forge/neoforge), don't check for server.jar yet
            # It will be created when the installer runs inside the container
            if server_type.lower() in ("forge", "neoforge"):
                logger.info(f"Server files prepared successfully for {server_type} (installer downloaded)")
            else:
                # Check if server.jar was created successfully for direct-download servers
                jar_path = server_dir / "server.jar"
                if jar_path.exists() and jar_path.stat().st_size >= 1024 * 100:  # At least 100KB
                    logger.info(f"Server files prepared successfully, server.jar found at {jar_path}")
                else:
                    logger.warning(f"Server.jar not found or too small after prepare_server_files, attempting fix")
                    fix_server_jar(server_dir, server_type, version, loader_version=loader_version)
        except Exception as e:
            logger.warning(f"prepare_server_files failed: {e}, attempting fix_server_jar")
            # Only run fix_server_jar for non-installer servers when there's an error
            if server_type.lower() not in ("forge", "neoforge"):
                fix_server_jar(server_dir, server_type, version, loader_version=loader_version)
            else:
                # For installer-based servers, re-raise the exception since fix_server_jar won't help
                raise

    def create_server_from_existing(self, name: str, host_port: int | None = None, min_ram: str = "1G", max_ram: str = "2G") -> dict:
        """Create a container for an existing server directory under /data/servers/{name} using the runtime image.
        Does not attempt to download any files; assumes files (including server.jar or installers) already exist.
        """
        self._ensure_runtime_image()
        server_dir: Path = SERVERS_ROOT / name
        if not server_dir.exists() or not server_dir.is_dir():
            raise RuntimeError(f"Server directory {server_dir} does not exist")

        port_binding = {}
        if host_port:
            port_binding[f"{MINECRAFT_PORT}/tcp"] = host_port
        else:
            port_binding[f"{MINECRAFT_PORT}/tcp"] = None

        env_vars = {
            "SERVER_DIR_NAME": name,
            "MIN_RAM": min_ram,
            "MAX_RAM": max_ram,
        }
        labels = {
            MINECRAFT_LABEL: "true",
            "mc.type": "custom",
        }
        try:
            container = self.client.containers.run(
                RUNTIME_IMAGE,
                name=name,
                labels=labels,
                environment=env_vars,
                ports=port_binding,
                volumes=self._get_bind_volume(server_dir),
                detach=True,
                tty=True,
                stdin_open=True,
                working_dir="/data",
            )
            logger.info(f"Container {container.id} created from existing dir for server {name}")
            return {"id": container.id, "name": container.name, "status": container.status}
        except Exception as e:
            logger.error(f"Failed to create container from existing dir for {name}: {e}")
            raise RuntimeError(f"Failed to create Docker container for server {name}: {e}")

        # Configure port binding
        port_binding = {}
        if host_port:
            port_binding[f"{MINECRAFT_PORT}/tcp"] = host_port
        else:
            # Let Docker assign a random port
            port_binding[f"{MINECRAFT_PORT}/tcp"] = None

        # Configure environment variables
        env_vars = {
            "SERVER_DIR_NAME": name,
            "MIN_RAM": min_ram,
            "MAX_RAM": max_ram,
            "SERVER_PORT": str(MINECRAFT_PORT),
            "SERVER_TYPE": server_type,
            "SERVER_VERSION": version
        }
        
        # Add loader_version to labels if present
        labels = {
            MINECRAFT_LABEL: "true",
            "mc.type": server_type,
            "mc.version": version,
        }
        if loader_version is not None:
            labels["mc.loader_version"] = loader_version

        # Convert RAM strings to bytes for Docker memory limit
        def ram_to_bytes(ram_str):
            if isinstance(ram_str, int):
                return ram_str * 1024 * 1024  # Assume MB
            if ram_str.upper().endswith('G'):
                return int(ram_str[:-1]) * 1024 * 1024 * 1024
            elif ram_str.upper().endswith('M'):
                return int(ram_str[:-1]) * 1024 * 1024
            else:
                return int(ram_str) * 1024 * 1024  # Assume MB
        
        # Set Docker memory limit to MAX_RAM
        memory_limit = ram_to_bytes(max_ram)
        
        try:
            container = self.client.containers.run(
                RUNTIME_IMAGE,
                name=name,
                labels=labels,
                environment=env_vars,
                ports=port_binding,
                volumes=self._get_bind_volume(server_dir),
                detach=True,
                tty=True,
                stdin_open=True,
                working_dir="/data",
                mem_limit=memory_limit,
            )
            logger.info(f"Container {container.id} created successfully for server {name}")
        except Exception as e:
            logger.error(f"Failed to create container for server {name}: {e}")
            raise RuntimeError(f"Failed to create Docker container for server {name}: {e}")

        # After starting container, check Java version compatibility (optional)
        java_version = self._get_java_version(container)
        if java_version is None:
            logger.warning(f"Could not determine Java version in container for server {name}. Server will continue but may have compatibility issues.")
        elif not self._is_java_version_compatible(java_version, server_type, version):
            logger.warning(f"Incompatible Java version {java_version} detected for server type {server_type} {version}. Server will continue but may have issues.")
        else:
            logger.info(f"Java version {java_version} is compatible with {server_type} {version}")

        return {"id": container.id, "name": container.name, "status": container.status}

    def start_server(self, container_id):
        container = self.client.containers.get(container_id)
        container.start()
        return {"id": container.id, "status": container.status}

    def stop_server(self, container_id):
        container = self.client.containers.get(container_id)
        container.stop()
        return {"id": container.id, "status": container.status}

    def restart_server(self, container_id):
        container = self.client.containers.get(container_id)
        container.restart()
        return {"id": container.id, "status": container.status}

    def kill_server(self, container_id):
        container = self.client.containers.get(container_id)
        container.kill()
        return {"id": container.id, "status": container.status}

    def delete_server(self, container_id):
        container = self.client.containers.get(container_id)
        container.remove(force=True)
        return {"id": container_id, "deleted": True}

    def get_server_logs(self, container_id, tail: int = 200):
        container = self.client.containers.get(container_id)
        logs = container.logs(tail=tail).decode(errors="ignore")
        return {"id": container.id, "logs": logs}

    def send_command(self, container_id: str, command: str) -> dict:
        """
        Sendet einen Befehl an den Minecraft-Server im Container.
        Versucht zuerst RCON, dann attach_socket, dann stdin-Fallback.
        """
        container = self.client.containers.get(container_id)

        try:
            # --- 1️⃣ RCON versuchen ---
            env_vars = container.attrs.get("Config", {}).get("Env", [])
            env_dict = dict(var.split("=", 1) for var in env_vars if "=" in var)

            rcon_enabled = env_dict.get("ENABLE_RCON", "false").lower() == "true"
            rcon_password = env_dict.get("RCON_PASSWORD", "")

            # Host & Port aus Port-Mapping ermitteln
            network_settings = container.attrs.get("NetworkSettings", {}).get("Ports", {})
            rcon_port = None
            rcon_host = "localhost"
            for port, mappings in (network_settings or {}).items():
                if port.endswith("/tcp") and mappings:
                    for mapping in mappings:
                        if "HostPort" in mapping and mapping["HostPort"].isdigit():
                            # RCON-Standardport oder ENV-Match
                            if port.startswith("25575") or str(env_dict.get("RCON_PORT", "25575")) in port:
                                rcon_port = int(mapping["HostPort"])

            if rcon_enabled and rcon_password and rcon_port:
                try:
                    with MCRcon(rcon_host, rcon_password, port=rcon_port) as mcr:
                        response = mcr.command(command)
                        return {"exit_code": 0, "output": response, "method": "rcon", "rcon_port": rcon_port}
                except Exception as rcon_err:
                    logger.warning(f"RCON fehlgeschlagen für Container {container_id}: {rcon_err}")

            # --- 2️⃣ attach_socket versuchen ---
            try:
                sock = container.attach_socket(params={
                    "stdin": True,
                    "stdout": True,
                    "stderr": True,
                    "stream": True
                })
                sock._sock.setblocking(True)

                # In der Konsole von MC kein "/" nötig
                cmd_with_newline = command.lstrip("/").strip() + "\n"
                sock._sock.send(cmd_with_newline.encode("utf-8"))

                time.sleep(0.2)
                try:
                    output = sock._sock.recv(4096).decode(errors="ignore")
                except Exception:
                    output = ""

                sock.close()
                return {"exit_code": 0, "output": output.strip(), "method": "attach_socket"}
            except Exception as attach_err:
                logger.warning(f"attach_socket fehlgeschlagen für Container {container_id}: {attach_err}")

            # --- 3️⃣ STDIN-Fallback ---
            safe_command = command.rstrip('\n') + '\n'
            exec_cmd = [
                "sh", "-c",
                f'echo {shlex.quote(safe_command)} > /proc/1/fd/0'
            ]
            exit_code, output = container.exec_run(exec_cmd)
            if exit_code == 0:
                return {"exit_code": exit_code, "output": f"Command sent via stdin: {command}", "method": "stdin"}

            # --- 4️⃣ Java-PID-Fallback ---
            exec_cmd_find_java = [
                "sh", "-c",
                "ps -eo pid,comm | grep java | awk '{print $1}' | head -n 1"
            ]
            exit_code_java, output_java = container.exec_run(exec_cmd_find_java)
            pid = output_java.decode().strip()
            if exit_code_java == 0 and pid.isdigit():
                exec_cmd2 = [
                    "sh", "-c",
                    f'echo {shlex.quote(safe_command)} > /proc/{pid}/fd/0'
                ]
                exit_code2, output2 = container.exec_run(exec_cmd2)
                if exit_code2 == 0:
                    return {"exit_code": exit_code2, "output": f"Command sent via PID {pid}: {command}", "method": "pid-stdin"}
                else:
                    return {"exit_code": exit_code2, "output": output2.decode(errors='ignore'), "method": "pid-stdin"}
            else:
                return {"exit_code": 1, "output": "Could not find Java process in container.", "method": "pid-stdin"}

        except Exception as e:
            logger.error(f"Fehler beim Senden des Befehls an Container {container_id}: {e}")
            return {"exit_code": 1, "output": f"Error: {e}", "method": "error"}

    def get_server_stats(self, container_id: str) -> dict:
        """
        Returns CPU %, RAM usage (MB), and network I/O (MB) for the given container.
        If stats are not available (container not running or Docker not responding), returns an error message.
        """
        try:
            container = self.client.containers.get(container_id)
            container.reload()
            if container.status != "running":
                return {
                    "id": container.id,
                    "error": "Container is not running. Stats unavailable.",
                    "cpu_percent": 0.0,
                    "memory_usage_mb": 0.0,
                    "memory_limit_mb": 0.0,
                    "memory_percent": 0.0,
                    "network_rx_mb": 0.0,
                    "network_tx_mb": 0.0,
                }

            # Get two samples to calculate CPU %
            stats1 = container.stats(stream=False)
            time.sleep(1.0)  # Use a full second for more accurate CPU calculation
            stats2 = container.stats(stream=False)

            # CPU calculation (see Docker API docs for details)
            cpu_delta = stats2["cpu_stats"]["cpu_usage"]["total_usage"] - stats1["cpu_stats"]["cpu_usage"]["total_usage"]
            system_delta = stats2["cpu_stats"].get("system_cpu_usage", 0) - stats1["cpu_stats"].get("system_cpu_usage", 0)
            cpu_count = stats2["cpu_stats"]["online_cpus"] if "online_cpus" in stats2["cpu_stats"] else len(stats2["cpu_stats"]["cpu_usage"].get("percpu_usage", [])) or 1
            cpu_percent = 0.0
            if system_delta > 0 and cpu_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * cpu_count * 100.0

            # RAM calculation
            mem_usage = stats2["memory_stats"].get("usage", 0)
            # Remove cache from memory usage if present (for more accurate "used" memory)
            if "stats" in stats2["memory_stats"] and "cache" in stats2["memory_stats"]["stats"]:
                mem_usage -= stats2["memory_stats"]["stats"]["cache"]
            mem_limit = stats2["memory_stats"].get("limit", 1)
            mem_percent = (mem_usage / mem_limit) * 100.0 if mem_limit else 0.0
            mem_usage_mb = mem_usage / (1024 * 1024)
            mem_limit_mb = mem_limit / (1024 * 1024)

            # Network calculation
            net_stats = stats2.get("networks", {})
            rx_bytes = sum(net.get("rx_bytes", 0) for net in net_stats.values())
            tx_bytes = sum(net.get("tx_bytes", 0) for net in net_stats.values())
            rx_mb = rx_bytes / (1024 * 1024)
            tx_mb = tx_bytes / (1024 * 1024)

            return {
                "id": container.id,
                "cpu_percent": round(cpu_percent, 2),
                "memory_usage_mb": round(mem_usage_mb, 2),
                "memory_limit_mb": round(mem_limit_mb, 2),
                "memory_percent": round(mem_percent, 2),
                "network_rx_mb": round(rx_mb, 2),
                "network_tx_mb": round(tx_mb, 2),
            }
        except docker.errors.NotFound:
            logger.warning(f"Container {container_id} not found for stats request.")
            return {
                "id": container_id,
                "error": "Container not found.",
                "cpu_percent": 0.0,
                "memory_usage_mb": 0.0,
                "memory_limit_mb": 0.0,
                "memory_percent": 0.0,
                "network_rx_mb": 0.0,
                "network_tx_mb": 0.0,
            }
        except Exception as e:
            logger.error(f"Error getting stats for container {container_id}: {e}")
            return {
                "id": container_id,
                "error": f"Failed to get stats: {str(e)}",
                "cpu_percent": 0.0,
                "memory_usage_mb": 0.0,
                "memory_limit_mb": 0.0,
                "memory_percent": 0.0,
                "network_rx_mb": 0.0,
                "network_tx_mb": 0.0,
            }

    def get_player_info(self, container_id: str) -> dict:
        """
        Retrieve player info using RCON only to avoid spamming the console.
        If RCON is not enabled or fails, return zeros without attempting console-based fallbacks.
        Returns a dict: { 'online': int, 'max': int, 'names': list[str] }
        """
        try:
            container = self.client.containers.get(container_id)
            env_vars = container.attrs.get("Config", {}).get("Env", [])
            env_dict = dict(var.split("=", 1) for var in env_vars if "=" in var)

            from mcrcon import MCRcon
            rcon_enabled = env_dict.get("ENABLE_RCON", "false").lower() == "true"
            rcon_password = env_dict.get("RCON_PASSWORD", "")
            rcon_port_env = env_dict.get("RCON_PORT", "25575")

            # Determine mapped host port for RCON
            rcon_port = None
            network_settings = container.attrs.get("NetworkSettings", {}).get("Ports", {})
            for port, mappings in (network_settings or {}).items():
                # Look for mapping that contains the RCON port or default 25575
                if port.endswith("/tcp") and (port.startswith(str(rcon_port_env)) or port.startswith("25575")):
                    if mappings and isinstance(mappings, list) and len(mappings) > 0:
                        rcon_port = int(mappings[0].get("HostPort")) if mappings[0].get("HostPort") else None
                        break

            if not (rcon_enabled and rcon_password and rcon_port):
                return {"online": 0, "max": 0, "names": []}

            # Query using RCON (does not spam console)
            output = ""
            try:
                with MCRcon("localhost", rcon_password, port=rcon_port, timeout=2) as mcr:
                    output = mcr.command("list") or ""
            except Exception as rcon_err:
                logger.debug(f"RCON list failed for {container_id}: {rcon_err}")
                return {"online": 0, "max": 0, "names": []}

            text = str(output)
            online = 0
            maxp = 0
            names: List[str] = []
            import re as _re
            m = _re.search(r"There are\s+(\d+)\s+of a max of\s+(\d+)\s+players online", text)
            if not m:
                m = _re.search(r"(\d+)\s*/\s*(\d+)\s*players? online", text)
            if m:
                online = int(m.group(1))
                maxp = int(m.group(2))
                colon_idx = text.find(":")
                if colon_idx != -1 and colon_idx + 1 < len(text):
                    names_str = text[colon_idx + 1:].strip()
                    if names_str:
                        names = [n.strip() for n in names_str.split(",") if n.strip()]
            return {"online": online, "max": maxp, "names": names}
        except Exception as e:
            logger.warning(f"Failed to get player info (RCON) for container {container_id}: {e}")
            return {"online": 0, "max": 0, "names": []}

    def get_server_terminal(self, container_id: str, tail: int = 100) -> dict:
        """
        Returns the latest lines from the server's terminal (stdout).
        """
        return self.get_server_logs(container_id, tail=tail)

    def write_server_terminal(self, container_id: str, command: str) -> dict:
        """
        Writes a command to the Minecraft server's terminal (stdin).
        """
        if command.startswith("/"):
            command_to_send = command[1:]
        else:
            command_to_send = command
        return self.send_command(container_id, command_to_send)

    def update_server_java_version(self, container_id: str, java_version: str) -> dict:
        """
        Updates the Java version for a server by modifying container environment variables.
        """
        try:
            container = self.client.containers.get(container_id)
            
            # Validate Java version
            if java_version not in ["8", "11", "17", "21"]:
                raise ValueError(f"Invalid Java version: {java_version}. Must be 8, 11, 17, or 21")
            
            # Get current container info
            attrs = container.attrs or {}
            config = attrs.get("Config", {})
            env_vars = config.get("Env", [])
            
            # Update environment variables
            new_env_vars = []
            java_version_updated = False
            java_bin_updated = False
            
            for env_var in env_vars:
                if env_var.startswith("JAVA_VERSION="):
                    new_env_vars.append(f"JAVA_VERSION={java_version}")
                    java_version_updated = True
                elif env_var.startswith("JAVA_BIN="):
                    new_env_vars.append(f"JAVA_BIN=/usr/local/bin/java{java_version}")
                    java_bin_updated = True
                else:
                    new_env_vars.append(env_var)
            
            # Add new environment variables if they didn't exist
            if not java_version_updated:
                new_env_vars.append(f"JAVA_VERSION={java_version}")
            if not java_bin_updated:
                new_env_vars.append(f"JAVA_BIN=/usr/local/bin/java{java_version}")
            
            # Update container labels (environment variables require container restart)
            current_labels = getattr(container, "labels", {}) or {}
            current_labels["mc.java_version"] = java_version
            current_labels["mc.java_bin"] = f"/usr/local/bin/java{java_version}"
            current_labels["mc.env.JAVA_VERSION"] = java_version
            current_labels["mc.env.JAVA_BIN"] = f"/usr/local/bin/java{java_version}"
            
            # Update container configuration with new labels
            container.update(labels=current_labels)
            
            logger.info(f"Updated Java version to {java_version} for container {container_id}")
            
            return {
                "success": True,
                "message": f"Java version updated to {java_version}. Container restart required to apply changes.",
                "java_version": java_version,
                "java_bin": f"/usr/local/bin/java{java_version}",
                "restart_required": True
            }
            
        except docker.errors.NotFound:
            logger.error(f"Container {container_id} not found when updating Java version")
            raise RuntimeError(f"Container {container_id} not found")
        except Exception as e:
            logger.error(f"Error updating Java version for container {container_id}: {e}")
            raise RuntimeError(f"Failed to update Java version: {e}")