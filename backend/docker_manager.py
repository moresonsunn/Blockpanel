import os
import re
import shlex
import docker
import json
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
# CasaOS application id to associate child runtime containers with the main app.
# IMPORTANT: CasaOS usually assigns its own internal app ID when installing apps.
# Hardcoding an ID can cause child containers to be shown as "Legacy App" in some CasaOS setups.
DEFAULT_CASAOS_APP_ID = "lynx"
_CASAOS_APP_ID_ENV = (os.getenv("CASAOS_APP_ID") or "").strip()
CASAOS_CATEGORY = os.getenv("CASAOS_CATEGORY", "Games")


def _is_unified_image_name(image: str | None) -> bool:
    s = (image or "").strip().lower()
    if not s:
        return False
    # Treat the single DockerHub repo (moresonsun/lynx) as the unified image.
    # Match both namespaced and local tags, but avoid matching other helper images.
    base = s.split("@", 1)[0]
    repo = base.split(":", 1)[0]
    return repo == "lynx" or repo.endswith("/lynx")


def _detect_self_container_id() -> str | None:
    """Best-effort detection of the current container ID.

    - In Docker, HOSTNAME is often the short container ID.
    - /proc/self/cgroup commonly includes a long 64-hex container id.
    """
    try:
        host = (os.getenv("HOSTNAME") or "").strip()
        if host and re.fullmatch(r"[0-9a-fA-F]{8,64}", host):
            return host
    except Exception:
        pass

    try:
        cgroup_path = "/proc/self/cgroup"
        if os.path.exists(cgroup_path):
            text = Path(cgroup_path).read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"([0-9a-f]{64})", text)
            if m:
                return m.group(1)
            m2 = re.search(r"docker[-/]{1}([0-9a-f]{12,64})", text)
            if m2:
                return m2.group(1)
    except Exception:
        pass

    return None

# Compose grouping detection: try to read the current controller container's labels and networks
def _detect_compose_context() -> tuple[str | None, str | None]:
    try:
        _client = docker.from_env()
        _self_id = _detect_self_container_id()
        if not _self_id:
            return None, None
        _self = _client.containers.get(_self_id)
        _labels = (_self.attrs.get("Config", {}) or {}).get("Labels", {}) or {}
        compose_project = _labels.get("com.docker.compose.project")
        # Pick any attached network that looks like a compose default network
        networks = (_self.attrs.get("NetworkSettings", {}) or {}).get("Networks", {}) or {}
        compose_net = None
        if compose_project and networks:
            # Common default network suffix "_default"
            preferred = f"{compose_project}_default"
            if preferred in networks:
                compose_net = preferred
            else:
                # Fallback to the first network name
                compose_net = next(iter(networks.keys())) if networks else None
        return compose_project, compose_net
    except Exception:
        return None, None

_detected_project, _detected_network = _detect_compose_context()
COMPOSE_PROJECT = _detected_project or os.getenv("COMPOSE_PROJECT_NAME") or os.getenv("CASAOS_COMPOSE_PROJECT") or (_CASAOS_APP_ID_ENV or DEFAULT_CASAOS_APP_ID)
COMPOSE_RUNTIME_SERVICE = os.getenv("COMPOSE_RUNTIME_SERVICE", "minecraft-runtime")
COMPOSE_NETWORK = _detected_network or os.getenv("COMPOSE_NETWORK") or (f"{os.getenv('COMPOSE_PROJECT_NAME')}_default" if os.getenv("COMPOSE_PROJECT_NAME") else None)
_runtime_image = (os.getenv("LYNX_RUNTIME_IMAGE") or os.getenv("BLOCKPANEL_RUNTIME_IMAGE") or "").strip()
_runtime_tag = (os.getenv("LYNX_RUNTIME_TAG") or os.getenv("BLOCKPANEL_RUNTIME_TAG") or "latest").strip() or "latest"
RUNTIME_IMAGE = f"{_runtime_image}:{_runtime_tag}" if _runtime_image else "mc-runtime:latest"
MINECRAFT_PORT = 25565
DEFAULT_STEAM_PORT_START = 20000

# CasaOS AppManagement (compose apps) integration for Steam servers.
# When configured, Steam servers can be installed as CasaOS v2 compose apps to avoid the
# "Legacy-App" section in CasaOS.
CASAOS_API_BASE = (os.getenv("CASAOS_API_BASE") or "").strip()
CASAOS_API_TOKEN = (os.getenv("CASAOS_API_TOKEN") or "").strip()

# --- Helper functions for direct jar download fallback ---

def download_file(url: str, dest: Path, min_size: int = 1024 * 100, max_retries: int = 3, diagnostics: list | None = None):
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
                status_code = r.status_code

                # Read the first few bytes to check if it's a valid file
                first_chunk = next(r.iter_content(chunk_size=8192), b'')
                r.close()  # Close the first request
                size_header = r.headers.get("content-length")
                # Record attempt diagnostics
                if diagnostics is not None:
                    diagnostics.append({
                        "attempt": attempt + 1,
                        "status_code": status_code,
                        "content_type": content_type,
                        "first_bytes_hex": first_chunk[:32].hex(),
                        "first_bytes_ascii": ''.join(chr(b) if 32 <= b <= 126 else '.' for b in first_chunk[:32]),
                        "declared_size": int(size_header) if size_header and size_header.isdigit() else None,
                        "url": url,
                    })

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
                if diagnostics is not None and diagnostics:
                    diagnostics[-1]["final_size"] = dest.stat().st_size
                    diagnostics[-1]["success"] = True
                return True
            else:
                logger.warning(f"Downloaded file {dest} is too small or missing after download.")
                if diagnostics is not None and diagnostics:
                    diagnostics[-1]["final_size"] = dest.stat().st_size if dest.exists() else None
                    diagnostics[-1]["success"] = False
        except Exception as e:
            logger.warning(f"Failed to download {url} to {dest}: {e}")
            if diagnostics is not None:
                diagnostics.append({
                    "attempt": attempt + 1,
                    "error": str(e),
                    "url": url,
                    "success": False,
                })
        # Remove incomplete file
        if dest.exists():
            try:
                dest.unlink()
            except Exception:
                pass
        time.sleep(2)
    return False

