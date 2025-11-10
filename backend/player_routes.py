from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database import get_db
from models import PlayerAction, User
from auth import require_auth, require_moderator
from runtime_adapter import get_runtime_manager_or_docker
from config import SERVERS_ROOT
import os, json, re, gzip, datetime as _dt

router = APIRouter(prefix="/players", tags=["player_management"])

# Pydantic models
class PlayerActionCreate(BaseModel):
    player_name: str
    action_type: str  # whitelist, ban, kick, op, deop
    reason: Optional[str] = None

class PlayerActionResponse(BaseModel):
    id: int
    server_name: str
    player_name: str
    action_type: str
    reason: Optional[str]
    performed_at: datetime
    is_active: bool
    
    class Config:
        from_attributes = True

_manager_cache = None


def get_docker_manager():
    """Get the active runtime manager (local or Docker)."""
    global _manager_cache
    if _manager_cache is None:
        _manager_cache = get_runtime_manager_or_docker()
    return _manager_cache


def _server_dir(server_name: str):
    try:
        p = (SERVERS_ROOT / server_name).resolve()
        if str(p).startswith(str(SERVERS_ROOT.resolve())):
            return p
    except Exception:
        pass
    return None

def _parse_log_timestamp(line: str, fallback_date: _dt.date | None) -> int | None:
    """Extract a timestamp (epoch seconds) from a log line if possible.
    Supports patterns like '2025-11-10 12:34:56' or '[12:34:56]'.
    """
    try:
        m = re.search(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})", line)
        if m:
            ts = f"{m.group(1)} {m.group(2)}"
            dt = _dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            return int(dt.replace(tzinfo=_dt.timezone.utc).timestamp())
        m2 = re.search(r"\[(\d{2}:\d{2}:\d{2})\]", line)
        if m2 and fallback_date:
            ts = f"{fallback_date.isoformat()} {m2.group(1)}"
            dt = _dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            return int(dt.replace(tzinfo=_dt.timezone.utc).timestamp())
    except Exception:
        return None
    return None

