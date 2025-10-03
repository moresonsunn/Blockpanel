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
import os

from auth import require_moderator
from models import User
from docker_manager import DockerManager
from config import SERVERS_ROOT

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

def _download_to(path: Path, url: str, headers: dict | None = None, timeout: int = 120):
    with requests.get(url, stream=True, timeout=timeout, headers=headers or {}) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

def _purge_client_only_mods(target_dir: Path, push_event=lambda ev: None):
    """Best-effort removal of client-only mods using metadata, with optional pattern overrides.

    Rules:
    - Inspect Fabric/Quilt JSON: environment == "client" => client-only
    - Inspect Forge mods.toml: client-only hints (side/clientSideOnly/onlyClient)
    - No built-in name patterns. Optional patterns can be supplied via:
      ENV `CLIENT_ONLY_MOD_PATTERNS` (comma-separated),
      ENV `CLIENT_ONLY_MOD_PATTERNS_URL` (one per line),
      files `client-only-mods.txt` in server folder or `/data/servers/client-only-mods.txt`.
    """
    try:
        mods_dir = target_dir / "mods"
        if not mods_dir.exists() or not mods_dir.is_dir():
            return
        disable_dir = target_dir / "mods-disabled-client"
        disable_dir.mkdir(parents=True, exist_ok=True)

        # Collect optional patterns from env/URL/files (all lowercased)
        # Start with a conservative built-in fallback list to catch common client-only mods when metadata is absent
        patterns: list[str] = [
            "oculus", "iris", "replaymod", "dynamicfps", "dynamic-fps", "dynamic_fps",
            "sodium", "embeddium", "xaero", "xaeros", "reeses_sodium_options", "lambdynamiclights",
            "betterf3", "particular", "itemphysic", "framework"
        ]
        try:
            extra_env = os.environ.get("CLIENT_ONLY_MOD_PATTERNS", "").strip()
            if extra_env:
                for tok in extra_env.split(","):
                    tok = tok.strip().lower()
                    if tok:
                        patterns.append(tok)
        except Exception:
            pass
        try:
            url = os.environ.get("CLIENT_ONLY_MOD_PATTERNS_URL", "").strip()
            if url:
                try:
                    rr = requests.get(url, timeout=10)
                    if rr.ok:
                        for line in rr.text.splitlines():
                            line = (line or "").strip().lower()
                            if not line or line.startswith("#"):
                                continue
                            patterns.append(line)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            for cfg in [target_dir / "client-only-mods.txt", Path("/data/servers/client-only-mods.txt")]:
                if cfg.exists():
                    for line in cfg.read_text(encoding="utf-8", errors="ignore").splitlines():
                        line = (line or "").strip().lower()
                        if not line or line.startswith("#"):
                            continue
                        patterns.append(line)
        except Exception:
            pass

        moved = 0
        for jar in mods_dir.glob("*.jar"):
            name = jar.name.lower()
            client_only = False
            has_metadata = False
            # Inspect contents for Fabric/Quilt/Forge metadata flags
            try:
                with zipfile.ZipFile(jar, 'r') as zf:
                    try:
                        if 'fabric.mod.json' in zf.namelist():
                            has_metadata = True
                            import json as _json
                            raw = zf.read('fabric.mod.json')
                            data = _json.loads(raw.decode('utf-8', errors='ignore'))
                            env = str((data or {}).get('environment') or '').strip().lower()
                            if env == 'client':
                                client_only = True
                    except Exception:
                        pass
                    try:
                        if not client_only and 'quilt.mod.json' in zf.namelist():
                            has_metadata = True
                            import json as _json
                            raw = zf.read('quilt.mod.json')
                            data = _json.loads(raw.decode('utf-8', errors='ignore'))
                            env = str((data or {}).get('environment') or '').strip().lower()
                            if env == 'client':
                                client_only = True
                    except Exception:
                        pass
                    try:
                        if not client_only and 'META-INF/mods.toml' in zf.namelist():
                            has_metadata = True
                            txt = zf.read('META-INF/mods.toml').decode('utf-8', errors='ignore').lower()
                            # Strict Forge heuristic: only mark as client-only on explicit boolean flags.
                            # Avoid generic side=\"client\" which often appears in dependency blocks.
                            if ('clientsideonly=true' in txt) or ('onlyclient=true' in txt) or ('client_only=true' in txt):
                                client_only = True
                    except Exception:
                        pass
            except Exception:
                pass
            # Optional fallback to provided name-patterns only (only if no metadata at all)
            if not client_only and not has_metadata and patterns and any(pat in name for pat in patterns):
                client_only = True
            if client_only:
                dest = disable_dir / jar.name
                try:
                    shutil.move(str(jar), str(dest))
                    moved += 1
                    push_event({
                        "type": "progress",
                        "step": "mods",
                        "message": f"Disabled likely client-only mod: {jar.name}",
                        "progress": 60
                    })
                except Exception:
                    continue
        if moved:
            push_event({
                "type": "progress",
                "step": "mods",
                "message": f"Moved {moved} client-only mods to mods-disabled-client/",
                "progress": 61
            })
    except Exception:
        # Best-effort only
        pass

