import shutil
from pathlib import Path
import requests
from server_providers.providers import get_provider
import logging

logger = logging.getLogger(__name__)

def stream_download(url: str, dest_file: Path):
    logger.info(f"Downloading {url} to {dest_file}")
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            
            # Check content type to ensure we're getting a JAR file
            content_type = r.headers.get('content-type', '').lower()
            if 'application/json' in content_type or 'text/html' in content_type:
                preview = r.raw.read(512)
                logger.error(f"Received non-binary response instead of JAR from {url}; content-type={content_type}; preview={preview[:200]!r}")
                raise ValueError(f"Download URL returned non-JAR content: {content_type}")
            elif 'application/java-archive' in content_type or 'application/octet-stream' in content_type or content_type == '':
                logger.info(f"Received JAR-like content type: {content_type or 'unknown'}")
            else:
                logger.warning(f"Unexpected content type: {content_type}, proceeding anyway")
            
            with open(dest_file, "wb") as f:
                shutil.copyfileobj(r.raw, f)
        
        file_size = dest_file.stat().st_size
        logger.info(f"Download complete, size: {file_size} bytes")
        
        # Validate file size (more lenient for different server types)
        if file_size < 1024 * 5:  # Less than 5KB
            logger.error(f"Downloaded file is too small ({file_size} bytes), likely corrupted")
            raise ValueError(f"Downloaded file is too small ({file_size} bytes), expected at least 5KB")
        
        # Validate JAR (ZIP) magic header 'PK\x03\x04'
        with open(dest_file, 'rb') as f:
            magic = f.read(4)
        if magic[:2] != b'PK':
            logger.error(f"Downloaded file does not look like a JAR (missing PK header): magic={magic!r}")
            raise ValueError("Downloaded file is not a valid JAR (ZIP) archive")
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Download failed for {url}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during download: {e}")
        raise

def prepare_server_files(server_type: str, version: str, dest_dir: Path, loader_version: str = None, installer_version: str = None):
    logger.info(f"Preparing {server_type} server v{version} in {dest_dir}")
    provider = get_provider(server_type)
    
    try:
        # Pass loader_version and installer_version to provider if supported
        if hasattr(provider, 'get_download_url_with_loader'):
            # Try signature with installer_version
            try:
                url = provider.get_download_url_with_loader(version, loader_version, installer_version)
            except TypeError:
                url = provider.get_download_url_with_loader(version, loader_version)
        else:
            url = provider.get_download_url(version)
        logger.info(f"Download URL: {url}")
        
        if server_type in ("forge", "neoforge"):
            installer_name = "forge-installer.jar" if server_type == "forge" else "neoforge-installer.jar"
            installer_path = dest_dir / installer_name
            logger.info(f"Downloading {server_type} installer from {url}")
            stream_download(url, installer_path)
            
            # Verify the installer was downloaded correctly
            if not installer_path.exists() or installer_path.stat().st_size < 1024:
                raise ValueError(f"Downloaded {server_type} installer is invalid or too small")
                
            # For installer-based servers, server.jar will be created when the installer runs
            # We don't need to check for server.jar existence here
            logger.info(f"{server_type} installer downloaded successfully to {installer_path}")
            
            # Accept EULA automatically for installer-based servers
            (dest_dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")
            
            # For installer-based servers, we return the installer path, not the server.jar path
            # The server.jar will be created by the runtime entrypoint when it runs the installer
            logger.info(f"Server files prepared successfully at {installer_path}")
            logger.info(f"Directory contents of {dest_dir}: {list(dest_dir.iterdir())}")
            return installer_path
            
        elif server_type == "fabric":
            # For Fabric, download the server launcher JAR directly
            jar_path = dest_dir / "server.jar"
            logger.info(f"Downloading Fabric server launcher from {url}")
            stream_download(url, jar_path)
            
            # Create a launcher script for Fabric
            launcher_script = dest_dir / "run.sh"
            launcher_content = f"""#!/bin/bash
cd "$(dirname "$0")"
java -jar server.jar server
"""
            launcher_script.write_text(launcher_content, encoding="utf-8")
            try:
                launcher_script.chmod(0o755)  # Make executable
            except Exception as e:
                logger.warning(f"Could not set executable permission on run.sh: {e}")
            
            # Verify Fabric JAR specifically (launcher JARs can be smaller than full servers)
            jar_size = jar_path.stat().st_size
            if jar_size < 1024 * 5:  # Less than 5KB for Fabric launcher
                logger.error(f"Fabric JAR is too small ({jar_size} bytes), likely corrupted")
                raise ValueError(f"Fabric JAR is too small ({jar_size} bytes), expected at least 5KB")
            
            logger.info(f"Fabric server launcher downloaded successfully ({jar_size} bytes)")
        else:
            # For vanilla, paper, purpur, etc.
            jar_path = dest_dir / "server.jar"
            logger.info(f"Downloading {server_type} server JAR from {url}")
            stream_download(url, jar_path)
            
            jar_size = jar_path.stat().st_size
            logger.info(f"{server_type} server JAR downloaded successfully ({jar_size} bytes)")
        
        # Verify download (only for non-installer based servers)
        if server_type not in ("forge", "neoforge"):
            if not jar_path.exists():
                logger.error(f"Server JAR not found at {jar_path} after download")
                logger.error(f"Directory contents of {dest_dir}: {list(dest_dir.iterdir())}")
                raise FileNotFoundError(f"Server JAR not found at {jar_path} after download")
            if jar_path.stat().st_size == 0:
                raise ValueError(f"Downloaded JAR is empty at {jar_path}")
            
            logger.info(f"Server files prepared successfully at {jar_path}")
            logger.info(f"Directory contents of {dest_dir}: {list(dest_dir.iterdir())}")
            
            # Accept EULA automatically
            (dest_dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")
            return jar_path
        
    except Exception as e:
        logger.error(f"Failed to prepare server files: {e}")
        raise