def get_paper_download_url(version: str) -> Optional[str]:
    """Resolve latest Paper build download URL with validation.

    New API structure:
      GET /v2/projects/paper/versions/{version} => { builds: [build_numbers...] }
      GET /v2/projects/paper/versions/{version}/builds/{build} => downloads.application.name

    Returns full download URL or None if unavailable.
    """
    base = "https://api.papermc.io/v2/projects/paper"
    try:
        # If version is blank, fetch project info and pick latest version
        if not version:
            proj = requests.get(base, timeout=15)
            proj.raise_for_status()
            versions = proj.json().get("versions") or []
            if not versions:
                logger.warning("Paper project returned no versions")
                return None
            version = versions[-1]

        v = requests.get(f"{base}/versions/{version}", timeout=15)
        if v.status_code == 404:
            logger.warning(f"Paper version {version} not found (404)")
            return None
        v.raise_for_status()
        data = v.json()
        builds = data.get("builds") or []
        if not builds:
            logger.warning(f"No builds listed for Paper {version}")
            return None
        latest = builds[-1]
        b = requests.get(f"{base}/versions/{version}/builds/{latest}", timeout=15)
        b.raise_for_status()
        bdata = b.json()
        downloads = (bdata.get("downloads") or {}).get("application") or {}
        jar_name = downloads.get("name") or f"paper-{version}-{latest}.jar"
        url = f"{base}/versions/{version}/builds/{latest}/downloads/{jar_name}"
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
    """
    Resolve the Fabric server launcher JAR URL using the official Fabric provider
    (game version + loader version + latest stable installer).
    """
    try:
        try:
            from server_providers.fabric import FabricProvider as _FabricProvider
        except Exception:
            from backend.server_providers.fabric import FabricProvider as _FabricProvider  # type: ignore
        provider = _FabricProvider()
        if not loader_version:
            loader_version = provider.get_latest_loader_version(version)
        installer_version = provider.get_latest_installer_version()
        return provider.get_download_url_with_loader(version, loader_version, installer_version)
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
            diag: list = []
            success = download_file(url, jar_path, min_size=min_jar_size, diagnostics=diag)
            if not success:
                # Persist diagnostics in server_meta.json for post-mortem
                try:
                    meta_path = server_dir / "server_meta.json"
                    meta = {}
                    if meta_path.exists():
                        meta = json.loads(meta_path.read_text(encoding="utf-8") or "{}")
                    meta.setdefault("last_download_failure", {
                        "url": url,
                        "attempts": diag,
                        "timestamp": int(time.time()),
                        "type": server_type,
                        "version": version,
                    })
                    meta_path.write_text(json.dumps(meta), encoding="utf-8")
                except Exception:
                    pass
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
        # Simple in-memory caches
        self._stats_cache: dict[str, tuple[float, dict]] = {}
        self._cached_casaos_app_id: str | None = None
        # Optional: run Steam servers on a separate Docker engine (e.g., remote host or DinD)
        # so they don't show up in CasaOS (which enumerates the host Docker engine).
        self._steam_docker_host: str | None = (os.getenv("STEAM_DOCKER_HOST") or "").strip() or None
        self._steam_client: docker.DockerClient | None = None

    def _get_steam_client(self) -> docker.DockerClient | None:
        host = (self._steam_docker_host or "").strip()
        if not host:
            return None
        if self._steam_client is not None:
            return self._steam_client
        try:
            self._steam_client = docker.DockerClient(base_url=host)
            return self._steam_client
        except Exception as exc:
            logger.warning(f"Failed to init STEAM_DOCKER_HOST client ({host}): {exc}")
            self._steam_client = None
            return None

    def _iter_docker_clients(self):
        """Yield available Docker clients as (client, engine_name)."""
        yield (self.client, "host")
        steam = self._get_steam_client()
        if steam is not None:
            yield (steam, "steam")

    def _get_container_any(self, container_id_or_name: str):
        """Lookup a container across all configured Docker engines."""
        last_exc: Exception | None = None
        for client, _engine in self._iter_docker_clients():
            try:
                return client.containers.get(container_id_or_name)
            except Exception as exc:
                last_exc = exc
                continue
        raise last_exc or docker.errors.NotFound("Container not found")

    def _resolve_casaos_app_id(self) -> str:
        """Resolve the CasaOS app id used to group child containers.

        Preference order:
        1) Detect from controller container labels (io.casaos.app / io.casaos.parent)
        2) Fall back to CASAOS_APP_ID env (if set)
        3) Fall back to DEFAULT_CASAOS_APP_ID
        """
        if self._cached_casaos_app_id:
            return self._cached_casaos_app_id

        try:
            self_id = _detect_self_container_id()
            if self_id:
                c = self.client.containers.get(self_id)
                labels = (c.attrs.get("Config", {}) or {}).get("Labels", {}) or {}
                detected = (labels.get("io.casaos.app") or labels.get("io.casaos.parent") or "").strip()
                if detected:
                    self._cached_casaos_app_id = detected
                    return detected

                # Secondary fallback: some installs might only expose compose metadata
                compose_project = (labels.get("com.docker.compose.project") or "").strip()
                if compose_project:
                    self._cached_casaos_app_id = compose_project
                    return compose_project
        except Exception:
            pass

        fallback = (os.getenv("CASAOS_APP_ID") or "").strip() or DEFAULT_CASAOS_APP_ID
        self._cached_casaos_app_id = fallback
        return fallback

    def _ensure_client(self) -> None:
        """Ensure the Docker client is ready; recreate it if the connection dropped."""
        if getattr(self, "client", None) is None:
            self.client = self._init_client()
            return
        try:
            # Ping the daemon to confirm the existing client is still valid.
            self.client.ping()
        except Exception:
            try:
                self.client.close()
            except Exception:
                pass
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
        # Lightweight 2s cache to avoid hammering Docker for dashboard polling.
        now = time.time()
        cache_entry = getattr(self, "_list_cache", None)
        if cache_entry:
            ts, payload = cache_entry
            if now - ts <= 2:
                return payload
        try:
            containers_by_engine: list[tuple[str, object]] = []
            for client, engine in self._iter_docker_clients():
                try:
                    for c in client.containers.list(all=True):
                        containers_by_engine.append((engine, c))
                except Exception as e:
                    logger.warning(f"Failed listing containers from engine '{engine}': {e}")

            result = []
            seen_ids: set[str] = set()
            for engine, c in containers_by_engine:
                try:
                    try:
                        cid = getattr(c, "id", None)
                        if cid and cid in seen_ids:
                            continue
                        if cid:
                            seen_ids.add(cid)
                    except Exception:
                        pass
                    attrs = c.attrs or {}
                    config = attrs.get("Config", {})
                    network = attrs.get("NetworkSettings", {})
                    # Extract server type and version from labels if present
                    labels = (attrs.get("Config", {}) or {}).get("Labels", {}) or {}
                    is_minecraft = str(labels.get(MINECRAFT_LABEL, "")).lower() == "true"
                    is_steam = str(labels.get("steam.server", "")).lower() == "true"
                    if not (is_minecraft or is_steam):
                        continue

                    server_type = labels.get("mc.type") if is_minecraft else None
                    server_version = labels.get("mc.version") if is_minecraft else None
                    loader_version = labels.get("mc.loader_version") if is_minecraft else None
                    steam_game = labels.get("steam.game") if is_steam else None
                    if is_steam:
                        server_type = f"steam:{steam_game}" if steam_game else "steam"
                        server_version = labels.get("steam.version")
                    
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

                    primary_host_port = None
                    try:
                        for mapping in port_mappings.values():
                            if isinstance(mapping, dict):
                                hp = mapping.get("host_port")
                                if hp:
                                    primary_host_port = int(hp) if str(hp).isdigit() else hp
                                    break
                    except Exception:
                        primary_host_port = None

                    mounts = attrs.get("Mounts", [])
                    data_path = None
                    try:
                        if mounts:
                            first_mount = next((m for m in mounts if isinstance(m, dict) and m.get("Source")), None)
                            if first_mount:
                                data_path = first_mount.get("Source")
                    except Exception:
                        data_path = None
                    
                    steam_ports: List[Dict[str, object]] = []
                    steam_port_summary: List[str] = []
                    try:
                        for raw_key, mapping in port_mappings.items():
                            if not isinstance(raw_key, str):
                                continue
                            parts = raw_key.split("/", 1)
                            if not parts:
                                continue
                            container_port = parts[0]
                            proto = parts[1] if len(parts) > 1 else "tcp"
                            try:
                                c_port_int = int(container_port)
                            except Exception:
                                c_port_int = container_port
                            host_port = None
                            host_ip = None
                            if isinstance(mapping, dict):
                                host_port = mapping.get("host_port")
                                host_ip = mapping.get("host_ip")
                            steam_ports.append({
                                "container_port": c_port_int,
                                "protocol": proto.lower(),
                                "host_port": host_port,
                                "host_ip": host_ip,
                            })
                            if host_port:
                                steam_port_summary.append(f"{host_port}/{proto.lower()}")
                    except Exception:
                        steam_ports = []
                        steam_port_summary = []

                    result.append({
                        "id": c.id,
                        "name": c.name,
                        "status": getattr(c, "status", "unknown"),
                        "image": config.get("Image"),
                        "labels": labels,
                        "ports": raw_ports,  # Keep raw ports for backward compatibility
                        "port_mappings": port_mappings,  # New field with actual host port mappings
                        "mounts": mounts,
                        "server_type": server_type,
                        "server_version": server_version,
                        "loader_version": loader_version,
                        "steam_game": steam_game,
                        "server_kind": "steam" if is_steam else "minecraft",
                        "primary_host_port": primary_host_port,
                        "data_path": data_path,
                        "steam_ports": steam_ports,
                        "port_summary": steam_port_summary,
                        "host_port": primary_host_port,
                        "created_at": attrs.get("Created"),
                        "engine": engine,
                        # Shorthand keys for UI convenience
                        "type": server_type,
                        "version": server_version,
                    })
                except docker.errors.NotFound:
                    logger.warning(f"Container {c.id} not found when listing servers, skipping")
                    continue
                except Exception as e:
                    logger.warning(f"Error processing container {c.id}: {e}")
                    continue
            self._list_cache = (now, result)
            return result
        except Exception as e:
            logger.error(f"Error listing servers: {e}")
            return []

    def get_server_type_and_version(self, container_id: str) -> dict:
        """
        Returns the server type and version for a given container.
        """
        try:
            container = self._get_container_any(container_id)
            labels = getattr(container, "labels", {})
            server_kind = "minecraft"
            server_type = labels.get("mc.type")
            server_version = labels.get("mc.version")
            loader_version = labels.get("mc.loader_version")
            steam_game = None
            if str(labels.get("steam.server", "")).lower() == "true":
                server_kind = "steam"
                steam_game = labels.get("steam.game")
                server_type = f"steam:{steam_game}" if steam_game else "steam"
                server_version = labels.get("steam.version")
                loader_version = None
            return {
                "id": container.id,
                "server_type": server_type,
                "server_version": server_version,
                "loader_version": loader_version,
                "server_kind": server_kind,
                "steam_game": steam_game,
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
            container = self._get_container_any(container_id)
            attrs = container.attrs or {}
            config = attrs.get("Config", {})
            network = attrs.get("NetworkSettings", {})
            labels = (attrs.get("Config", {}) or {}).get("Labels", {}) or {}
            server_kind = "minecraft"
            steam_game = None
            server_type = labels.get("mc.type")
            server_version = labels.get("mc.version")
            loader_version = labels.get("mc.loader_version")
            if str(labels.get("steam.server", "")).lower() == "true":
                server_kind = "steam"
                steam_game = labels.get("steam.game")
                server_type = f"steam:{steam_game}" if steam_game else "steam"
                server_version = labels.get("steam.version")
                loader_version = None
            
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
            java_opts = ""
            
            for env_var in env_vars:
                if env_var.startswith("JAVA_VERSION="):
                    java_version = env_var.split("=", 1)[1]
                elif env_var.startswith("JAVA_BIN="):
                    java_bin = env_var.split("=", 1)[1]
                elif env_var.startswith("JAVA_VERSION_OVERRIDE="):
                    # Prefer explicit override variable when present
                    java_version = env_var.split("=", 1)[1]
                elif env_var.startswith("JAVA_BIN_OVERRIDE="):
                    java_bin = env_var.split("=", 1)[1]
                elif env_var.startswith("JAVA_OPTS="):
                    java_opts = env_var.split("=", 1)[1]
            
            # Override with label if present
            if "mc.java_version" in labels:
                java_version = labels["mc.java_version"]
                java_bin = f"/usr/local/bin/java{java_version}"
            if "mc.env.JAVA_OPTS" in labels:
                java_opts = labels["mc.env.JAVA_OPTS"]
            
            # Extract actual host port mappings
            port_mappings = {}
            steam_ports: List[Dict[str, object]] = []
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

                try:
                    parts = str(container_port).split("/", 1)
                    c_port = parts[0]
                    proto = parts[1] if len(parts) > 1 else "tcp"
                    try:
                        c_port_val = int(c_port)
                    except Exception:
                        c_port_val = c_port
                    mapping = port_mappings.get(container_port)
                    steam_ports.append({
                        "container_port": c_port_val,
                        "protocol": proto.lower(),
                        "host_port": mapping.get("host_port") if isinstance(mapping, dict) else None,
                        "host_ip": mapping.get("host_ip") if isinstance(mapping, dict) else None,
                    })
                except Exception:
                    continue

            primary_host_port = None
            try:
                for mapping in port_mappings.values():
                    if isinstance(mapping, dict):
                        hp = mapping.get("host_port")
                        if hp:
                            primary_host_port = int(hp) if str(hp).isdigit() else hp
                            break
            except Exception:
                primary_host_port = None

            mounts = attrs.get("Mounts", [])
            data_path = None
            try:
                if mounts:
                    first_mount = next((m for m in mounts if isinstance(m, dict) and m.get("Source")), None)
                    if first_mount:
                        data_path = first_mount.get("Source")
            except Exception:
                data_path = None
            
            return {
                "id": container.id,
                "name": container.name,
                "status": getattr(container, "status", "unknown"),
                "image": config.get("Image"),
                "labels": labels,
                "ports": raw_ports,
                "port_mappings": port_mappings,
                "mounts": mounts,
                "server_type": server_type,
                "server_version": server_version,
                "loader_version": loader_version,
                "server_kind": server_kind,
                "steam_game": steam_game,
                "primary_host_port": primary_host_port,
                "data_path": data_path,
                "steam_ports": steam_ports,
                "java_version": java_version,
                "java_bin": java_bin,
                "java_args": java_opts,
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
                "Runtime image '{}' not found. Build it with: docker build -t {} -f docker/controller-unified.Dockerfile .".format(
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

    def get_used_host_ports(self, only_minecraft: bool = True, *, client: docker.DockerClient | None = None) -> set:
        """
        Return a set of host ports currently bound by any Docker container.
        If only_minecraft is True, limit to the Minecraft container port (25565/tcp)
        but still include bindings from *all* containers to avoid collisions with
        the controller or CasaOS parent app.
        """
        used: set[int] = set()
        try:
            active_client = client or self.client
            containers = active_client.containers.list(all=True)
            for c in containers:
                try:
                    ports = (c.attrs.get("NetworkSettings", {}) or {}).get("Ports", {}) or {}
                    for container_port, bindings in ports.items():
                        if only_minecraft and not str(container_port).startswith(f"{MINECRAFT_PORT}/"):
                            continue
                        if bindings and isinstance(bindings, list):
                            for b in bindings:
                                hp = b.get("HostPort")
                                if hp:
                                    try:
                                        used.add(int(hp))
                                    except Exception:
                                        pass
                except Exception:
                    continue
        except Exception:
            pass
        return used

    def _get_used_host_ports_by_protocol(
        self,
        *,
        only_minecraft: bool = True,
        client: docker.DockerClient | None = None,
    ) -> dict[str, set[int]]:
        """Return used host ports grouped by protocol.

        Docker allows binding the same numeric port for TCP and UDP simultaneously,
        so callers that allocate game server ports should treat them independently.
        """
        used_by_proto: dict[str, set[int]] = {"tcp": set(), "udp": set()}
        try:
            active_client = client or self.client
            containers = active_client.containers.list(all=True)
            for c in containers:
                try:
                    ports = (c.attrs.get("NetworkSettings", {}) or {}).get("Ports", {}) or {}
                    for container_port, bindings in ports.items():
                        if only_minecraft and not str(container_port).startswith(f"{MINECRAFT_PORT}/"):
                            continue
                        proto = "tcp"
                        try:
                            parts = str(container_port).split("/", 1)
                            if len(parts) == 2 and parts[1]:
                                proto = str(parts[1]).lower()
                        except Exception:
                            proto = "tcp"
                        if proto not in used_by_proto:
                            used_by_proto[proto] = set()
                        if bindings and isinstance(bindings, list):
                            for b in bindings:
                                hp = b.get("HostPort")
                                if hp:
                                    try:
                                        used_by_proto[proto].add(int(hp))
                                    except Exception:
                                        pass
                except Exception:
                    continue
        except Exception:
            pass
        return used_by_proto

    def _pick_available_port_for_protocol(
        self,
        *,
        proto: str,
        used_by_proto: dict[str, set[int]],
        preferred: int | None = None,
        start: int = 1,
        end: int = 65535,
        allow_fallback: bool = True,
    ) -> int:
        """Pick an available host port for a specific protocol.

        This intentionally does *not* ask Docker for an ephemeral port.
        """
        proto = (proto or "tcp").lower()
        used = used_by_proto.setdefault(proto, set())
        if preferred and 1 <= preferred <= 65535:
            if preferred not in used:
                return preferred
            if not allow_fallback:
                raise RuntimeError(
                    f"Host port {preferred} ({proto}) is already in use by another container. Free it or choose a different port."
                )
        scan_start = max(int(start), (int(preferred) + 1) if preferred else int(start))
        for p in range(scan_start, int(end) + 1):
            if p not in used:
                return p
        raise RuntimeError(f"No available host ports found for {proto} in the scanned range")

    def pick_available_port(self, preferred: int | None = None, start: int = 25565, end: int = 25999, allow_fallback: bool = True) -> int:
        """
        Pick an available host port by scanning Docker port mappings.
        - If preferred is provided and free, return it.
        - If preferred is taken and allow_fallback is False, raise to force the caller to free it.
        - Otherwise scan for the next free port.
        Note: This only checks Docker-bound ports, not other host processes.
        """
        used = self.get_used_host_ports(only_minecraft=False)
        if preferred and 1 <= preferred <= 65535:
            if preferred not in used:
                return preferred
            if not allow_fallback:
                raise RuntimeError(f"Host port {preferred} is already in use by another container. Free it or choose a different port.")
        # If preferred given but used (and fallback allowed), start from preferred+1
        scan_start = max(start, (preferred + 1) if preferred else start)
        for p in range(scan_start, end + 1):
            if p not in used:
                return p
        # As a fallback, expand a bit beyond end
        for p in range(end + 1, min(end + 1000, 65535)):
            if p not in used:
                return p
        raise RuntimeError("No available host ports found in the scanned range")

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

    def create_server(self, name, server_type, version, host_port=None, loader_version=None, min_ram="1G", max_ram="2G", installer_version=None, extra_labels: dict | None = None):
        """
        Prepare server files for the requested type/version (downloading installers or jars as needed)
        and create a runtime container to run the server.
        """
        self._ensure_runtime_image()
        server_dir: Path = SERVERS_ROOT / name
        server_dir.mkdir(parents=True, exist_ok=True)

        # 1) Prepare server files (download jar/installer)
        try:
            prepare_server_files(
                server_type,
                version,
                server_dir,
                loader_version=loader_version,
                installer_version=installer_version,
            )

            # For installer-based servers (forge/neoforge), the installer will run in the runtime container
            if server_type.lower() in ("forge", "neoforge"):
                logger.info(f"Prepared {server_type} installer for {name}")
            else:
                jar_path = server_dir / "server.jar"
                if jar_path.exists() and jar_path.stat().st_size >= 1024 * 100:  # At least 100KB
                    logger.info(f"Server jar ready at {jar_path}")
                else:
                    logger.warning("server.jar missing or too small after prepare_server_files; attempting fix_server_jar")
                    fix_server_jar(server_dir, server_type, version, loader_version=loader_version)
        except Exception as e:
            logger.warning(f"prepare_server_files failed: {e}; attempting fix_server_jar where applicable")
            if server_type.lower() not in ("forge", "neoforge"):
                # Only non-installer types can be fixed with a direct jar download
                fix_server_jar(server_dir, server_type, version, loader_version=loader_version)
            else:
                # For installer-based servers, we cannot recover here
                raise

        # 2) Ensure EULA is accepted
        try:
            (server_dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")
        except Exception:
            pass

        # 3) Configure port binding (choose available host port if not provided)
        selected_host_port: int | None = None
        try:
            if host_port is not None:
                selected_host_port = self.pick_available_port(preferred=int(host_port), start=MINECRAFT_PORT, end=25999, allow_fallback=False)
            else:
                selected_host_port = self.pick_available_port(start=MINECRAFT_PORT, end=25999)
        except Exception:
            # Fallback to docker-assigned ephemeral mapping
            selected_host_port = None
        port_binding = {f"{MINECRAFT_PORT}/tcp": selected_host_port}

        # 4) Environment variables for runtime
        env_vars = {
            "SERVER_DIR_NAME": name,
            "MIN_RAM": min_ram,
            "MAX_RAM": max_ram,
            "SERVER_PORT": str(MINECRAFT_PORT),
            "SERVER_TYPE": server_type,
            "SERVER_VERSION": version,
        }
        # If a jar exists now, expose it so the runtime can prefer it
        try:
            preferred_names = ["server.jar", "fabric-server-launch.jar"] if server_type.lower() == "fabric" else ["server.jar"]
            for fname in preferred_names:
                fpath = server_dir / fname
                if fpath.exists() and fpath.stat().st_size > 0:
                    env_vars["SERVER_JAR"] = fname
                    break
        except Exception:
            pass

        casaos_app_id = self._resolve_casaos_app_id()

        # 5) Labels for metadata
        labels = {
            MINECRAFT_LABEL: "true",
            "mc.type": server_type,
            "mc.version": version,
            # Compose-equivalent grouping for UIs that rely on compose metadata
            "com.docker.compose.project": COMPOSE_PROJECT,
            "com.docker.compose.service": COMPOSE_RUNTIME_SERVICE,
            "com.docker.compose.version": "2",
            # CasaOS grouping to avoid Legacy App classification
            "io.casaos.app": casaos_app_id,
            "io.casaos.parent": casaos_app_id,
            "io.casaos.managed": "true",
            "io.casaos.category": CASAOS_CATEGORY,
            "io.casaos.group": casaos_app_id,
            "io.casaos.subapp": "true",
            "casaos": "casaos",
            "origin": "lynx",
            "name": name,
            "custom_id": f"{casaos_app_id}-{name}",
            "protocol": "tcp",
            # Optional: generic metadata that some dashboards honor
            "org.opencontainers.image.title": "Lynx Runtime",
            "org.opencontainers.image.description": "Minecraft server runtime container managed by Lynx",
        }
        if loader_version is not None:
            labels["mc.loader_version"] = str(loader_version)
        if extra_labels:
            try:
                labels.update({k: str(v) for k, v in extra_labels.items()})
            except Exception:
                pass
        if selected_host_port is not None:
            labels["web"] = str(selected_host_port)
        else:
            labels.setdefault("web", "")

        # 6) Memory limits
        def ram_to_bytes(ram_str):
            if isinstance(ram_str, int):
                return ram_str * 1024 * 1024  # Assume MB
            s = str(ram_str).strip().upper()
            if s.endswith('G'):
                return int(s[:-1]) * 1024 * 1024 * 1024
            elif s.endswith('M'):
                return int(s[:-1]) * 1024 * 1024
            else:
                # Interpret as MB
                return int(s) * 1024 * 1024

        memory_limit = ram_to_bytes(max_ram)

        # 7) Create the container
        # 7) Create the container (retry on host port conflicts)
        max_retries = 10
        attempt = 0
        last_err: Exception | None = None
        while attempt < max_retries:
            try:
                # If we are using the unified image (which has a default CMD that starts uvicorn),
                # override the entrypoint so the container runs the runtime script instead.
                run_kwargs = {}
                if (
                    os.getenv("LYNX_UNIFIED_IMAGE")
                    or os.getenv("BLOCKPANEL_UNIFIED_IMAGE")
                    or _is_unified_image_name(RUNTIME_IMAGE)
                    or _is_unified_image_name(os.getenv("LYNX_RUNTIME_IMAGE", ""))
                    or _is_unified_image_name(os.getenv("BLOCKPANEL_RUNTIME_IMAGE", ""))
                ):
                    # Only set entrypoint if the script exists in the image; if missing, let it fail visibly.
                    run_kwargs["entrypoint"] = ["/usr/local/bin/runtime-entrypoint.sh"]
                container = self.client.containers.run(
                    RUNTIME_IMAGE,
                    name=name,
                    labels=labels,
                    environment=env_vars,
                    ports=port_binding,
                    volumes=self._get_bind_volume(server_dir),
                    network=COMPOSE_NETWORK if COMPOSE_NETWORK else None,
                    detach=True,
                    tty=True,
                    stdin_open=True,
                    working_dir="/data",
                    mem_limit=memory_limit,
                    **run_kwargs,
                )
                logger.info(f"Container {container.id} created successfully for server {name}")
                break
            except docker.errors.APIError as e:
                msg = str(e).lower()
                # Retry if port is already allocated; pick next available and retry
                if "port is already allocated" in msg or "address already in use" in msg:
                    attempt += 1
                    try:
                        next_port = self.pick_available_port(
                            preferred=(selected_host_port + 1) if selected_host_port else MINECRAFT_PORT,
                            start=MINECRAFT_PORT,
                            end=25999,
                        )
                        selected_host_port = next_port
                        port_binding = {f"{MINECRAFT_PORT}/tcp": selected_host_port}
                        continue
                    except Exception as pick_err:
                        last_err = pick_err
                        break
                last_err = e
                break
            except Exception as e:
                last_err = e
                break
        if last_err is not None:
            logger.error(f"Failed to create container for server {name}: {last_err}")
            raise RuntimeError(f"Failed to create Docker container for server {name}: {last_err}")

        # 8) Optional: check Java version compatibility
        java_version = self._get_java_version(container)
        if java_version is None:
            logger.warning(
                f"Could not determine Java version in container for server {name}. It will continue but may have compatibility issues."
            )
        elif not self._is_java_version_compatible(java_version, server_type, version):
            logger.warning(
                f"Incompatible Java version {java_version} detected for server type {server_type} {version}. The server will continue but may have issues."
            )
        else:
            logger.info(f"Java version {java_version} is compatible with {server_type} {version}")

        return {"id": container.id, "name": container.name, "status": container.status}

    def create_server_from_existing(self, name: str, host_port: int | None = None, min_ram: str = "1G", max_ram: str = "2G", extra_env: dict | None = None, extra_labels: dict | None = None) -> dict:
        """Create a container for an existing server directory under /data/servers/{name} using the runtime image.
        Does not attempt to download any files; assumes files (including server.jar or installers) already exist.
        Optionally accepts extra_env to override runtime env (e.g., JAVA_BIN, JAVA_OPTS).
        """
        self._ensure_runtime_image()
        server_dir: Path = SERVERS_ROOT / name
        if not server_dir.exists() or not server_dir.is_dir():
            raise RuntimeError(f"Server directory {server_dir} does not exist")

        # Choose available host port for existing server if not provided
        try:
            if host_port is not None:
                selected_host_port = self.pick_available_port(preferred=int(host_port), start=MINECRAFT_PORT, end=25999, allow_fallback=False)
            else:
                selected_host_port = self.pick_available_port(start=MINECRAFT_PORT, end=25999)
        except Exception:
            selected_host_port = None
        port_binding = {f"{MINECRAFT_PORT}/tcp": selected_host_port}

        env_vars = {
            "SERVER_DIR_NAME": name,
            "MIN_RAM": min_ram,
            "MAX_RAM": max_ram,
            # Keep the runtime container's Minecraft port stable.
            # The entrypoint will normalize server.properties to this value.
            "SERVER_PORT": str(MINECRAFT_PORT),
        }
        if extra_env:
            try:
                for k, v in (extra_env or {}).items():
                    if v is None:
                        continue
                    env_vars[str(k)] = str(v)
            except Exception:
                pass
        try:
            run_kwargs = {}
            if (
                os.getenv("LYNX_UNIFIED_IMAGE")
                or os.getenv("BLOCKPANEL_UNIFIED_IMAGE")
                or _is_unified_image_name(RUNTIME_IMAGE)
                or _is_unified_image_name(os.getenv("LYNX_RUNTIME_IMAGE", ""))
                or _is_unified_image_name(os.getenv("BLOCKPANEL_RUNTIME_IMAGE", ""))
            ):
                run_kwargs["entrypoint"] = ["/usr/local/bin/runtime-entrypoint.sh"]

            # Load existing metadata (if any) and merge extra_env to build env_overrides
            meta_path = SERVERS_ROOT / name / "server_meta.json"
            meta = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8") or "{}")
                except Exception:
                    meta = {}

            stored_overrides = meta.get("env_overrides") or {}
            if not isinstance(stored_overrides, dict):
                stored_overrides = {}
            merged_env = {**stored_overrides}
            try:
                for k, v in (extra_env or {}).items():
                    if v is None:
                        continue
                    merged_env[str(k)] = str(v)
            except Exception:
                pass

            template_section = meta.get("template")
            template_info = template_section if isinstance(template_section, dict) else {}
            source_template_section = meta.get("source_template")
            source_template_info = source_template_section if isinstance(source_template_section, dict) else {}

            def _first_non_empty(*values):
                for value in values:
                    if isinstance(value, str):
                        candidate = value.strip()
                        if candidate:
                            return candidate
                return None

            server_type_guess = _first_non_empty(
                (extra_labels or {}).get("mc.type") if extra_labels else None,
                merged_env.get("SERVER_TYPE"),
                merged_env.get("SERVER_KIND"),
                meta.get("detected_type"),
                meta.get("server_type"),
                template_info.get("server_type"),
                source_template_info.get("server_type"),
                meta.get("type"),
            )
            server_version_guess = _first_non_empty(
                (extra_labels or {}).get("mc.version") if extra_labels else None,
                merged_env.get("SERVER_VERSION"),
                merged_env.get("MINECRAFT_VERSION"),
                merged_env.get("VERSION"),
                meta.get("detected_version"),
                meta.get("server_version"),
                template_info.get("server_version"),
                source_template_info.get("server_version"),
                meta.get("version"),
            )
            loader_version_guess = _first_non_empty(
                (extra_labels or {}).get("mc.loader_version") if extra_labels else None,
                merged_env.get("LOADER_VERSION"),
                merged_env.get("FABRIC_LOADER_VERSION"),
                merged_env.get("SERVER_LOADER"),
                meta.get("detected_loader_version"),
                meta.get("loader_version"),
                template_info.get("loader_version"),
                source_template_info.get("loader_version"),
            )
            casaos_app_id = self._resolve_casaos_app_id()

            custom_id_guess = _first_non_empty(
                (extra_labels or {}).get("custom_id") if extra_labels else None,
                meta.get("custom_id"),
                template_info.get("custom_id"),
                source_template_info.get("custom_id"),
            ) or f"{casaos_app_id}-{name}"

            def _ensure_env_var(key: str, value: str | None):
                if value is None:
                    return
                value_str = str(value).strip()
                if not value_str:
                    return
                current_env_val = env_vars.get(key)
                if not isinstance(current_env_val, str) or not current_env_val.strip():
                    env_vars[key] = value_str
                current_override = merged_env.get(key)
                if not isinstance(current_override, str) or not current_override.strip():
                    merged_env[key] = value_str

            _ensure_env_var("SERVER_TYPE", server_type_guess)
            _ensure_env_var("SERVER_VERSION", server_version_guess)
            if loader_version_guess:
                _ensure_env_var("LOADER_VERSION", loader_version_guess)
                if (server_type_guess or "").lower() == "fabric":
                    _ensure_env_var("FABRIC_LOADER_VERSION", loader_version_guess)

            resolved_label_type = server_type_guess or "custom"
            labels = {
                MINECRAFT_LABEL: "true",
                "mc.type": resolved_label_type,
                # Group with controller using compose-style labels only
                "com.docker.compose.project": COMPOSE_PROJECT,
                "com.docker.compose.service": COMPOSE_RUNTIME_SERVICE,
                "com.docker.compose.version": "2",
                # CasaOS grouping to avoid Legacy App classification
                "io.casaos.app": casaos_app_id,
                "io.casaos.parent": casaos_app_id,
                "io.casaos.managed": "true",
                "io.casaos.category": CASAOS_CATEGORY,
                "io.casaos.group": casaos_app_id,
                "io.casaos.subapp": "true",
                "casaos": "casaos",
                "origin": "lynx",
                "name": name,
                "custom_id": custom_id_guess,
                "protocol": "tcp",
                "org.opencontainers.image.title": "Lynx Runtime",
                "org.opencontainers.image.description": "Minecraft server runtime container managed by Lynx",
            }
            if server_version_guess:
                labels["mc.version"] = str(server_version_guess)
            if loader_version_guess:
                labels["mc.loader_version"] = str(loader_version_guess)
            try:
                for k, v in (extra_labels or {}).items():
                    if v is None:
                        continue
                    labels[str(k)] = str(v)
            except Exception:
                pass
            if selected_host_port is not None:
                labels["web"] = str(selected_host_port)
            else:
                labels.setdefault("web", "")

            # Determine numeric RAM values if provided (best-effort parsing)
            def _parse_mb(s):
                try:
                    if isinstance(s, str) and re.search(r"\d", s):
                        return int(re.sub(r"[^0-9]", "", s))
                except Exception:
                    return None
                return None

            min_mb = _parse_mb(min_ram) or meta.get("min_ram_mb")
            max_mb = _parse_mb(max_ram) or meta.get("max_ram_mb")

            # Compute top-level java_version
            java_ver = merged_env.get("JAVA_VERSION_OVERRIDE") or merged_env.get("JAVA_VERSION") or meta.get("java_version")

            # Attempt an auto-repair of a missing/corrupt server.jar when we have enough context
            try:
                jar_path = server_dir / "server.jar"
                min_jar_size = 1024 * 100
                if server_type_guess and server_version_guess and ((not jar_path.exists()) or jar_path.stat().st_size < min_jar_size):
                    logger.warning(
                        f"server.jar missing/too small for {name}; attempting auto-repair using {server_type_guess} {server_version_guess}..."
                    )
                    try:
                        fix_server_jar(server_dir, server_type_guess, server_version_guess, loader_version=loader_version_guess or None)
                    except Exception as rep_err:
                        logger.error(f"Auto-repair failed for {name}: {rep_err}")
            except Exception as auto_rep_err:
                logger.warning(f"Auto-repair check failed for {name}: {auto_rep_err}")

            # Persist merged metadata so UI/LocalAdapter can read it immediately
            new_meta = dict(meta or {})
            # Set creation timestamp if not already present
            if "created_ts" not in new_meta:
                import time, datetime
                now_ts = int(time.time())
                new_meta["created_ts"] = now_ts  # seconds since epoch
                try:
                    new_meta["created_iso"] = datetime.datetime.utcfromtimestamp(now_ts).isoformat() + "Z"
                except Exception:
                    pass
            new_meta.setdefault("name", name)
            if selected_host_port is not None:
                new_meta["host_port"] = int(selected_host_port)
            if min_mb is not None:
                new_meta["min_ram"] = f"{min_mb}M"
                new_meta["min_ram_mb"] = int(min_mb)
            if max_mb is not None:
                new_meta["max_ram"] = f"{max_mb}M"
                new_meta["max_ram_mb"] = int(max_mb)
            if merged_env:
                new_meta["env_overrides"] = merged_env
            if java_ver:
                new_meta["java_version"] = str(java_ver)
            if custom_id_guess:
                new_meta.setdefault("custom_id", custom_id_guess)
            if server_type_guess:
                new_meta["server_type"] = server_type_guess
                existing_detected_type = new_meta.get("detected_type")
                if not isinstance(existing_detected_type, str) or not existing_detected_type.strip():
                    new_meta["detected_type"] = server_type_guess
            if server_version_guess:
                new_meta["server_version"] = server_version_guess
                existing_detected_version = new_meta.get("detected_version")
                if not isinstance(existing_detected_version, str) or not existing_detected_version.strip():
                    new_meta["detected_version"] = server_version_guess
            if loader_version_guess:
                new_meta["loader_version"] = loader_version_guess
                existing_detected_loader = new_meta.get("detected_loader_version")
                if not isinstance(existing_detected_loader, str) or not existing_detected_loader.strip():
                    new_meta["detected_loader_version"] = loader_version_guess
            try:
                (SERVERS_ROOT / name).mkdir(parents=True, exist_ok=True)
                meta_path.write_text(json.dumps(new_meta), encoding="utf-8")
            except Exception:
                pass

            # Reflect java override in container labels for quick discovery
            try:
                if merged_env:
                    jver = merged_env.get("JAVA_VERSION_OVERRIDE") or merged_env.get("JAVA_VERSION")
                    if jver:
                        labels["mc.java_version"] = str(jver)
                        labels["mc.java_bin"] = merged_env.get("JAVA_BIN_OVERRIDE") or merged_env.get("JAVA_BIN") or f"/usr/local/bin/java{jver}"
            except Exception:
                pass

            container = self.client.containers.run(
                RUNTIME_IMAGE,
                name=name,
                labels=labels,
                environment=env_vars,
                ports=port_binding,
                volumes=self._get_bind_volume(server_dir),
                network=COMPOSE_NETWORK if COMPOSE_NETWORK else None,
                detach=True,
                tty=True,
                stdin_open=True,
                working_dir="/data",
                **run_kwargs,
            )
            logger.info(f"Container {container.id} created from existing dir for server {name}")
            try:
                # Augment meta with container creation time if available
                c_created = getattr(container, 'attrs', {}).get('Created') if hasattr(container, 'attrs') else None
                if c_created:
                    # Store raw string for debugging and parsed epoch
                    new_meta = json.loads((SERVERS_ROOT / name / 'server_meta.json').read_text(encoding='utf-8'))
                    new_meta.setdefault('container_created_raw', c_created)
                    from datetime import datetime, timezone
                    try:
                        ts = c_created.rstrip('Z')
                        if '.' in ts:
                            head, frac = ts.split('.', 1)
                            frac = (frac + '000000')[:6]
                            ts = f"{head}.{frac}"
                        dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
                        new_meta.setdefault('container_created_ts', int(dt.timestamp()))
                    except Exception:
                        pass
                    (SERVERS_ROOT / name / 'server_meta.json').write_text(json.dumps(new_meta), encoding='utf-8')
            except Exception:
                pass
            return {"id": container.id, "name": container.name, "status": container.status}
        except Exception as e:
            logger.error(f"Failed to create container from existing dir for {name}: {e}")
            raise RuntimeError(f"Failed to create Docker container for server {name}: {e}")


    def create_steam_container(
        self,
        *,
        name: str,
        image: str,
        ports: list[dict],
        env: dict | None = None,
        volume: dict | None = None,
        command: list[str] | None = None,
        restart_policy: dict | None = None,
        extra_labels: dict | None = None,
    ) -> dict:
        """Create a non-Minecraft container (Steam or other dedicated server).

        ports: list of {"container": 27015, "protocol": "udp"|"tcp", "host": optional int}
        volume: {"host": Path, "container": "/data"}
        """
        self._ensure_client()

        # Prefer a dedicated Docker engine for Steam when configured.
        # This allows hiding Steam containers from CasaOS by not creating them
        # on the host Docker engine CasaOS enumerates.
        client = self._get_steam_client() or self.client

        # Resolve host port bindings (deterministic; never ask Docker for ephemeral ports)
        # IMPORTANT: Many Steam dedicated servers require related/consecutive ports.
        # Bind ports as a single block (preserving offsets from the first port) so choosing a
        # custom host port doesn't break the rest of the required ports.
        port_binding: dict[str, int] = {}
        used_by_proto = self._get_used_host_ports_by_protocol(only_minecraft=False, client=client)
        # If Steam runs on a different engine but still binds ports on the same host network
        # (e.g., Docker-in-Docker with network_mode: host), also avoid collisions with host-engine ports.
        if client is not self.client:
            try:
                host_used = self._get_used_host_ports_by_protocol(only_minecraft=False, client=self.client)
                for proto, ports_set in (host_used or {}).items():
                    used_by_proto.setdefault(proto, set()).update(ports_set or set())
            except Exception:
                pass
        first_protocol: str | None = None

        normalized_ports: list[dict] = []
        for p in ports:
            try:
                raw_container = p.get("container")
                if raw_container is None:
                    raise ValueError("Missing container port")
                cport = int(raw_container)
                proto = (p.get("protocol") or "tcp").lower()
                if first_protocol is None:
                    first_protocol = proto

                preferred_raw = p.get("host")
                preferred_int = None
                if preferred_raw is not None:
                    try:
                        preferred_int = int(preferred_raw)
                    except Exception:
                        preferred_int = None
                normalized_ports.append({"cport": cport, "proto": proto, "preferred": preferred_int})
            except Exception as e:
                logger.warning(f"Failed to parse Steam port config {p}: {e}")
                raise

        # If someone supplied explicit host ports for multiple entries (not just the primary),
        # keep the older per-port behavior to respect those overrides.
        explicit_host_count = sum(1 for item in normalized_ports if (item.get("preferred") or 0) > 0)
        has_non_primary_explicit = any(
            (item.get("preferred") or 0) > 0 and idx != 0 for idx, item in enumerate(normalized_ports)
        )

        def _bind_single_port(cport: int, proto: str, preferred: int | None, *, allow_fallback: bool) -> int:
            host_val = self._pick_available_port_for_protocol(
                proto=proto,
                used_by_proto=used_by_proto,
                preferred=preferred,
                start=max(1, int(preferred or cport)),
                end=65535,
                allow_fallback=allow_fallback,
            )
            used_by_proto.setdefault(proto, set()).add(host_val)
            return host_val

        if has_non_primary_explicit and explicit_host_count > 0:
            for item in normalized_ports:
                cport = int(item["cport"])
                proto = str(item["proto"]).lower()
                preferred = item.get("preferred")
                allow_fallback = False if (preferred and preferred > 0) else True
                host_val = _bind_single_port(cport, proto, (preferred if preferred and preferred > 0 else cport), allow_fallback=allow_fallback)
                port_binding[f"{cport}/{proto}"] = host_val
        else:
            # Block allocation: preserve offsets from the primary port.
            base_cport = int(normalized_ports[0]["cport"]) if normalized_ports else 0
            requested_base = normalized_ports[0].get("preferred")
            strict_base = bool(requested_base and int(requested_base) > 0)
            base_candidate = int(requested_base) if strict_base else base_cport

            offsets = [int(item["cport"]) - base_cport for item in normalized_ports] if normalized_ports else [0]
            min_offset = min(offsets) if offsets else 0
            max_offset = max(offsets) if offsets else 0
            candidate_min = 1 - min_offset
            candidate_max = 65535 - max_offset
            if base_candidate < candidate_min or base_candidate > candidate_max:
                raise RuntimeError(
                    f"Host port base {base_candidate} is out of range for this game's port set (valid base: {candidate_min}-{candidate_max})."
                )

            def _block_is_free(base_host: int) -> bool:
                for item in normalized_ports:
                    cport = int(item["cport"])
                    proto = str(item["proto"]).lower()
                    desired = base_host + (cport - base_cport)
                    if desired in used_by_proto.setdefault(proto, set()):
                        return False
                return True

            chosen_base = base_candidate
            if strict_base:
                if not _block_is_free(chosen_base):
                    conflicts: list[str] = []
                    for item in normalized_ports:
                        cport = int(item["cport"])
                        proto = str(item["proto"]).lower()
                        desired = chosen_base + (cport - base_cport)
                        if desired in used_by_proto.setdefault(proto, set()):
                            conflicts.append(f"{desired}/{proto}")
                    raise RuntimeError(
                        f"Requested host port {chosen_base} cannot be used for '{name}' (conflicts: {', '.join(conflicts)})."
                    )
            else:
                # Find the next base where the whole block fits.
                start_base = max(chosen_base, candidate_min)
                b = start_base
                while b <= candidate_max and not _block_is_free(b):
                    b += 1
                if b > candidate_max:
                    raise RuntimeError("No available host ports found for the Steam server's required port set")
                chosen_base = b

            for item in normalized_ports:
                cport = int(item["cport"])
                proto = str(item["proto"]).lower()
                host_val = chosen_base + (cport - base_cport)
                used_by_proto.setdefault(proto, set()).add(host_val)
                port_binding[f"{cport}/{proto}"] = host_val

        casaos_app_id = self._resolve_casaos_app_id()
        labels = {
            "steam.server": "true",
            "steam.name": name,
            "origin": "lynx",
        }
        # CasaOS: group Steam child containers under the Lynx app so they don't
        # appear as standalone "Legacy Apps". Keep this minimal (no web/custom_id/name)
        # to avoid creating app tiles.
        try:
            if casaos_app_id:
                labels.update(
                    {
                        "io.casaos.app": casaos_app_id,
                        "io.casaos.parent": casaos_app_id,
                        "io.casaos.managed": "true",
                        "io.casaos.category": CASAOS_CATEGORY,
                        "io.casaos.group": casaos_app_id,
                        "io.casaos.subapp": "true",
                    }
                )
        except Exception:
            pass
        if first_protocol:
            labels["protocol"] = first_protocol
        # Intentionally omit CasaOS-facing "web" metadata; this helps avoid the container
        # being surfaced as a first-class CasaOS app tile.

        if extra_labels:
            for label_key, label_value in extra_labels.items():
                try:
                    labels[label_key] = str(label_value)
                except Exception:
                    pass

        volume_mounts = None
        if volume and volume.get("host") and volume.get("container"):
            volume_mounts = {str(Path(volume["host"])): {"bind": volume["container"], "mode": "rw"}}

        run_kwargs = {}
        if restart_policy:
            run_kwargs["restart_policy"] = restart_policy

        effective_network = None
        if client is self.client:
            effective_network = COMPOSE_NETWORK if COMPOSE_NETWORK else None

        container = client.containers.run(
            image,
            name=name,
            detach=True,
            tty=True,
            stdin_open=True,
            environment={k: str(v) for k, v in (env or {}).items()},
            ports=port_binding,
            volumes=volume_mounts,
            network=effective_network,
            command=command,
            labels=labels,
            **run_kwargs,
        )

        # Refresh the container to gather dynamically assigned host ports.
        try:
            container.reload()
        except Exception:
            pass

        resolved_ports: dict[str, int] = {}
        primary_host_port: str | None = None
        try:
            port_info = ((getattr(container, "attrs", {}) or {}).get("NetworkSettings", {}) or {}).get("Ports") or {}
            for key, bindings in port_info.items():
                if not bindings:
                    continue
                host_binding = bindings[0] if isinstance(bindings, list) and bindings else None
                if not host_binding:
                    continue
                host_port = host_binding.get("HostPort")
                if not host_port:
                    continue
                try:
                    resolved_ports[key] = int(host_port)
                except Exception:
                    resolved_ports[key] = host_port
                if primary_host_port is None:
                    primary_host_port = str(host_port)
        except Exception as inspect_err:
            logger.warning(f"Failed to inspect assigned ports for {name}: {inspect_err}")

        # Do not update container labels with resolved ports; Lynx reads ports directly.

        return {
            "id": container.id,
            "name": container.name,
            "image": image,
            "ports": resolved_ports or dict(port_binding),
            "labels": labels,
            "status": getattr(container, "status", "unknown"),
            "engine": "steam" if client is not self.client else "host",
        }

    def _resolve_casaos_api_base(self) -> str | None:
        """Return a CasaOS AppManagement base URL (ending in /v2/app_management).

        Supports CASAOS_API_BASE set to any of:
        - http(s)://host
        - http(s)://host/v2
        - http(s)://host/v2/app_management
        - http(s)://host/v2/app_management/compose

        Prefer explicit CASAOS_API_BASE; otherwise try common Docker hostnames.
        """

        def _normalize_base(raw: str) -> str:
            raw = (raw or "").strip().rstrip("/")
            if not raw:
                return raw
            if "://" not in raw and not raw.startswith("/"):
                raw = f"http://{raw}"
            if raw.endswith("/compose"):
                raw = raw[: -len("/compose")]
            if raw.endswith("/v2/app_management"):
                return raw
            if raw.endswith("/v2"):
                return f"{raw}/app_management"
            marker = "/v2/app_management"
            if marker in raw:
                idx = raw.index(marker)
                return raw[: idx + len(marker)]
            return f"{raw}/v2/app_management"

        if CASAOS_API_BASE:
            return _normalize_base(CASAOS_API_BASE)

        candidates = [
            "http://host.docker.internal/v2/app_management",
            "http://gateway.docker.internal/v2/app_management",
            "http://172.17.0.1/v2/app_management",
        ]
        for base in candidates:
            try:
                base = _normalize_base(base)
                r = requests.get(f"{base}/compose", timeout=2)
                if r.status_code in (200, 401, 403):
                    return base.rstrip("/")
            except Exception:
                continue
        return None

    def _resolve_steam_port_binding(self, ports: list[dict]) -> dict[str, int]:
        """Resolve host port bindings for Steam servers.

        Returns a dict in Docker SDK port binding format: {"27015/udp": 27015, ...}
        Preserves offsets from the primary port when only a single preferred host port is provided.
        """
        port_binding: dict[str, int] = {}
        used_by_proto = self._get_used_host_ports_by_protocol(only_minecraft=False)

        normalized_ports: list[dict] = []
        for p in ports or []:
            raw_container = p.get("container")
            if raw_container is None:
                raise ValueError(f"Missing container port in: {p}")
            cport = int(raw_container)
            proto = (p.get("protocol") or "tcp").lower()
            preferred_raw = p.get("host")
            preferred_int = None
            if preferred_raw is not None:
                try:
                    preferred_int = int(preferred_raw)
                except Exception:
                    preferred_int = None
            normalized_ports.append({"cport": cport, "proto": proto, "preferred": preferred_int})

        explicit_host_count = sum(1 for item in normalized_ports if (item.get("preferred") or 0) > 0)
        has_non_primary_explicit = any(
            (item.get("preferred") or 0) > 0 and idx != 0 for idx, item in enumerate(normalized_ports)
        )

        def _bind_single_port(cport: int, proto: str, preferred: int | None, *, allow_fallback: bool) -> int:
            host_val = self._pick_available_port_for_protocol(
                proto=proto,
                used_by_proto=used_by_proto,
                preferred=preferred,
                start=max(1, int(preferred or cport)),
                end=65535,
                allow_fallback=allow_fallback,
            )
            used_by_proto.setdefault(proto, set()).add(host_val)
            return host_val

        if has_non_primary_explicit and explicit_host_count > 0:
            for item in normalized_ports:
                cport = int(item["cport"])
                proto = str(item["proto"]).lower()
                preferred = item.get("preferred")
                allow_fallback = False if (preferred and preferred > 0) else True
                host_val = _bind_single_port(
                    cport,
                    proto,
                    (preferred if preferred and preferred > 0 else cport),
                    allow_fallback=allow_fallback,
                )
                port_binding[f"{cport}/{proto}"] = host_val
        else:
            base_cport = int(normalized_ports[0]["cport"]) if normalized_ports else 0
            requested_base = normalized_ports[0].get("preferred")
            strict_base = bool(requested_base and int(requested_base) > 0)
            base_candidate = int(requested_base) if strict_base else base_cport

            offsets = [int(item["cport"]) - base_cport for item in normalized_ports] if normalized_ports else [0]
            min_offset = min(offsets) if offsets else 0
            max_offset = max(offsets) if offsets else 0
            candidate_min = 1 - min_offset
            candidate_max = 65535 - max_offset
            if base_candidate < candidate_min or base_candidate > candidate_max:
                raise RuntimeError(
                    f"Host port base {base_candidate} is out of range for this game's port set (valid base: {candidate_min}-{candidate_max})."
                )

            def _block_is_free(base_host: int) -> bool:
                for item in normalized_ports:
                    cport = int(item["cport"])
                    proto = str(item["proto"]).lower()
                    desired = base_host + (cport - base_cport)
                    if desired in used_by_proto.setdefault(proto, set()):
                        return False
                return True

            chosen_base = base_candidate
            if strict_base:
                if not _block_is_free(chosen_base):
                    conflicts: list[str] = []
                    for item in normalized_ports:
                        cport = int(item["cport"])
                        proto = str(item["proto"]).lower()
                        desired = chosen_base + (cport - base_cport)
                        if desired in used_by_proto.setdefault(proto, set()):
                            conflicts.append(f"{desired}/{proto}")
                    raise RuntimeError(
                        f"Requested host port {chosen_base} cannot be used (conflicts: {', '.join(conflicts)})."
                    )
            else:
                start_base = max(chosen_base, candidate_min)
                b = start_base
                while b <= candidate_max and not _block_is_free(b):
                    b += 1
                if b > candidate_max:
                    raise RuntimeError("No available host ports found for the Steam server's required port set")
                chosen_base = b

            for item in normalized_ports:
                cport = int(item["cport"])
                proto = str(item["proto"]).lower()
                host_val = chosen_base + (cport - base_cport)
                used_by_proto.setdefault(proto, set()).add(host_val)
                port_binding[f"{cport}/{proto}"] = host_val

        return port_binding

    def create_steam_compose_app(
        self,
        *,
        name: str,
        image: str,
        ports: list[dict],
        env: dict | None = None,
        volume: dict | None = None,
        command: list[str] | None = None,
        restart_policy: dict | None = None,
        extra_labels: dict | None = None,
    ) -> dict:
        """Install a Steam server as a CasaOS v2 compose app.

        Requires CASAOS_API_TOKEN to be configured (and optionally CASAOS_API_BASE).
        This avoids the container showing under CasaOS "Legacy-App".
        """
        base = self._resolve_casaos_api_base()
        if not base:
            raise RuntimeError("CasaOS API base not reachable; set CASAOS_API_BASE")

        token = CASAOS_API_TOKEN
        if not token:
            raise RuntimeError("CASAOS_API_TOKEN not set; cannot install compose app")

        auth_values: list[str] = []
        token_stripped = token.strip()
        if token_stripped:
            auth_values.append(token_stripped)
        if token_stripped and not token_stripped.lower().startswith("bearer "):
            auth_values.append(f"Bearer {token_stripped}")

        # Compute port bindings.
        port_binding = self._resolve_steam_port_binding(ports)

        # Compose ports list.
        compose_ports: list[str] = []
        first_host_port: str | None = None
        first_protocol: str | None = None
        for key, host_port in port_binding.items():
            cport, proto = key.split("/", 1)
            proto = (proto or "tcp").lower()
            compose_ports.append(f"{host_port}:{cport}/{proto}")
            if first_host_port is None:
                first_host_port = str(host_port)
                first_protocol = proto

        casaos_app_id = self._resolve_casaos_app_id()

        # Labels for Lynx discovery.
        labels = {
            "steam.server": "true",
            "steam.name": name,
            "origin": "lynx",
            "name": name,
            "custom_id": f"{casaos_app_id}-{name}",
        }
        if first_protocol:
            labels["protocol"] = first_protocol
        labels.setdefault("web", first_host_port or "")
        if extra_labels:
            for k, v in extra_labels.items():
                try:
                    labels[str(k)] = str(v)
                except Exception:
                    pass

        # Volumes.
        compose_volumes: list[str] = []
        if volume and volume.get("host") and volume.get("container"):
            host_path = str(volume["host"])
            container_path = str(volume["container"])
            # Default to rw.
            compose_volumes.append(f"{host_path}:{container_path}:rw")

        # Environment.
        env_map = {str(k): str(v) for k, v in (env or {}).items() if v is not None}

        # Compose app id / project name. Keep it deterministic and CasaOS-friendly.
        def _slugify(raw: str) -> str:
            raw = (raw or "").strip().lower()
            out = []
            for ch in raw:
                if ch.isalnum() or ch in ("-", "_"):
                    out.append(ch)
                else:
                    out.append("-")
            s = "".join(out).strip("-")
            while "--" in s:
                s = s.replace("--", "-")
            return s or "steam-server"

        app_id = _slugify(f"steam-{name}")
        service_name = "server"

        # Minimal Compose YAML with x-casaos.
        # Use YAML-friendly indentation and avoid external deps.
        yaml_lines: list[str] = []
        yaml_lines.append(f"name: {app_id}")
        yaml_lines.append("x-casaos:")
        yaml_lines.append(f"  main: {service_name}")
        yaml_lines.append("  category: Games")
        yaml_lines.append("  title:")
        yaml_lines.append(f"    en_us: {name}")
        if first_host_port:
            yaml_lines.append(f"  port_map: \"{first_host_port}\"")
        yaml_lines.append("services:")
        yaml_lines.append(f"  {service_name}:")
        yaml_lines.append(f"    image: {image}")
        yaml_lines.append(f"    container_name: {name}")
        yaml_lines.append("    restart: unless-stopped")
        if compose_ports:
            yaml_lines.append("    ports:")
            for p in compose_ports:
                yaml_lines.append(f"      - \"{p}\"")
        if env_map:
            yaml_lines.append("    environment:")
            for k, v in env_map.items():
                # Quote values to avoid YAML parsing surprises.
                vv = v.replace('"', '\\"')
                yaml_lines.append(f"      {k}: \"{vv}\"")
        if compose_volumes:
            yaml_lines.append("    volumes:")
            for v in compose_volumes:
                yaml_lines.append(f"      - \"{v}\"")
        if command:
            yaml_lines.append("    command:")
            for part in command:
                part = str(part).replace('"', '\\"')
                yaml_lines.append(f"      - \"{part}\"")
        yaml_lines.append("    labels:")
        for k, v in labels.items():
            vv = str(v).replace('"', '\\"')
            yaml_lines.append(f"      {k}: \"{vv}\"")

        compose_yaml = "\n".join(yaml_lines) + "\n"

        # Install the compose app.
        # CasaOS AppManagement v2 expects raw compose YAML in the request body.
        url = f"{base}/compose?check_port_conflict=true"
        resp = None
        last_exc: Exception | None = None
        for auth in auth_values or [token_stripped]:
            headers = {
                "Authorization": auth,
                "Content-Type": "application/yaml",
            }
            try:
                resp = requests.post(url, data=compose_yaml.encode("utf-8"), headers=headers, timeout=15)
            except Exception as exc:
                last_exc = exc
                continue
            if resp.status_code not in (401, 403):
                break

        if resp is None:
            raise RuntimeError(f"CasaOS compose install request failed: {last_exc}")

        if resp.status_code >= 400:
            body = (resp.text or "").strip()
            raise RuntimeError(
                f"CasaOS compose install failed: HTTP {resp.status_code} at {url}. "
                f"Response: {body[:2000]}"
            )

        # Best-effort: wait briefly for the container to appear.
        self._ensure_client()
        container = None
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                container = self.client.containers.get(name)
                break
            except Exception:
                time.sleep(0.5)

        resolved_ports: dict[str, int] = {}
        status = "unknown"
        if container is not None:
            try:
                container.reload()
                status = getattr(container, "status", "unknown")
                port_info = ((getattr(container, "attrs", {}) or {}).get("NetworkSettings", {}) or {}).get("Ports") or {}
                for key, bindings in port_info.items():
                    if not bindings:
                        continue
                    host_binding = bindings[0] if isinstance(bindings, list) and bindings else None
                    if not host_binding:
                        continue
                    host_port = host_binding.get("HostPort")
                    if not host_port:
                        continue
                    try:
                        resolved_ports[key] = int(host_port)
                    except Exception:
                        resolved_ports[key] = host_port
            except Exception:
                pass

        return {
            "id": getattr(container, "id", None) if container is not None else None,
            "name": name,
            "image": image,
            "ports": resolved_ports or {k: v for k, v in port_binding.items()},
            "labels": labels,
            "status": status,
            "casaos_compose_app": app_id,
        }


    def start_server(self, container_id):
        """Start the container and attempt a lightweight readiness check.
        Does not block for long; callers can poll logs/status if needed.
        """
        container = self._get_container_any(container_id)
        try:
            container.start()
            # Briefly wait and refresh status
            time.sleep(0.5)
            container.reload()
        except Exception as e:
            logger.error(f"Failed to start container {container_id}: {e}")
        return {"id": container.id, "status": container.status}

    def stop_server(self, container_id, timeout: int = 60, force: bool = False):
        """Gracefully stop the Minecraft server inside the container.
        Attempts in order: RCON -> attach_socket -> stdin, then Docker stop/kill as fallback.
        """
        container = self._get_container_any(container_id)
        try:
            container.reload()
        except Exception:
            pass

        if getattr(container, "status", "unknown") != "running":
            return {"id": container.id, "status": container.status, "method": "noop"}

        method_used = None
        try:
            result = self.send_command(container_id, "stop")
            method_used = result.get("method") if isinstance(result, dict) else None
        except Exception as e:
            logger.warning(f"Failed to send graceful stop to {container_id}: {e}")

        # Wait for graceful shutdown
        deadline = time.time() + max(1, int(timeout))
        while time.time() < deadline:
            try:
                container.reload()
                if container.status != "running":
                    return {"id": container.id, "status": container.status, "method": method_used or "graceful"}
            except Exception:
                # If reload fails, assume it may be stopping; keep waiting a bit
                pass
            time.sleep(1)

        # Fallback to Docker stop/kill
        try:
            if force:
                container.kill()
            else:
                container.stop(timeout=10)
        except Exception as e:
            logger.error(f"Docker stop/kill failed for {container_id}: {e}")

        try:
            container.reload()
        except Exception:
            pass
        return {"id": container.id, "status": container.status, "method": method_used or ("kill" if force else "docker-stop")}

    def restart_server(self, container_id, stop_timeout: int = 60):
        """Restart the server using a graceful stop then start."""
        try:
            self.stop_server(container_id, timeout=stop_timeout, force=False)
        except Exception as e:
            logger.warning(f"Graceful stop failed during restart for {container_id}: {e}")
        # Start again
        return self.start_server(container_id)

    def kill_server(self, container_id):
        container = self._get_container_any(container_id)
        container.kill()
        return {"id": container.id, "status": container.status}

    def delete_server(self, container_id):
        """Delete the server's container AND its directory under SERVERS_ROOT if present.

        container_id may be a container ID or the server name. We'll prefer container.name when found.
        """
        name_hint = str(container_id)
        # Remove container first
        try:
            container = self._get_container_any(container_id)
            try:
                name_hint = getattr(container, 'name', name_hint)
            except Exception:
                pass
            try:
                container.remove(force=True)
            except Exception:
                pass
        except Exception:
            container = None
        # Remove directory (prefer using name)
        removed_dir = False
        try:
            server_dir = SERVERS_ROOT / name_hint
            target_removed = False
            if server_dir.exists():
                import shutil
                # Handle symlinked Steam directories without wiping shared targets unexpectedly
                if server_dir.is_symlink():
                    try:
                        target = server_dir.resolve()
                    except Exception:
                        target = None
                    server_dir.unlink(missing_ok=True)
                    target_removed = True
                    if target and target.exists() and target.is_dir():
                        shutil.rmtree(target, ignore_errors=True)
                        target_removed = not target.exists()
                elif server_dir.is_dir():
                    shutil.rmtree(server_dir, ignore_errors=True)
                    target_removed = not server_dir.exists()
            if not target_removed:
                # Fallback: if name_hint was an ID but directory uses container name, try to list possible match
                alt_dir = SERVERS_ROOT / str(container_id)
                if alt_dir.exists():
                    import shutil
                    if alt_dir.is_symlink():
                        try:
                            target = alt_dir.resolve()
                        except Exception:
                            target = None
                        alt_dir.unlink(missing_ok=True)
                        target_removed = True
                        if target and target.exists() and target.is_dir():
                            shutil.rmtree(target, ignore_errors=True)
                            target_removed = target_removed or (not target.exists())
                    elif alt_dir.is_dir():
                        shutil.rmtree(alt_dir, ignore_errors=True)
                        target_removed = target_removed or (not alt_dir.exists())
            removed_dir = target_removed
        except Exception as e:
            logger.warning(f"Failed to remove server directory for {container_id}: {e}")
        return {"id": container_id, "deleted": True, "dir_removed": removed_dir}

    def recreate_server_with_env(self, container_id: str, env_overrides: dict | None = None) -> dict:
        """Stop and remove the existing container, then recreate it from its server directory
        with the given environment overrides.
        """
        try:
            container = self.client.containers.get(container_id)
            name = container.name
            attrs = container.attrs or {}
            config = attrs.get("Config", {})
            env_list = config.get("Env", []) or []
            env_map = {}
            for e in env_list:
                if "=" in e:
                    k, v = e.split("=", 1)
                    env_map[k] = v
            min_ram = env_map.get("MIN_RAM", "1G")
            max_ram = env_map.get("MAX_RAM", "2G")

            # Detect host port for 25565/tcp
            host_port = None
            ports = (attrs.get("NetworkSettings", {}) or {}).get("Ports", {}) or {}
            mapping = ports.get(f"{MINECRAFT_PORT}/tcp")
            if mapping and isinstance(mapping, list) and len(mapping) > 0:
                host_port = int(mapping[0].get("HostPort")) if mapping[0].get("HostPort") else None

            # Stop and remove existing
            try:
                container.stop(timeout=5)
            except Exception:
                pass
            try:
                container.remove(force=True)
            except Exception:
                pass

            # Recreate with overrides
            extra_env = env_overrides or {}
            return self.create_server_from_existing(name=name, host_port=host_port, min_ram=min_ram, max_ram=max_ram, extra_env=extra_env)
        except docker.errors.NotFound:
            raise RuntimeError(f"Container {container_id} not found")
        except Exception as e:
            raise RuntimeError(f"Failed to recreate server container: {e}")

    def rename_server(self, old_name: str, new_name: str) -> dict:
        """Rename a server: directory, metadata, and container.

        Steps:
        1. Collect current host port, RAM settings, and env overrides.
        2. Stop & remove existing container (if any).
        3. Rename the server directory.
        4. Update server_meta.json (name + previous_names).
        5. Recreate container under new name preserving settings.
        """
        old_dir = SERVERS_ROOT / old_name
        new_dir = SERVERS_ROOT / new_name
        if not old_dir.exists() or not old_dir.is_dir():
            raise RuntimeError(f"Server directory {old_dir} does not exist")
        if new_dir.exists():
            raise RuntimeError(f"Target server directory {new_dir} already exists")

        # Extract metadata
        meta_path = old_dir / "server_meta.json"
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8") or "{}")
            except Exception:
                meta = {}
        min_ram = meta.get("min_ram") or "1G"
        max_ram = meta.get("max_ram") or "2G"
        env_overrides = meta.get("env_overrides") or {}
        if not isinstance(env_overrides, dict):
            env_overrides = {}

        # Try to capture host port from existing container
        host_port: int | None = None
        container = None
        try:
            container = self.client.containers.get(old_name)
            try:
                attrs = container.attrs or {}
                ports = (attrs.get("NetworkSettings", {}) or {}).get("Ports", {}) or {}
                mapping = ports.get(f"{MINECRAFT_PORT}/tcp")
                if mapping and isinstance(mapping, list) and mapping and mapping[0].get("HostPort"):
                    host_port = int(mapping[0]["HostPort"])
            except Exception:
                host_port = None
        except Exception:
            container = None

        if container is not None:
            try:
                try:
                    container.stop(timeout=10)
                except Exception:
                    pass
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            except Exception:
                pass

        # Rename directory
        old_dir.rename(new_dir)

        # Update metadata name/history
        try:
            new_meta = dict(meta or {})
            prev = new_meta.get("previous_names") or []
            if isinstance(prev, list):
                if old_name not in prev:
                    prev.append(old_name)
                new_meta["previous_names"] = prev
            new_meta["name"] = new_name
            (SERVERS_ROOT / new_name / "server_meta.json").write_text(json.dumps(new_meta), encoding="utf-8")
        except Exception:
            pass

        # Recreate container with preserved settings
        result = self.create_server_from_existing(
            name=new_name,
            host_port=host_port,
            min_ram=min_ram,
            max_ram=max_ram,
            extra_env=env_overrides,
        )
        return {"old_name": old_name, "new_name": new_name, "container": result}

    def get_server_logs(self, container_id, tail: int = 200):
        container = self._get_container_any(container_id)
        logs = container.logs(tail=tail).decode(errors="ignore")
        return {"id": container.id, "logs": logs}

    def send_command(self, container_id: str, command: str) -> dict:
        """
        Sendet einen Befehl an den Minecraft-Server im Container.
        Versucht zuerst RCON, dann attach_socket, dann stdin-Fallback.
        """
        container = self._get_container_any(container_id)

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
            container = self._get_container_any(container_id)
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
            # Single-sample CPU calculation using precpu_stats to avoid delay
            stats_now = container.stats(stream=False)
            cpu_stats = stats_now.get("cpu_stats", {}) or {}
            precpu_stats = stats_now.get("precpu_stats", {}) or {}
            cpu_usage_now = ((cpu_stats.get("cpu_usage", {}) or {}).get("total_usage", 0))
            cpu_usage_prev = ((precpu_stats.get("cpu_usage", {}) or {}).get("total_usage", 0))
            system_now = cpu_stats.get("system_cpu_usage", 0)
            system_prev = precpu_stats.get("system_cpu_usage", 0)
            cpu_delta = cpu_usage_now - cpu_usage_prev
            system_delta = system_now - system_prev
            online_cpus = cpu_stats.get("online_cpus")
            if online_cpus is None:
                per_cpu = (cpu_stats.get("cpu_usage", {}) or {}).get("percpu_usage", [])
                online_cpus = len(per_cpu) or 1
            cpu_percent = 0.0
            if system_delta > 0 and cpu_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * online_cpus * 100.0

            # RAM calculation
            mem_usage = stats_now["memory_stats"].get("usage", 0)
            # Remove cache from memory usage if present (for more accurate "used" memory)
            if "stats" in stats_now["memory_stats"] and "cache" in stats_now["memory_stats"]["stats"]:
                mem_usage -= stats_now["memory_stats"]["stats"]["cache"]
            mem_limit = stats_now["memory_stats"].get("limit", 1)
            mem_percent = (mem_usage / mem_limit) * 100.0 if mem_limit else 0.0
            mem_usage_mb = mem_usage / (1024 * 1024)
            mem_limit_mb = mem_limit / (1024 * 1024)

            # Network calculation
            net_stats = stats_now.get("networks", {})
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

    def get_server_stats_cached(self, container_id: str, ttl_seconds: int = 3) -> dict:
        """Return cached stats if fresh; otherwise fetch and cache."""
        now = time.time()
        cached = self._stats_cache.get(container_id)
        if cached:
            ts, data = cached
            if now - ts <= ttl_seconds:
                return data
        data = self.get_server_stats(container_id)
        self._stats_cache[container_id] = (now, data)
        return data

    def get_bulk_server_stats(self, ttl_seconds: int = 3) -> dict:
        """Return stats for all labeled servers in one call, using cache for speed."""
        stats: dict[str, dict] = {}
        try:
            servers = self.list_servers()
            for s in servers:
                cid = s.get("id")
                if cid:
                    stats[cid] = self.get_server_stats_cached(cid, ttl_seconds)
        except Exception as e:
            logger.warning(f"Bulk stats failed: {e}")
        return stats

    def get_player_info(self, container_id: str) -> dict:
        """Retrieve player info using mcstatus first, then RCON, then fallbacks.

        Returns a dict: { 'online': int, 'max': int, 'names': list[str], 'method': str }
        method will be one of: 'mcstatus', 'rcon', 'attach_socket', 'stdin', 'logs', 'none'
        """
        try:
            container = self._get_container_any(container_id)
            env_vars = container.attrs.get("Config", {}).get("Env", [])
            env_dict = dict(var.split("=", 1) for var in env_vars if "=" in var)

            network_settings = container.attrs.get("NetworkSettings", {}).get("Ports", {}) or {}

            # --- 1️⃣ Try mcstatus JavaServer.status on mapped Minecraft port (non-intrusive) ---
            try:
                primary = network_settings.get("25565/tcp") if isinstance(network_settings, dict) else None
                host_port = None
                if primary and isinstance(primary, list) and primary and primary[0].get("HostPort"):
                    try:
                        host_port = int(primary[0]["HostPort"])
                    except Exception:
                        host_port = primary[0].get("HostPort")

                if host_port:
                    from mcstatus import JavaServer

                    server = JavaServer("localhost", port=int(host_port))
                    status = server.status(timeout=2)
                    players = getattr(status, "players", None)

                    online = int(getattr(players, "online", 0) or 0) if players is not None else 0
                    maxp = int(getattr(players, "max", 0) or 0) if players is not None else 0

                    names: List[str] = []
                    sample = getattr(players, "sample", None) if players is not None else None
                    if sample:
                        for p in sample:
                            nm = None
                            try:
                                nm = getattr(p, "name", None)
                            except Exception:
                                nm = None
                            if nm is None and isinstance(p, dict):
                                nm = p.get("name")
                            if nm:
                                names.append(str(nm))

                    return {"online": online, "max": maxp, "names": names, "method": "mcstatus"}
            except Exception as mc_err:
                logger.debug(f"mcstatus failed for {container_id}: {mc_err}")

            # --- 2️⃣ Try RCON if enabled ---
            try:
                from mcrcon import MCRcon

                rcon_enabled = env_dict.get("ENABLE_RCON", "false").lower() == "true"
                rcon_password = env_dict.get("RCON_PASSWORD", "")
                rcon_port_env = env_dict.get("RCON_PORT", "25575")

                rcon_port = None
                for port, mappings in (network_settings or {}).items():
                    if port.endswith("/tcp") and (port.startswith(str(rcon_port_env)) or port.startswith("25575")):
                        if mappings and isinstance(mappings, list) and len(mappings) > 0:
                            hostp = mappings[0].get("HostPort") if isinstance(mappings[0], dict) else None
                            rcon_port = int(hostp) if hostp else None
                            break

                if rcon_enabled and rcon_password and rcon_port:
                    with MCRcon("localhost", rcon_password, port=rcon_port, timeout=2) as mcr:
                        output = mcr.command("list") or ""
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

                        return {"online": online, "max": maxp, "names": names, "method": "rcon"}
            except Exception as rcon_err:
                logger.debug(f"RCON list failed for {container_id}: {rcon_err}")

            # --- 3️⃣ Try non-RCON console methods (attach_socket / stdin) for a 'list' command ---
            try:
                # attach_socket attempt
                try:
                    sock = container.attach_socket(params={
                        "stdin": True,
                        "stdout": True,
                        "stderr": True,
                        "stream": True
                    })
                    sock._sock.setblocking(True)
                    cmd_with_newline = "list\n"
                    sock._sock.send(cmd_with_newline.encode("utf-8"))
                    time.sleep(0.2)
                    try:
                        output = sock._sock.recv(4096).decode(errors="ignore")
                    except Exception:
                        output = ""
                    sock.close()
                    text = str(output)
                    import re as _re2
                    m = _re2.search(r"There are\s+(\d+)\s+of a max of\s+(\d+)\s+players online", text)
                    if not m:
                        m = _re2.search(r"(\d+)\s*/\s*(\d+)\s*players? online", text)
                    if m:
                        online = int(m.group(1))
                        maxp = int(m.group(2))
                        colon_idx = text.find(":")
                        names = []
                        if colon_idx != -1 and colon_idx + 1 < len(text):
                            names_str = text[colon_idx + 1:].strip()
                            if names_str:
                                names = [n.strip() for n in names_str.split(",") if n.strip()]
                        return {"online": online, "max": maxp, "names": names, "method": "attach_socket"}
                except Exception:
                    pass

                # stdin fallback
                try:
                    safe_command = "list\n"
                    exec_cmd = ["sh", "-c", f'echo {shlex.quote(safe_command)} > /proc/1/fd/0']
                    exit_code, output = container.exec_run(exec_cmd)
                    if exit_code == 0:
                        return {"online": 0, "max": 0, "names": [], "method": "stdin"}
                except Exception:
                    pass
            except Exception:
                pass

            # --- 4️⃣ If nothing worked, return none/empty ---
            return {"online": 0, "max": 0, "names": [], "method": "none"}
        except Exception as e:
            logger.warning(f"Failed to get player info for container {container_id}: {e}")
            return {"online": 0, "max": 0, "names": [], "method": "error"}

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
            
            # Update container labels (keep labels up-to-date)
            current_labels = (container.attrs.get("Config", {}) or {}).get("Labels", {}) or {}
            current_labels["mc.java_version"] = java_version
            current_labels["mc.java_bin"] = f"/usr/local/bin/java{java_version}"
            current_labels["mc.env.JAVA_VERSION"] = java_version
            current_labels["mc.env.JAVA_BIN"] = f"/usr/local/bin/java{java_version}"

            try:
                container.update(labels=current_labels)
            except Exception:
                # Non-fatal: continue to recreate below
                pass

            # Now recreate the container with the updated environment so the change actually takes effect
            try:
                env_overrides = {
                    # Override-style names expected by runtime-entrypoint
                    "JAVA_VERSION_OVERRIDE": java_version,
                    "JAVA_BIN_OVERRIDE": f"/usr/local/bin/java{java_version}",
                    # Also include legacy names for backward compatibility
                    "JAVA_VERSION": java_version,
                    "JAVA_BIN": f"/usr/local/bin/java{java_version}",
                }
                recreate_result = self.recreate_server_with_env(container_id, env_overrides=env_overrides)
                logger.info(f"Recreated container {container_id} to apply Java version {java_version}")
                return {
                    "success": True,
                    "message": f"Java version updated to {java_version} and container recreated.",
                    "java_version": java_version,
                    "java_bin": f"/usr/local/bin/java{java_version}",
                    "recreate_result": recreate_result,
                }
            except Exception as e:
                logger.error(f"Failed to recreate container {container_id} after updating Java env: {e}")
                return {
                    "success": False,
                    "message": f"Labels updated but recreate failed: {e}. Container restart may be required.",
                    "error": str(e),
                    "java_version": java_version,
                    "java_bin": f"/usr/local/bin/java{java_version}",
                    "restart_required": True,
                }
            
        except docker.errors.NotFound:
            logger.error(f"Container {container_id} not found when updating Java version")
            raise RuntimeError(f"Container {container_id} not found")
        except Exception as e:
            logger.error(f"Error updating Java version for container {container_id}: {e}")
            raise RuntimeError(f"Failed to update Java version: {e}")

    def update_server_java_args(self, container_id: str, java_args: str | None) -> dict:
        """Update custom Java arguments (JAVA_OPTS) for a server and recreate the container."""
        try:
            container = self.client.containers.get(container_id)
            server_name = container.name or container_id

            raw = java_args or ""
            normalized = " ".join(raw.replace("\r", " ").split())
            if len(normalized) > 4096:
                raise ValueError("java_args too long (max 4096 characters when normalized)")

            # Load and update metadata env_overrides
            meta_path = SERVERS_ROOT / server_name / "server_meta.json"
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8") or "{}") if meta_path.exists() else {}
            except Exception:
                meta = {}

            env_overrides = meta.get("env_overrides") or {}
            if not isinstance(env_overrides, dict):
                env_overrides = {}
            merged = {str(k): str(v) for k, v in env_overrides.items() if v is not None}
            if normalized:
                merged["JAVA_OPTS"] = normalized
            else:
                merged.pop("JAVA_OPTS", None)

            meta["env_overrides"] = merged
            try:
                meta_path.parent.mkdir(parents=True, exist_ok=True)
                meta_path.write_text(json.dumps(meta), encoding="utf-8")
            except Exception:
                pass

            # Update labels to reflect the new value (best effort)
            current_labels = (container.attrs.get("Config", {}) or {}).get("Labels", {}) or {}
            if normalized:
                current_labels["mc.env.JAVA_OPTS"] = normalized
            else:
                current_labels.pop("mc.env.JAVA_OPTS", None)
            try:
                container.update(labels=current_labels)
            except Exception:
                pass

            # Recreate container with updated env overrides so runtime-entrypoint sees the change
            recreate_result = self.recreate_server_with_env(container_id, env_overrides=merged or None)
            return {
                "success": True,
                "java_args": normalized,
                "recreate_result": recreate_result,
            }
        except docker.errors.NotFound:
            raise RuntimeError(f"Container {container_id} not found")
        except Exception as e:
            raise RuntimeError(f"Failed to update Java arguments: {e}")