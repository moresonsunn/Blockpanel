from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import Optional
from pathlib import Path
import tempfile
import shutil
import zipfile
import requests

from auth import require_moderator
from models import User
from docker_manager import DockerManager
from database import get_db

router = APIRouter(prefix="/modpacks", tags=["modpacks"])

def get_docker_manager() -> DockerManager:
    return DockerManager()

class ImportServerPackRequest(BaseModel):
    server_name: str
    server_pack_url: HttpUrl
    host_port: Optional[int] = None
    min_ram: Optional[str] = "2G"
    max_ram: Optional[str] = "4G"

@router.post("/import")
async def import_server_pack(
    payload: ImportServerPackRequest,
    current_user: User = Depends(require_moderator),
):
    """
    Download a server pack ZIP from a given URL, extract it into /data/servers/{server_name},
    accept EULA, and create a container using the existing files.
    """
    dm = get_docker_manager()

    servers_root = Path("/data/servers")
    target_dir = servers_root / payload.server_name
    if target_dir.exists():
        raise HTTPException(status_code=400, detail="Server directory already exists")

    tmpdir = Path(tempfile.mkdtemp(prefix="modpack_"))
    zip_path = tmpdir / "serverpack.zip"

    try:
        # Download
        with requests.get(str(payload.server_pack_url), stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        # Extract
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(tmpdir)

        # Move extracted content into target dir
        # Heuristic: If the zip contains a single top-level folder, use its content
        def _single_top_level_dir(base: Path):
            entries = [p for p in base.iterdir()]
            if len(entries) == 1 and entries[0].is_dir():
                return entries[0]
            return None

        src_dir = _single_top_level_dir(tmpdir) or tmpdir
        shutil.move(str(src_dir), str(target_dir))

        # Ensure EULA accepted
        eula = target_dir / "eula.txt"
        eula.write_text("eula=true\n", encoding="utf-8")

        # Start container using runtime, pointing to existing dir
        result = dm.create_server_from_existing(
            name=payload.server_name,
            host_port=payload.host_port,
            min_ram=payload.min_ram or "2G",
            max_ram=payload.max_ram or "4G",
        )
        return {"message": "Server pack imported", "server": result}

    except requests.RequestException as e:
        raise HTTPException(status_code=400, detail=f"Failed to download server pack: {e}")
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Downloaded file is not a valid ZIP archive")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to import server pack: {e}")
    finally:
        # Cleanup temp dir
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

