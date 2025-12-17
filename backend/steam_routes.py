from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Optional
from auth import require_moderator, require_auth
from docker_manager import DockerManager, DEFAULT_STEAM_PORT_START
from config import SERVERS_ROOT
from pathlib import Path
import os
import random
import string
import json

from steam_games import STEAM_GAMES

router = APIRouter(prefix="/steam", tags=["steam"])


def _random_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


class SteamInstallRequest(BaseModel):
    game: str = Field(..., description="Game slug, e.g. palworld, valheim")
    name: str = Field(..., description="Container/server name")
    host_port: Optional[int] = Field(None, description="Preferred host port for the primary game port")
    env: Dict[str, str] | None = None


@router.get("/games")
async def list_games(current_user=Depends(require_auth)):
    games: list[dict] = []
    for slug, meta in STEAM_GAMES.items():
        env_defaults = {}
        for key, value in (meta.get("env") or {}).items():
            try:
                env_defaults[key] = str(value)
            except Exception:
                env_defaults[key] = value
        sanitized_ports: list[dict] = []
        for port_cfg in meta.get("ports") or []:
            sanitized_ports.append({
                "container": port_cfg.get("container"),
                "protocol": (port_cfg.get("protocol") or "tcp").lower(),
                "description": port_cfg.get("description"),
            })
        games.append({
            "slug": slug,
            "name": meta.get("display_name") or slug.replace("_", " ").title(),
            "summary": meta.get("summary") or meta.get("notes") or "",
            "notes": meta.get("notes") or "",
            "image": meta.get("image"),
            "ports": sanitized_ports,
            "env": env_defaults,
            "volume": meta.get("volume"),
            "default_name": meta.get("default_name") or slug,
        })
    return {"games": games}


@router.post("/install")
async def install_steam_server(payload: SteamInstallRequest, current_user=Depends(require_moderator)):
    game = payload.game.lower()
    if game not in STEAM_GAMES:
        raise HTTPException(status_code=400, detail=f"Unsupported game: {game}")

    meta = STEAM_GAMES[game]
    image = meta["image"]
    ports = [dict(p) for p in (meta.get("ports") or [])]
    if not ports:
        raise HTTPException(status_code=400, detail="Game definition missing ports")

    env = {}
    for key, value in (meta.get("env") or {}).items():
        try:
            env[key] = str(value)
        except Exception:
            env[key] = value
    # Fill passwords if present and still set to placeholders
    for key in list(env.keys()):
        if isinstance(env[key], str) and env[key].lower() in {"change-me", "admin", ""}:
            env[key] = _random_password()
    if payload.env:
        for k, v in payload.env.items():
            if v is None:
                continue
            env[k] = v

    # Use host_port for the first port only; others auto-assign
    if payload.host_port is not None and ports:
        try:
            ports[0]["host"] = int(payload.host_port)
        except Exception:
            pass

    volume = None
    host_dir = SERVERS_ROOT / "steam" / game / payload.name
    host_dir.mkdir(parents=True, exist_ok=True)
    if meta.get("volume"):
        volume = {
            "host": host_dir,
            "container": meta["volume"].get("container") or "/data",
        }

    restart_policy = {"Name": "unless-stopped"}

    dm = DockerManager()
    try:
        result = dm.create_steam_container(
            name=payload.name,
            image=image,
            ports=ports,
            env=env,
            volume=volume,
            restart_policy=restart_policy,
            extra_labels={"steam.game": game},
        )
        container_id = result.get("id")
        mc_link = None
        if container_id:
            try:
                steam_dir = SERVERS_ROOT / "steam" / game / payload.name
                mc_link = SERVERS_ROOT / payload.name
                if mc_link.exists() or mc_link.is_symlink():
                    mc_link.unlink()
                os.symlink(steam_dir, mc_link)
                meta_path = steam_dir / "server_meta.json"
                meta = {}
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8") or "{}")
                    except Exception:
                        meta = {}
                steam_ports = []
                try:
                    for raw_key, host_port in (result.get("ports") or {}).items():
                        parts = str(raw_key).split("/", 1)
                        c_port = parts[0]
                        proto = parts[1] if len(parts) > 1 else "tcp"
                        try:
                            c_port_val = int(c_port)
                        except Exception:
                            c_port_val = c_port
                        steam_ports.append({
                            "container_port": c_port_val,
                            "protocol": proto.lower(),
                            "host_port": host_port,
                        })
                except Exception:
                    steam_ports = []
                meta.update({
                    "name": payload.name,
                    "steam_game": game,
                    "server_kind": "steam",
                    "data_path": str(mc_link or steam_dir),
                    "id": container_id,
                    "ports": result.get("ports"),
                    "steam_ports": steam_ports,
                    "env": env,
                })
                try:
                    meta_path.write_text(json.dumps(meta), encoding="utf-8")
                except Exception:
                    pass
            except Exception as link_err:
                print(f"[STEAM] Failed to create symlink for {payload.name}: {link_err}")
        result["steam_game"] = game
        result["env"] = env
        result["server_kind"] = "steam"
        result["data_path"] = str(mc_link or host_dir)
        if steam_ports:
            result["steam_ports"] = steam_ports
        if mc_link is not None:
            result["symlink"] = str(mc_link)
        return result
    except Exception as e:
        # Cleanup directory on failure
        try:
            if host_dir.exists() and not any(host_dir.iterdir()):
                host_dir.rmdir()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to start {game}: {e}")