def _collect_history(server_name: str, limit_files: int = 6, limit_lines: int = 8000) -> dict[str, dict]:
    """Scan recent logs and usercache.json to build {name: {last_seen, sources}}.
    Returns a map keyed by lowercase name.
    """
    base = _server_dir(server_name)
    hist: dict[str, dict] = {}
    if not base:
        return hist
    # 1) usercache.json
    try:
        uc = base / "usercache.json"
        if uc.exists():
            data = json.loads(uc.read_text(encoding="utf-8", errors="ignore") or "[]")
            for ent in data or []:
                name = (ent.get("name") or "").strip()
                if not name:
                    continue
                k = name.lower()
                rec = hist.setdefault(k, {"name": name, "last_seen": None, "sources": set()})
                rec["sources"].add("usercache")
    except Exception:
        pass
    # 2) logs: latest.log and logs/*.log(.gz)
    try:
        candidates = []
        latest = base / "logs" / "latest.log"
        if latest.exists():
            candidates.append(latest)
        logs_dir = base / "logs"
        if logs_dir.exists() and logs_dir.is_dir():
            for p in logs_dir.iterdir():
                if p.name == "latest.log":
                    continue
                if p.suffix in (".log", ".gz"):
                    candidates.append(p)
        # sort by mtime desc and cap
        candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        candidates = candidates[:limit_files]
        total_lines = 0
        joined_re = re.compile(r"([A-Za-z0-9_\-]{2,16}) (joined the game|logged in)", re.IGNORECASE)
        left_re = re.compile(r"([A-Za-z0-9_\-]{2,16}) (left the game|logged out)", re.IGNORECASE)
        for p in candidates:
            try:
                fallback_date = _dt.date.fromtimestamp(p.stat().st_mtime)
            except Exception:
                fallback_date = None
            # open file (support gz)
            lines: list[str] = []
            try:
                if p.suffix == ".gz":
                    with gzip.open(p, "rt", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                else:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
            except Exception:
                continue
            # iterate from end for recency
            for line in reversed(lines):
                if total_lines >= limit_lines:
                    break
                total_lines += 1
                m = joined_re.search(line) or left_re.search(line)
                if not m:
                    continue
                name = m.group(1)
                k = name.lower()
                ts = _parse_log_timestamp(line, fallback_date)
                rec = hist.setdefault(k, {"name": name, "last_seen": None, "sources": set()})
                if ts and (rec["last_seen"] is None or int(ts) > int(rec["last_seen"])):
                    rec["last_seen"] = int(ts)
                rec["sources"].add("logs")
    except Exception:
        pass
    # finalize sets to lists
    for v in hist.values():
        if isinstance(v.get("sources"), set):
            v["sources"] = sorted(list(v["sources"]))
    return hist

@router.get("/{server_name}/roster")
async def get_player_roster(server_name: str, current_user: User = Depends(require_auth)):
    """Return online and offline players with last_seen.
    online: list of names (authoritative if available)
    offline: list of {name, last_seen} sorted by recency
    """
    # online via runtime manager (mcstatus/RCON/etc.)
    online_names: list[str] = []
    method = None
    try:
        dm = get_docker_manager()
        servers = dm.list_servers()
        target = next((s for s in servers if s.get("name") == server_name), None)
        if not target:
            raise HTTPException(status_code=404, detail="Server not found")
        cid = target.get("id")
        if not cid:
            raise HTTPException(status_code=400, detail="Server container not found")
        info = dm.get_player_info(cid)
        online_names = [n for n in (info.get("names") or []) if isinstance(n, str)]
        method = info.get("method") or "unknown"
    except HTTPException:
        raise
    except Exception:
        online_names = []
        method = "error"

    # history from logs/usercache
    hist = _collect_history(server_name)
    online_set = {n.lower() for n in online_names}
    offline: list[dict] = []
    for k, rec in hist.items():
        if k in online_set:
            continue
        offline.append({"name": rec.get("name"), "last_seen": rec.get("last_seen")})
    # sort by last_seen desc (unknown last)
    offline.sort(key=lambda x: (x.get("last_seen") or 0), reverse=True)
    return {"online": online_names, "offline": offline, "method": method}

@router.get("/{server_name}/actions", response_model=List[PlayerActionResponse])
async def list_player_actions(
    server_name: str,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """List all player actions for a server."""
    actions = db.query(PlayerAction).filter(
        PlayerAction.server_name == server_name
    ).order_by(PlayerAction.performed_at.desc()).all()
    
    return actions

@router.post("/{server_name}/whitelist", response_model=PlayerActionResponse)
async def whitelist_player(
    server_name: str,
    action_data: PlayerActionCreate,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Add a player to the whitelist."""
    if action_data.action_type != "whitelist":
        action_data.action_type = "whitelist"
    
    try:
        # Execute whitelist command
        docker_manager = get_docker_manager()
        servers = docker_manager.list_servers()
        
        target_server = None
        for server in servers:
            if server.get("name") == server_name:
                target_server = server
                break
        
        if not target_server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server not found"
            )
        
        container_id = target_server.get("id")
        if not container_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Server container not found"
            )
        
        # Send whitelist command
        command = f"whitelist add {action_data.player_name}"
        docker_manager.send_command(container_id, command)
        
        # Record action in database
        player_action = PlayerAction(
            server_name=server_name,
            player_name=action_data.player_name,
            action_type="whitelist",
            reason=action_data.reason,
            performed_by=current_user.id,
            is_active=True
        )
        
        db.add(player_action)
        db.commit()
        db.refresh(player_action)
        
        return player_action
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to whitelist player: {str(e)}"
        )

@router.delete("/{server_name}/whitelist/{player_name}")
async def remove_from_whitelist(
    server_name: str,
    player_name: str,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Remove a player from the whitelist."""
    try:
        # Execute whitelist remove command
        docker_manager = get_docker_manager()
        servers = docker_manager.list_servers()
        
        target_server = None
        for server in servers:
            if server.get("name") == server_name:
                target_server = server
                break
        
        if not target_server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server not found"
            )
        
        container_id = target_server.get("id")
        if not container_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Server container not found"
            )
        
        # Send whitelist remove command
        command = f"whitelist remove {player_name}"
        docker_manager.send_command(container_id, command)
        
        # Update database - mark as inactive
        player_action = db.query(PlayerAction).filter(
            PlayerAction.server_name == server_name,
            PlayerAction.player_name == player_name,
            PlayerAction.action_type == "whitelist",
            PlayerAction.is_active == True
        ).first()
        
        if player_action:
            try:
                # SQLAlchemy model attribute assignment guarded for linters
                setattr(player_action, 'is_active', False)
                db.commit()
            except Exception:
                pass
        
        return {"message": f"Player {player_name} removed from whitelist"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove player from whitelist: {str(e)}"
        )

@router.post("/{server_name}/ban", response_model=PlayerActionResponse)
async def ban_player(
    server_name: str,
    action_data: PlayerActionCreate,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Ban a player from the server."""
    if action_data.action_type != "ban":
        action_data.action_type = "ban"
    
    try:
        # Execute ban command
        docker_manager = get_docker_manager()
        servers = docker_manager.list_servers()
        
        target_server = None
        for server in servers:
            if server.get("name") == server_name:
                target_server = server
                break
        
        if not target_server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server not found"
            )
        
        container_id = target_server.get("id")
        if not container_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Server container not found"
            )
        
        # Send ban command
        if action_data.reason:
            command = f"ban {action_data.player_name} {action_data.reason}"
        else:
            command = f"ban {action_data.player_name}"
        docker_manager.send_command(container_id, command)
        
        # Record action in database
        player_action = PlayerAction(
            server_name=server_name,
            player_name=action_data.player_name,
            action_type="ban",
            reason=action_data.reason,
            performed_by=current_user.id,
            is_active=True
        )
        
        db.add(player_action)
        db.commit()
        db.refresh(player_action)
        
        return player_action
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ban player: {str(e)}"
        )

@router.delete("/{server_name}/ban/{player_name}")
async def unban_player(
    server_name: str,
    player_name: str,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Unban a player from the server."""
    try:
        # Execute pardon command
        docker_manager = get_docker_manager()
        servers = docker_manager.list_servers()
        
        target_server = None
        for server in servers:
            if server.get("name") == server_name:
                target_server = server
                break
        
        if not target_server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server not found"
            )
        
        container_id = target_server.get("id")
        if not container_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Server container not found"
            )
        
        # Send pardon command
        command = f"pardon {player_name}"
        docker_manager.send_command(container_id, command)
        
        # Update database - mark ban as inactive
        player_action = db.query(PlayerAction).filter(
            PlayerAction.server_name == server_name,
            PlayerAction.player_name == player_name,
            PlayerAction.action_type == "ban",
            PlayerAction.is_active == True
        ).first()
        
        if player_action:
            try:
                setattr(player_action, 'is_active', False)
                db.commit()
            except Exception:
                pass
        
        return {"message": f"Player {player_name} unbanned"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unban player: {str(e)}"
        )