def _ensure_server_jar(
    target_dir: Path,
    loader: Optional[str],
    mc_version: Optional[str],
    loader_version: Optional[str],
    push_event=lambda ev: None
):
    """Ensure a runnable server jar or installer exists in target_dir.
    Attempts for known loaders; falls back to vanilla server.jar.
    """
    # Quick check for existing jar or run.sh
    patterns = [
        "server.jar", "run.sh", "neoforge-*-universal.jar", "*forge-*-universal.jar",
        "forge-*-server.jar", "forge-*.jar", "*paper*.jar", "*purpur*.jar", "*fabric*.jar", "*server*.jar"
    ]
    for pat in patterns:
        if list(target_dir.glob(pat)):
            return  # something present already

    try:
        ldr = (loader or "").lower()
        mc = (mc_version or "").strip()
        lver = (loader_version or "").strip()

        if ldr == "fabric":
            # Determine loader version if missing
            if not lver and mc:
                try:
                    resp = requests.get(f"https://meta.fabricmc.net/v2/versions/loader/{mc}", timeout=30)
                    if resp.ok:
                        arr = resp.json()
                        # Pick first stable else first entry
                        stable = next((x for x in arr if x.get("stable")), None)
                        lver = (stable or (arr[0] if arr else {})).get("loader", {}).get("version") or ""
                except Exception:
                    pass
            if mc and lver:
                url = f"https://meta.fabricmc.net/v2/versions/loader/{mc}/{lver}/server/jar"
                out = target_dir / f"fabric-server-mc.{mc}-loader.{lver}.jar"
                push_event({"type": "progress", "step": "server", "message": f"Downloading Fabric server jar {mc}/{lver}", "progress": 62})
                _download_to(out, url, timeout=180)
                return

        if ldr == "forge":
            # If loader_version missing, use promotions_slim.json to find recommended/latest
            if not lver and mc:
                try:
                    resp = requests.get("https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json", timeout=30)
                    if resp.ok:
                        data = resp.json()
                        promos = data.get("promos", {})
                        lver = promos.get(f"{mc}-recommended") or promos.get(f"{mc}-latest") or ""
                except Exception:
                    pass
            if mc and lver:
                # If loader_version already includes the MC version prefix, don't duplicate
                base = lver if lver.startswith(f"{mc}-") else f"{mc}-{lver}"
                url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{base}/forge-{base}-installer.jar"
                out = target_dir / f"forge-{base}-installer.jar"
                push_event({"type": "progress", "step": "server", "message": f"Downloading Forge installer {base}", "progress": 62})
                _download_to(out, url, timeout=300)
                return

        if ldr == "neoforge":
            # Prefer provided loader_version; otherwise, try to infer latest for this MC version
            if not lver and mc:
                try:
                    meta_url = "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
                    resp = requests.get(meta_url, timeout=30)
                    if resp.ok:
                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(resp.text)
                        versions = [v.text or "" for v in root.findall(".//version")]
                        # Choose the latest version that starts with the MC version prefix
                        for v in reversed(versions):
                            if v.startswith(mc):
                                lver = v
                                break
                except Exception:
                    pass
            if lver:
                url = f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{lver}/neoforge-{lver}-installer.jar"
                out = target_dir / f"neoforge-{lver}-installer.jar"
                push_event({"type": "progress", "step": "server", "message": f"Downloading NeoForge installer {lver}", "progress": 62})
                _download_to(out, url, timeout=300)
                return

        # Fallback: vanilla server jar for the given Minecraft version
        if mc:
            try:
                man = requests.get("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json", timeout=30).json()
                version = next((v for v in man.get("versions", []) if v.get("id") == mc), None)
                if version and version.get("url"):
                    det = requests.get(version["url"], timeout=30).json()
                    server_info = det.get("downloads", {}).get("server")
                    if server_info and server_info.get("url"):
                        out = target_dir / "server.jar"
                        push_event({"type": "progress", "step": "server", "message": f"Downloading Vanilla server {mc}", "progress": 62})
                        _download_to(out, server_info["url"], timeout=300)
                        return
            except Exception:
                pass
    except Exception as e:
        push_event({"type": "progress", "step": "server", "message": f"Auto-download failed: {e}", "progress": 63})

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

    servers_root = SERVERS_ROOT
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
    servers_root = SERVERS_ROOT
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
        tmpdir: Path | None = None
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

            # Determine downloadable artifact (modrinth .mrpack or curseforge .zip server pack)
            files = v.get("files") or []
            artifact = None
            for f in files:
                fn = (f.get("filename") or "").lower()
                if f.get("primary") or fn.endswith(".mrpack") or fn.endswith(".zip"):
                    artifact = f
                    break
            if not artifact and files:
                artifact = files[0]
            if not artifact or not artifact.get("url"):
                raise RuntimeError("No downloadable file for this version")

            # Prepare server dir
            servers_root = SERVERS_ROOT
            target_dir = servers_root / req.name
            target_dir.mkdir(parents=True, exist_ok=True)

            # Download artifact
            tmpdir = Path(tempfile.mkdtemp(prefix="modpack_install_"))
            filename = artifact.get("filename") or "artifact.bin"
            url = artifact.get("url")
            lower_name = filename.lower()
            if lower_name.endswith(".mrpack"):
                _push_event(task_id, {"type": "progress", "step": "download", "message": "Downloading modpack (.mrpack)", "progress": 25})
                artifact_path = tmpdir / filename
                with requests.get(url, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    with open(artifact_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
            elif lower_name.endswith(".zip"):
                _push_event(task_id, {"type": "progress", "step": "download", "message": "Downloading server pack (.zip)", "progress": 25})
                artifact_path = tmpdir / filename
                with requests.get(url, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    with open(artifact_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
            else:
                raise RuntimeError("Unsupported modpack file type")

            # Initialize variables used by both paths
            idx = None
            loader = None
            mc_version = None
            loader_version = None
            if lower_name.endswith(".mrpack"):
                # Extract overrides and parse Modrinth index
                _push_event(task_id, {"type": "progress", "step": "extract", "message": "Extracting overrides and index", "progress": 40})
                with zipfile.ZipFile(artifact_path, 'r') as z:
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
            elif lower_name.endswith(".zip"):
                # Extract entire server pack zip into target_dir
                _push_event(task_id, {"type": "progress", "step": "extract", "message": "Unpacking server pack zip", "progress": 40})
                extract_dir = tmpdir / "extracted"
                extract_dir.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(artifact_path, 'r') as z:
                    z.extractall(extract_dir)
                # If a single top-level dir, move contents; else move all
                def _single_top_level_dir(base: Path):
                    entries = [p for p in base.iterdir()]
                    if len(entries) == 1 and entries[0].is_dir():
                        return entries[0]
                    return None
                src_dir = _single_top_level_dir(extract_dir) or extract_dir
                # Move contents into target_dir
                for p in src_dir.iterdir():
                    dest = target_dir / p.name
                    if p.is_dir():
                        shutil.move(str(p), str(dest))
                    else:
                        target_dir.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(p), str(dest))
                # If overrides/ exists, merge its contents into root and remove folder
                for ov_name in ("overrides", "server-overrides"):
                    ov_dir = target_dir / ov_name
                    if ov_dir.exists() and ov_dir.is_dir():
                        for root, dirs, files in os.walk(ov_dir):
                            rel = Path(root).relative_to(ov_dir)
                            out_dir = target_dir / rel
                            out_dir.mkdir(parents=True, exist_ok=True)
                            for fn in files:
                                srcf = Path(root) / fn
                                shutil.move(str(srcf), str(out_dir / fn))
                        try:
                            shutil.rmtree(ov_dir, ignore_errors=True)
                        except Exception:
                            pass
                # If manifest.json exists, use CurseForge API to download listed mods into mods/
                manifest_path = None
                for cand in (target_dir / "manifest.json",):
                    if cand.exists():
                        manifest_path = cand
                        break
                # also search one-level deep if not found
                if not manifest_path:
                    for child in target_dir.iterdir():
                        if child.is_dir() and (child / "manifest.json").exists():
                            manifest_path = child / "manifest.json"
                            break
                if manifest_path and manifest_path.exists():
                    try:
                        with open(manifest_path, 'r', encoding='utf-8') as f:
                            mani = json.load(f)
                        # Derive loader/minecraft version
                        mc = mani.get("minecraft", {})
                        mv = mc.get("version")
                        if isinstance(mv, str):
                            mc_version = mv
                        mls = mc.get("modLoaders") or []
                        if isinstance(mls, list) and mls:
                            # Scan all entries, prefer NeoForge > Forge > Fabric
                            preferred = ["neoforge", "forge", "fabric"]
                            for pref in preferred:
                                for entry in mls:
                                    mid = str((entry or {}).get("id") or "")
                                    mid_l = mid.lower()
                                    if pref == "neoforge" and (mid_l.startswith("neoforge") or mid_l == "neoforge"):
                                        loader = "neoforge"
                                        try:
                                            loader_version = mid.split("-", 1)[1]
                                        except Exception:
                                            pass
                                        break
                                    if pref == "forge" and (mid_l.startswith("forge") or mid_l == "forge" or ("forge" in mid_l and not mid_l.startswith("neo"))):
                                        loader = "forge"
                                        try:
                                            loader_version = mid.split("-", 1)[1]
                                        except Exception:
                                            pass
                                        break
                                    if pref == "fabric" and (mid_l.startswith("fabric") or "fabric" in mid_l):
                                        loader = "fabric"
                                        try:
                                            loader_version = mid.split("-", 1)[1]
                                        except Exception:
                                            pass
                                        break
                                if loader:
                                    break
                        files_list = mani.get("files") or []
                        if files_list:
                            from integrations_store import get_integration_key
                            api_key = get_integration_key("curseforge")
                            if not api_key:
                                # Abort install early to avoid a broken server missing required dependencies
                                raise RuntimeError("CurseForge API key not configured; cannot download listed mods from manifest.json")
                            else:
                                headers = {"x-api-key": api_key, "Accept": "application/json", "User-Agent": "minecraft-controller/1.0"}
                                mods_dir = target_dir / "mods"
                                mods_dir.mkdir(parents=True, exist_ok=True)
                                total = len(files_list)
                                done = 0
                                for entry in files_list:
                                    proj = entry.get("projectID") or entry.get("projectId")
                                    fid = entry.get("fileID") or entry.get("fileId")
                                    if not proj or not fid:
                                        continue
                                    try:
                                        url_meta = f"https://api.curseforge.com/v1/mods/{proj}/files/{fid}"
                                        rr = requests.get(url_meta, headers=headers, timeout=30)
                                        rr.raise_for_status()
                                        data = rr.json().get("data") or {}
                                        # Skip client-only files on dedicated servers
                                        try:
                                            gv = [str(x).lower() for x in (data.get("gameVersions") or [])]
                                            if ("client" in gv) and ("server" not in gv):
                                                done += 1
                                                pct = 55 + int((done/total) * 10)
                                                _push_event(task_id, {"type": "progress", "step": "mods", "message": f"Skipped client-only mod {proj}/{fid}", "progress": pct})
                                                continue
                                        except Exception:
                                            pass
                                        dl = data.get("downloadUrl")
                                        out_name = data.get("fileName") or f"{proj}-{fid}.jar"
                                        if dl:
                                            with requests.get(dl, stream=True, timeout=120) as dr:
                                                dr.raise_for_status()
                                                with open(mods_dir / out_name, 'wb') as f2:
                                                    for chunk in dr.iter_content(chunk_size=8192):
                                                        if chunk:
                                                            f2.write(chunk)
                                        done += 1
                                        pct = 55 + int((done/total) * 10)
                                        _push_event(task_id, {"type": "progress", "step": "mods", "message": f"Downloaded {done}/{total} mods", "progress": pct})
                                    except Exception as de:
                                        _push_event(task_id, {"type": "progress", "step": "mods", "message": f"Failed mod {proj}/{fid}: {de}", "progress": 58})
                                # After Mods download, remove client-only mods that slip through
                                try:
                                    _purge_client_only_mods(target_dir, push_event=lambda ev: _push_event(task_id, ev))
                                except Exception:
                                    pass
                    except Exception as e:
                        _push_event(task_id, {"type": "progress", "step": "mods", "message": f"manifest.json processing failed: {e}", "progress": 52})

                # After processing manifest and overrides, ensure a server jar/installer is present
                try:
                    _ensure_server_jar(target_dir, loader, mc_version, loader_version, push_event=lambda ev: _push_event(task_id, ev))
                except Exception as e:
                    _push_event(task_id, {"type": "progress", "step": "server", "message": f"Server jar check failed: {e}", "progress": 64})

            # Derive loader/mc_version (for .mrpack path only). Do not clobber if already known.
            if isinstance(idx, dict):
                deps = idx.get("dependencies", {})
                if mc_version is None:
                    mc_version = deps.get("minecraft") or mc_version
                if loader is None:
                    if deps.get("fabric-loader"):
                        loader = "fabric"
                        loader_version = deps.get("fabric-loader")
                    elif deps.get("neoforge"):
                        loader = "neoforge"
                        loader_version = deps.get("neoforge")
                    elif deps.get("forge"):
                        loader = "forge"
                        loader_version = deps.get("forge")

            # Download files listed in index (mods/config/etc.) for .mrpack
            # Cache Modrinth project server_side info to avoid repeated lookups
            modrinth_side_cache: dict[str, str] = {}
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
                    # If env missing, best-effort: Detect Modrinth project from URL and skip if server_side is unsupported
                    url0 = downloads[0]
                    try:
                        if isinstance(url0, str) and "cdn.modrinth.com/data/" in url0:
                            import re as _re
                            m = _re.search(r"cdn\.modrinth\.com/data/([^/]+)/versions/", url0)
                            if m:
                                proj_id = m.group(1)
                                side = modrinth_side_cache.get(proj_id)
                                if side is None:
                                    pr = requests.get(f"https://api.modrinth.com/v2/project/{proj_id}", timeout=15)
                                    if pr.ok:
                                        side = (pr.json().get("server_side") or "").lower()
                                        modrinth_side_cache[proj_id] = side
                                if side == "unsupported":
                                    _push_event(task_id, {"type": "progress", "step": "mods", "message": f"Skipped client-only mod (Modrinth) for {path}", "progress": 56})
                                    continue
                    except Exception:
                        pass
                    dest = target_dir / path
                    dest.parent.mkdir(parents=True, exist_ok=True)
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
                                    while True:
                                        data = f.read(8192)
                                        if not data:
                                            break
                                        h.update(data)
                                if h.hexdigest().lower() != str(hashes["sha512"]).lower():
                                    raise ValueError(f"SHA512 mismatch for {path}")
                            elif hashes.get("sha1"):
                                h = hashlib.sha1()
                                with open(dest, 'rb') as f:
                                    while True:
                                        data = f.read(8192)
                                        if not data:
                                            break
                                        h.update(data)
                                if h.hexdigest().lower() != str(hashes["sha1"]).lower():
                                    raise ValueError(f"SHA1 mismatch for {path}")
                    except Exception as de:
                        # Continue even if a mod fails; log event
                        _push_event(task_id, {"type": "progress", "step": "mods", "message": f"Failed to fetch {path}: {de}", "progress": 58})
            # After Mods download, remove client-only mods that slip through
            try:
                _purge_client_only_mods(target_dir, push_event=lambda ev: _push_event(task_id, ev))
            except Exception:
                pass

            dm = DockerManager()
            def normalize_ram(s: str) -> str:
                s = str(s).upper()
                if s.endswith("G") or s.endswith("M"):
                    return s
                try:
                    n = int(s)
                    return f"{n}M"
                except Exception:
                    return "2048M"

            # Two paths: .mrpack => create_server; .zip => create_server_from_existing
            if lower_name.endswith(".mrpack"):
                # Fallbacks if not found earlier
                if not loader:
                    loaders = v.get("loaders") or []
                    for cand in ("neoforge", "forge", "fabric"):
                        if cand in [l.lower() for l in loaders]:
                            loader = cand
                            break
                if not mc_version:
                    games = v.get("game_versions") or []
                    mc_version = games[0] if games else "1.21"
                if not loader:
                    loader = "paper"

                _push_event(task_id, {"type": "progress", "step": "prepare", "message": f"Preparing {loader} server", "progress": 70})

                min_ram = req.min_ram or ("2048M" if loader != "paper" else "1024M")
                max_ram = req.max_ram or ("4096M" if loader != "paper" else "2048M")
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
                        "mc.modpack.version_id": str(v.get("id")),
                    }
                )
            else:
                # .zip server pack path
                _push_event(task_id, {"type": "progress", "step": "prepare", "message": "Preparing existing server files", "progress": 70})
                # Ensure EULA accepted
                try:
                    (target_dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")
                except Exception:
                    pass
                min_ram = req.min_ram or "2048M"
                max_ram = req.max_ram or "4096M"
                min_ram_n = normalize_ram(min_ram)
                max_ram_n = normalize_ram(max_ram)

                _push_event(task_id, {"type": "progress", "step": "create", "message": "Creating server container", "progress": 85})
                # Try to pass loader/version to runtime for Java selection if known
                extra_env = {}
                try:
                    if loader:
                        extra_env["SERVER_TYPE"] = loader
                    if mc_version:
                        extra_env["SERVER_VERSION"] = mc_version
                except Exception:
                    pass
                result = dm.create_server_from_existing(
                    name=req.name,
                    host_port=req.host_port,
                    min_ram=min_ram_n,
                    max_ram=max_ram_n,
                    extra_env=extra_env or None,
                    extra_labels={
                        "mc.modpack.provider": req.provider,
                        "mc.modpack.id": str(req.pack_id),
                        "mc.modpack.version_id": str(v.get("id")),
                    }
                )

            _push_event(task_id, {"type": "done", "message": "Installation complete", "server": result})
        except Exception as e:
            _push_event(task_id, {"type": "error", "message": str(e)})
        finally:
            try:
                if 'tmpdir' in locals() and tmpdir:
                    shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True).start()
    return {"task_id": task_id}

@router.get("/updates")
async def list_updates():
    from catalog_routes import get_providers_live
    dm = DockerManager()
    servers = dm.list_servers()
    updates = []
    providers = get_providers_live()
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
    from catalog_routes import get_providers_live
    dm = DockerManager()
    providers = get_providers_live()
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

    servers_root = SERVERS_ROOT
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
        # Record metadata about installed modpack version (labels not updatable post-create)
        try:
            meta_path = target_dir / "modpack.meta.json"
            meta = {
                "provider": provider,
                "pack_id": str(pack_id),
                "version_id": str(version_id),
            }
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f)
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

