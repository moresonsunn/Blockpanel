from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl
from typing import Optional
from pathlib import Path
import tempfile
import shutil
import zipfile
import requests
import threading
import time
import json
import uuid
from urllib.parse import urlparse

from auth import require_moderator
from models import User
from docker_manager import DockerManager

router = APIRouter(prefix="/modpacks", tags=["modpacks"])

_install_tasks = {}
_install_lock = threading.Lock()

def _push_event(task_id: str, event):
    with _install_lock:
        task = _install_tasks.get(task_id)
        if not task:
            return
        task["events"].append(event)
        if event.get("type") in ("done", "error"):
            task["done"] = True

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
    Supports CurseForge links by resolving the real file URL via the Core API.
    """
    dm = get_docker_manager()

    servers_root = Path("/data/servers")
    target_dir = servers_root / payload.server_name
    if target_dir.exists():
        raise HTTPException(status_code=400, detail="Server directory already exists")

    tmpdir = Path(tempfile.mkdtemp(prefix="modpack_"))
    zip_path = tmpdir / "serverpack.zip"

    def resolve_download_url(raw_url: str) -> tuple[str, dict]:
        """Return (download_url, headers) ready for requests.get.
        If the URL is a CurseForge web download page, use the Core API to resolve the direct file URL.
        """
        u = urlparse(raw_url)
        headers = {
            "User-Agent": "minecraft-controller/1.0",
            "Accept": "application/octet-stream, application/zip, */*",
        }
        host = (u.netloc or "").lower()
        path = (u.path or "")
        if "curseforge.com" in host and "/download/" in path:
            # Expect .../download/<fileId>
            try:
                file_id = path.rstrip("/").split("/")[-1]
                if not file_id.isdigit():
                    return raw_url, headers
                # Use CF Core API to get file info and download URL
                from integrations_store import get_integration_key
                api_key = get_integration_key("curseforge")
                if not api_key:
                    raise HTTPException(status_code=400, detail="CurseForge API key not configured in Settings")
                info = requests.get(
                    f"https://api.curseforge.com/v1/mods/files/{file_id}",
                    headers={
                        "x-api-key": api_key,
                        "Accept": "application/json",
                        "User-Agent": "minecraft-controller/1.0",
                    },
                    timeout=30,
                )
                info.raise_for_status()
                data = info.json().get("data") or {}
                dl = data.get("downloadUrl")
                if not dl:
                    # Fallback to the webpage URL (may still 403)
                    return raw_url, headers
                return dl, headers
            except HTTPException:
                raise
            except Exception as e:
                # Fall back to raw URL
                return raw_url, headers
        return raw_url, headers

    try:
        # Resolve and download
        download_url, headers = resolve_download_url(str(payload.server_pack_url))
        with requests.get(download_url, stream=True, timeout=60, headers=headers) as r:
            if r.status_code == 403 and "curseforge" in download_url:
                # If direct URL still forbidden, provide clearer guidance
                raise HTTPException(status_code=400, detail="Failed to download server pack: CurseForge denied access (403). Ensure a valid CurseForge Core API key is configured and use a valid Server Pack file.")
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

@router.post("/import-upload")
async def import_server_pack_upload(
    server_name: str = Form(...),
    host_port: Optional[int] = Form(None),
    min_ram: str = Form("2G"),
    max_ram: str = Form("4G"),
    file: UploadFile | None = None,
    current_user: User = Depends(require_moderator),
):
    """
    Import a server pack from an uploaded ZIP file and create a server container.
    - Saves the uploaded file to a temp dir
    - Safely extracts contents
    - Moves them into /data/servers/{server_name}
    - Accepts EULA and starts a container using existing files
    """
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    if not file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="Only .zip files are supported")

    dm = get_docker_manager()
    servers_root = Path("/data/servers")
    target_dir = servers_root / server_name
    if target_dir.exists():
        raise HTTPException(status_code=400, detail="Server directory already exists")

    tmpdir = Path(tempfile.mkdtemp(prefix="upload_zip_"))
    zip_path = tmpdir / "serverpack.zip"

    try:
        # Save uploaded file to disk
        with open(zip_path, 'wb') as out_f:
            shutil.copyfileobj(file.file, out_f)

        # Safely extract ZIP into tmpdir/extracted
        extract_dir = tmpdir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        def is_within(base: Path, target: Path) -> bool:
            try:
                target.resolve().relative_to(base.resolve())
                return True
            except Exception:
                return False

        with zipfile.ZipFile(zip_path, 'r') as z:
            for member in z.infolist():
                # Skip directories explicitly handled
                name = member.filename
                if name.endswith('/'):
                    continue
                # Prevent absolute paths or traversal
                dest_path = extract_dir / name
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                if not is_within(extract_dir, dest_path):
                    raise HTTPException(status_code=400, detail="Zip contains invalid paths")
                with z.open(member) as src, open(dest_path, 'wb') as dst:
                    shutil.copyfileobj(src, dst)

        # If there is a single top-level directory, use its contents
        def _single_top_level_dir(base: Path):
            entries = [p for p in base.iterdir()]
            if len(entries) == 1 and entries[0].is_dir():
                return entries[0]
            return None

        src_dir = _single_top_level_dir(extract_dir) or extract_dir
        shutil.move(str(src_dir), str(target_dir))

        # Ensure EULA accepted
        try:
            (target_dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")
        except Exception:
            pass

        result = dm.create_server_from_existing(
            name=server_name,
            host_port=host_port,
            min_ram=min_ram or "2G",
            max_ram=max_ram or "4G",
        )
        return {"message": "Server pack imported", "server": result}
    except HTTPException:
        raise
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid ZIP archive")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to import uploaded server pack: {e}")
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

class InstallRequest(BaseModel):
    provider: str
    pack_id: str
    version_id: Optional[str] = None
    name: str
    host_port: Optional[int] = None
    min_ram: Optional[str] = None
    max_ram: Optional[str] = None

@router.post("/install")
async def install_modpack(req: InstallRequest, current_user: User = Depends(require_moderator)):
    task_id = str(uuid.uuid4())
    with _install_lock:
        _install_tasks[task_id] = {"events": [], "done": False}

    def worker():
        try:
            _push_event(task_id, {"type": "progress", "step": "resolve", "message": "Resolving pack metadata", "progress": 10})

            from catalog_routes import get_providers_live
            prov = get_providers_live()
            provider = prov.get(req.provider)
            if not provider:
                raise RuntimeError("Unknown provider (not configured)")

            # Resolve version
            versions = provider.get_versions(req.pack_id, limit=50)
            v = None
            if req.version_id:
                v = next((x for x in versions if x.get("id") == req.version_id), None)
            if not v and versions:
                v = versions[0]
            if not v:
                raise RuntimeError("No versions available for this pack")

            # Determine .mrpack file
            files = v.get("files") or []
            mr = None
            for f in files:
                fn = (f.get("filename") or "").lower()
                if f.get("primary") or fn.endswith(".mrpack"):
                    mr = f
                    break
            if not mr and files:
                mr = files[0]
            if not mr or not mr.get("url"):
                raise RuntimeError("No downloadable modpack file in this version")

            # Prepare server dir
            servers_root = Path("/data/servers")
            target_dir = servers_root / req.name
            target_dir.mkdir(parents=True, exist_ok=True)

            # Download .mrpack
            _push_event(task_id, {"type": "progress", "step": "download", "message": "Downloading modpack (.mrpack)", "progress": 25})
            tmpdir = Path(tempfile.mkdtemp(prefix="mrpack_"))
            mrpack_path = tmpdir / (mr.get("filename") or "pack.mrpack")
            with requests.get(mr["url"], stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(mrpack_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

            # Extract overrides and parse index
            _push_event(task_id, {"type": "progress", "step": "extract", "message": "Extracting overrides and index", "progress": 40})
            idx = None
            with zipfile.ZipFile(mrpack_path, 'r') as z:
                names = z.namelist()
                # Extract overrides/
                for name in names:
                    if name.startswith("overrides/") and not name.endswith("/"):
                        dest = target_dir / name[len("overrides/"):]
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(name) as src, open(dest, 'wb') as dst:
                            shutil.copyfileobj(src, dst)
                # Read index (modrinth.index.json or index.json)
                index_name = None
                for cand in ("modrinth.index.json", "index.json"):
                    if cand in names:
                        index_name = cand
                        break
                if index_name:
                    with z.open(index_name) as s:
                        idx = json.load(s)

            # Derive loader/mc_version from index dependencies if present
            loader = None
            mc_version = None
            loader_version = None
            if isinstance(idx, dict):
                deps = idx.get("dependencies", {})
                mc_version = deps.get("minecraft") or mc_version
                if deps.get("fabric-loader"):
                    loader = "fabric"
                    loader_version = deps.get("fabric-loader")
                elif deps.get("forge"):
                    loader = "forge"
                    loader_version = deps.get("forge")
                elif deps.get("neoforge"):
                    loader = "neoforge"
                    loader_version = deps.get("neoforge")

            # Download files listed in index (mods/config/etc.)
            if isinstance(idx, dict) and isinstance(idx.get("files"), list):
                _push_event(task_id, {"type": "progress", "step": "mods", "message": "Downloading mods and files", "progress": 55})
                for entry in idx["files"]:
                    path = entry.get("path")
                    downloads = entry.get("downloads") or []
                    if not path or not downloads:
                        continue
                    # Skip client-only files if env marks server unsupported
                    env = entry.get("env") or {}
                    if isinstance(env, dict) and str(env.get("server", "")).lower() == "unsupported":
                        continue
                    dest = target_dir / path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    url0 = downloads[0]
                    try:
                        with requests.get(url0, stream=True, timeout=60) as r:
                            r.raise_for_status()
                            with open(dest, 'wb') as f:
                                for chunk in r.iter_content(chunk_size=8192):
                                    if chunk:
                                        f.write(chunk)
                        # Verify hashes if provided
                        hashes = entry.get("hashes") or {}
                        import hashlib
                        if isinstance(hashes, dict):
                            if hashes.get("sha512"):
                                h = hashlib.sha512()
                                with open(dest, 'rb') as f:
                                    for chunk in iter(lambda: f.read(8192), b""):
                                        h.update(chunk)
                                if h.hexdigest().lower() != str(hashes["sha512"]).lower():
                                    raise ValueError(f"SHA512 mismatch for {path}")
                            elif hashes.get("sha1"):
                                h = hashlib.sha1()
                                with open(dest, 'rb') as f:
                                    for chunk in iter(lambda: f.read(8192), b""):
                                        h.update(chunk)
                                if h.hexdigest().lower() != str(hashes["sha1"]).lower():
                                    raise ValueError(f"SHA1 mismatch for {path}")
                    except Exception as de:
                        # Continue even if a mod fails; log event
                        _push_event(task_id, {"type": "progress", "step": "mods", "message": f"Failed to fetch {path}: {de}", "progress": 58})

            # Fallbacks if not found earlier
            if not loader:
                # Try version loaders array from v
                loaders = v.get("loaders") or []
                for cand in ("fabric", "forge", "neoforge"):
                    if cand in [l.lower() for l in loaders]:
                        loader = cand
                        break
            if not mc_version:
                games = v.get("game_versions") or []
                mc_version = games[0] if games else "1.21"
            if not loader:
                loader = "paper"

            _push_event(task_id, {"type": "progress", "step": "prepare", "message": f"Preparing {loader} server", "progress": 70})

            dm = DockerManager()
            min_ram = req.min_ram or ("2048M" if loader != "paper" else "1024M")
            max_ram = req.max_ram or ("4096M" if loader != "paper" else "2048M")

            def normalize_ram(s: str) -> str:
                s = str(s).upper()
                if s.endswith("G") or s.endswith("M"):
                    return s
                try:
                    n = int(s)
                    return f"{n}M"
                except Exception:
                    return "2048M"

            min_ram_n = normalize_ram(min_ram)
            max_ram_n = normalize_ram(max_ram)

            _push_event(task_id, {"type": "progress", "step": "create", "message": "Creating server container", "progress": 85})

            result = dm.create_server(
                req.name,
                loader,
                mc_version or "1.21",
                req.host_port,
                loader_version,
                min_ram_n,
                max_ram_n,
                None,
                extra_labels={
                    "mc.modpack.provider": req.provider,
                    "mc.modpack.id": str(req.pack_id),
                    "mc.modpack.version_id": str(installVersionId) if 'installVersionId' in locals() and installVersionId else str(v.get("id")),
                }
            )

            _push_event(task_id, {"type": "done", "message": "Installation complete", "server": result})
        except Exception as e:
            _push_event(task_id, {"type": "error", "message": str(e)})
        finally:
            try:
                if 'tmpdir' in locals():
                    shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True).start()
    return {"task_id": task_id}

@router.get("/updates")
async def list_updates():
    from catalog_routes import providers
    dm = DockerManager()
    servers = dm.list_servers()
    updates = []
    for s in servers:
        labels = s.get("labels") or {}
        prov = labels.get("mc.modpack.provider")
        pack_id = labels.get("mc.modpack.id")
        current_ver = labels.get("mc.modpack.version_id")
        if not prov or not pack_id or not current_ver or prov not in providers:
            continue
        try:
            p = providers[prov]
            vers = p.get_versions(pack_id, limit=10)
            latest = vers[0] if vers else None
            if latest and str(latest.get("id")) != str(current_ver):
                updates.append({
                    "server": s.get("name"),
                    "provider": prov,
                    "pack_id": pack_id,
                    "current_version_id": current_ver,
                    "latest_version_id": latest.get("id"),
                    "latest_name": latest.get("name") or latest.get("version_number"),
                })
        except Exception:
            continue
    return {"updates": updates}

@router.post("/update")
async def update_modpack(server_name: str, provider: str, pack_id: str, version_id: str, current_user: User = Depends(require_moderator)):
    # Simplified update: stop, backup, apply new files (overrides+mods), restart
    from catalog_routes import providers
    dm = DockerManager()
    # Find server container id
    target = None
    for s in dm.list_servers():
        if s.get("name") == server_name:
            target = s
            break
    if not target:
        raise HTTPException(status_code=404, detail="Server not found")
    container_id = target.get("id")
    if not container_id:
        raise HTTPException(status_code=400, detail="Container id missing")

    # Stop server
    try:
        dm.stop_server(container_id)
    except Exception:
        pass

    # Backup
    try:
        from backup_manager import create_backup as bk_create
        bk_create(server_name)
    except Exception:
        pass

    # Download and apply new version (reuse logic from install worker in a simplified form)
    p = providers.get(provider)
    if not p:
        raise HTTPException(status_code=400, detail="Provider not configured")
    versions = p.get_versions(pack_id, limit=50)
    v = next((x for x in versions if str(x.get("id")) == str(version_id)), None)
    if not v:
        raise HTTPException(status_code=400, detail="Version not found")
    files = v.get("files") or []
    mr = None
    for f in files:
        fn = (f.get("filename") or "").lower()
        if f.get("primary") or fn.endswith(".mrpack"):
            mr = f
            break
    if not mr and files:
        mr = files[0]
    if not mr or not mr.get("url"):
        raise HTTPException(status_code=400, detail="No downloadable file for version")

    servers_root = Path("/data/servers")
    target_dir = servers_root / server_name
    if not target_dir.exists():
        raise HTTPException(status_code=400, detail="Server directory does not exist")

    tmpdir = Path(tempfile.mkdtemp(prefix="mrpack_update_"))
    try:
        mrpack_path = tmpdir / (mr.get("filename") or "pack.mrpack")
        with requests.get(mr["url"], stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(mrpack_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        # Extract overrides and download files
        idx = None
        with zipfile.ZipFile(mrpack_path, 'r') as z:
            names = z.namelist()
            for name in names:
                if name.startswith("overrides/") and not name.endswith("/"):
                    dest = target_dir / name[len("overrides/"):]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(name) as src, open(dest, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
            index_name = None
            for cand in ("modrinth.index.json", "index.json"):
                if cand in names:
                    index_name = cand
                    break
            if index_name:
                with z.open(index_name) as s:
                    idx = json.load(s)
        if isinstance(idx, dict) and isinstance(idx.get("files"), list):
            for entry in idx["files"]:
                env = entry.get("env") or {}
                if isinstance(env, dict) and str(env.get("server", "")).lower() == "unsupported":
                    continue
                path = entry.get("path")
                downloads = entry.get("downloads") or []
                if not path or not downloads:
                    continue
                dest = target_dir / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                url0 = downloads[0]
                try:
                    with requests.get(url0, stream=True, timeout=60) as r:
                        r.raise_for_status()
                        with open(dest, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                except Exception:
                    continue
        # Update labels to new version
        try:
            container = dm.client.containers.get(container_id)
            labels = (container.attrs.get("Config", {}) or {}).get("Labels", {}) or {}
            labels["mc.modpack.provider"] = provider
            labels["mc.modpack.id"] = str(pack_id)
            labels["mc.modpack.version_id"] = str(version_id)
            container.update(labels=labels)
        except Exception:
            pass
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
    # Start server
    dm.start_server(container_id)
    return {"ok": True}

@router.get("/install/events/{task_id}")
async def install_events(task_id: str):
    def gen():
        idx = 0
        while True:
            with _install_lock:
                task = _install_tasks.get(task_id)
                if not task:
                    yield f"data: {json.dumps({'type':'error','message':'task not found'})}\n\n"
                    break
                events = task["events"]
                done = task.get("done")
            while idx < len(events):
                ev = events[idx]
                idx += 1
                yield f"data: {json.dumps(ev)}\n\n"
            if done:
                break
            time.sleep(0.5)
    return StreamingResponse(gen(), media_type="text/event-stream")