@router.post("/{server_name}/kick")
async def kick_player(
    server_name: str,
    action_data: PlayerActionCreate,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Kick a player from the server."""
    if action_data.action_type != "kick":
        action_data.action_type = "kick"
    
    try:
        # Execute kick command
        docker_manager = get_docker_manager()
        servers = docker_manager.list_servers()
        
        target_server = None
        for server in servers:
            if server.get("name") == server_name:
                target_server = server
                break
        
        if not target_server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server not found"
            )
        
        container_id = target_server.get("id")
        if not container_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Server container not found"
            )
        
        # Send kick command
        if action_data.reason:
            command = f"kick {action_data.player_name} {action_data.reason}"
        else:
            command = f"kick {action_data.player_name}"
        docker_manager.send_command(container_id, command)
        
        # Record action in database
        player_action = PlayerAction(
            server_name=server_name,
            player_name=action_data.player_name,
            action_type="kick",
            reason=action_data.reason,
            performed_by=current_user.id,
            is_active=True
        )
        
        db.add(player_action)
        db.commit()
        db.refresh(player_action)
        
        return {"message": f"Player {action_data.player_name} kicked"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to kick player: {str(e)}"
        )

@router.post("/{server_name}/op", response_model=PlayerActionResponse)
async def op_player(
    server_name: str,
    action_data: PlayerActionCreate,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Give operator privileges to a player."""
    if action_data.action_type != "op":
        action_data.action_type = "op"
    
    try:
        # Execute op command
        docker_manager = get_docker_manager()
        servers = docker_manager.list_servers()
        
        target_server = None
        for server in servers:
            if server.get("name") == server_name:
                target_server = server
                break
        
        if not target_server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server not found"
            )
        
        container_id = target_server.get("id")
        if not container_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Server container not found"
            )
        
        # Send op command
        command = f"op {action_data.player_name}"
        docker_manager.send_command(container_id, command)
        
        # Record action in database
        player_action = PlayerAction(
            server_name=server_name,
            player_name=action_data.player_name,
            action_type="op",
            reason=action_data.reason,
            performed_by=current_user.id,
            is_active=True
        )
        
        db.add(player_action)
        db.commit()
        db.refresh(player_action)
        
        return player_action
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to OP player: {str(e)}"
        )

