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
        

        if file_size < 1024 * 5:  
            logger.error(f"Downloaded file is too small ({file_size} bytes), likely corrupted")
            raise ValueError(f"Downloaded file is too small ({file_size} bytes), expected at least 5KB")
        
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
            

            if not installer_path.exists() or installer_path.stat().st_size < 1024:
                raise ValueError(f"Downloaded {server_type} installer is invalid or too small")
                
            logger.info(f"{server_type} installer downloaded successfully to {installer_path}")
            
            (dest_dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")
            
            logger.info(f"Server files prepared successfully at {installer_path}")
            logger.info(f"Directory contents of {dest_dir}: {list(dest_dir.iterdir())}")
            return installer_path
            
        elif server_type == "fabric":

            # Download to the canonical launcher filename and also create server.jar alias for compatibility
            launcher_path = dest_dir / "fabric-server-launch.jar"
            logger.info(f"Downloading Fabric server launcher from {url}")
            stream_download(url, launcher_path)

            # Create/refresh server.jar alias for any tooling that expects it
            jar_path = dest_dir / "server.jar"
            try:
                if jar_path.exists():
                    jar_path.unlink()
                shutil.copy2(launcher_path, jar_path)
                logger.info("Created server.jar alias for Fabric launcher")
            except Exception as e:
                logger.warning(f"Could not create server.jar alias for Fabric launcher: {e}")

            # Simple run helper
            launcher_script = dest_dir / "run.sh"
            launcher_content = f"""#!/bin/bash
cd "$(dirname "$0")"
java -jar fabric-server-launch.jar server
"""
            launcher_script.write_text(launcher_content, encoding="utf-8")
            try:
                launcher_script.chmod(0o755)  
            except Exception as e:
                logger.warning(f"Could not set executable permission on run.sh: {e}")

            # Validate
            jar_size = launcher_path.stat().st_size
            if jar_size < 1024 * 5:  
                logger.error(f"Fabric JAR is too small ({jar_size} bytes), likely corrupted")
                raise ValueError(f"Fabric JAR is too small ({jar_size} bytes), expected at least 5KB")
            
            logger.info(f"Fabric server launcher downloaded successfully ({jar_size} bytes)")
        else:

            jar_path = dest_dir / "server.jar"
            logger.info(f"Downloading {server_type} server JAR from {url}")
            stream_download(url, jar_path)
            
            jar_size = jar_path.stat().st_size
            logger.info(f"{server_type} server JAR downloaded successfully ({jar_size} bytes)")
        

        if server_type not in ("forge", "neoforge"):
            if not jar_path.exists():
                logger.error(f"Server JAR not found at {jar_path} after download")
                logger.error(f"Directory contents of {dest_dir}: {list(dest_dir.iterdir())}")
                raise FileNotFoundError(f"Server JAR not found at {jar_path} after download")
            if jar_path.stat().st_size == 0:
                raise ValueError(f"Downloaded JAR is empty at {jar_path}")
            
            logger.info(f"Server files prepared successfully at {jar_path}")
            logger.info(f"Directory contents of {dest_dir}: {list(dest_dir.iterdir())}")
        
            (dest_dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")
            return jar_path
        
    except Exception as e:
        logger.error(f"Failed to prepare server files: {e}")
        raise