from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
import requests
from auth import require_auth
from models import User

router = APIRouter(prefix="/probe", tags=["probe"])


@router.get("/paper")
def probe_paper(
    version: str = Query(..., description="Minecraft version, e.g. 1.21.1"),
    build: Optional[int] = Query(None, description="Specific Paper build number; if omitted, latest is used"),
    sample_bytes: int = Query(0, ge=0, le=65536, description="If >0, fetch first N bytes to verify PK header"),
    current_user: User = Depends(require_auth),
):
    """Probe PaperMC availability for a given version/build without creating a server.

    Returns resolved build, download URL, headers (content-type,length), and optional first bytes.
    """
    base = "https://api.papermc.io/v2/projects/paper"
    try:
        # Resolve build and jar name
        if build is None:
            vr = requests.get(f"{base}/versions/{version}", timeout=15)
            if vr.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Paper version {version} not found")
            vr.raise_for_status()
            builds = vr.json().get("builds") or []
            if not builds:
                raise HTTPException(status_code=404, detail=f"No builds listed for Paper {version}")
            build = int(builds[-1])

        br = requests.get(f"{base}/versions/{version}/builds/{build}", timeout=15)
        if br.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Build {build} for Paper {version} not found")
        br.raise_for_status()
        bdata = br.json()
        downloads = (bdata.get("downloads") or {}).get("application") or {}
        jar_name = downloads.get("name") or f"paper-{version}-{build}.jar"
        url = f"{base}/versions/{version}/builds/{build}/downloads/{jar_name}"

        # Try a HEAD request first to get headers quickly
        head_info: dict[str, object] = {}
        first_bytes_hex = None
        first_bytes_ascii = None
        try:
            h = requests.head(url, allow_redirects=True, timeout=15)
            # Some CDNs might not support HEAD reliably; tolerate non-200
            clen = h.headers.get("content-length")
            head_info = {
                "status_code": int(h.status_code),
                "content_type": h.headers.get("content-type"),
                "content_length": int(clen) if (clen or "").isdigit() else None,
            }
        except Exception:
            head_info = {"error": "HEAD request failed"}

        # Optionally sample first bytes using Range GET
        if sample_bytes and sample_bytes > 0:
            try:
                rg = requests.get(url, headers={"Range": f"bytes=0-{sample_bytes-1}"}, stream=True, timeout=20)
                rg.raise_for_status()
                data = b""
                for chunk in rg.iter_content(chunk_size=min(8192, sample_bytes)):
                    if not chunk:
                        break
                    data += chunk
                    if len(data) >= sample_bytes:
                        break
                first_bytes_hex = data[:sample_bytes].hex()
                first_bytes_ascii = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in data[:sample_bytes])
                # Infer full size from Content-Range if present
                cr = rg.headers.get("Content-Range") or ""
                # Example: bytes 0-1023/1234567
                if cr.startswith("bytes") and "/" in cr:
                    try:
                        total = cr.split("/")[-1]
                        if total.isdigit():
                            # Only set if not already present
                            if "content_length" not in head_info or head_info.get("content_length") in (None, 0):
                                head_info["content_length"] = int(total)
                    except Exception:
                        pass
            except Exception as e:
                # Non-fatal: continue without sample
                first_bytes_hex = None
                first_bytes_ascii = None

        return {
            "available": True,
            "version": version,
            "build": build,
            "jar_name": jar_name,
            "url": url,
            "headers": head_info,
            "first_bytes_hex": first_bytes_hex,
            "first_bytes_ascii": first_bytes_ascii,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Probe failed: {e}")