@router.delete("/{server_name}/op/{player_name}")
async def deop_player(
    server_name: str,
    player_name: str,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Remove operator privileges from a player."""
    try:
        # Execute deop command
        docker_manager = get_docker_manager()
        servers = docker_manager.list_servers()
        
        target_server = None
        for server in servers:
            if server.get("name") == server_name:
                target_server = server
                break
        
        if not target_server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server not found"
            )
        
        container_id = target_server.get("id")
        if not container_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Server container not found"
            )
        
        # Send deop command
        command = f"deop {player_name}"
        docker_manager.send_command(container_id, command)
        
        # Update database - mark OP as inactive
        player_action = db.query(PlayerAction).filter(
            PlayerAction.server_name == server_name,
            PlayerAction.player_name == player_name,
            PlayerAction.action_type == "op",
            PlayerAction.is_active == True
        ).first()
        
        if player_action:
            try:
                setattr(player_action, 'is_active', False)
                db.commit()
            except Exception:
                pass
        
        return {"message": f"Player {player_name} de-opped"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to de-OP player: {str(e)}"
        )

@router.get("/{server_name}/online")
async def get_online_players(
    server_name: str,
    current_user: User = Depends(require_auth)
):
    """Get list of currently online players."""
    try:
        # Execute list command to get online players
        docker_manager = get_docker_manager()
        servers = docker_manager.list_servers()
        
        target_server = None
        for server in servers:
            if server.get("name") == server_name:
                target_server = server
                break
        
        if not target_server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server not found"
            )
        
        container_id = target_server.get("id")
        if not container_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Server container not found"
            )
        
        # Send list command
        # Prefer authoritative player info from the runtime manager (RCON-backed)
        try:
            info = docker_manager.get_player_info(container_id)
            names = info.get('names') or []
            online = info.get('online') or 0
            maxp = info.get('max') or info.get('max_players') or 0
            method = info.get('method') or 'none'
            return {"players": names, "count": online, "max": maxp, "method": method}
        except Exception:
            # Fallback: attempt to send a 'list' command via the manager which may write to console
            result = docker_manager.send_command(container_id, "list")
            # Best-effort: parse the result if available
            try:
                text = result if isinstance(result, str) else (result.get('output') if isinstance(result, dict) else '')
                import re as _re
                m = _re.search(r"There are\s+(\d+)\s+of a max of\s+(\d+)\s+players online", str(text))
                if not m:
                    m = _re.search(r"(\d+)\s*/\s*(\d+)\s*players? online", str(text))
                names = []
                online = int(m.group(1)) if m else 0
                maxp = int(m.group(2)) if m else 0
            except Exception:
                names = []
                online = 0
                maxp = 0
            return {"players": names, "count": online, "max": maxp}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get online players: {str(e)}"
        )