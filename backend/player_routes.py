from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database import get_db
from models import PlayerAction, User
from auth import require_auth, require_moderator
from runtime_adapter import get_runtime_manager_or_docker

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
            player_action.is_active = False
            db.commit()
        
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
            player_action.is_active = False
            db.commit()
        
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
            player_action.is_active = False
            db.commit()
        
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