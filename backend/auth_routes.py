from fastapi import APIRouter, Depends, HTTPException, status, Request
import logging
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field, validator
from typing import List, Optional
from datetime import datetime, timedelta

from database import get_db
from models import User, Role, UserSession
from auth import (
    create_access_token, require_auth,
    get_password_hash,
    require_user_view, require_user_create, require_user_edit, require_user_delete,
    require_user_manage_roles, require_permission,
    get_client_ip, get_user_agent
)
from user_service import UserService

router = APIRouter(prefix="/auth", tags=["authentication"])

# Pydantic models
class Token(BaseModel):
    access_token: str
    token_type: str

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str = "user"

    @validator("password")
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(ch.isupper() for ch in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(ch.islower() for ch in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(ch.isdigit() for ch in v):
            raise ValueError("Password must contain at least one digit")
        return v

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    must_change_password: bool
    created_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: List[str]

class RoleUpdate(BaseModel):
    description: Optional[str] = None
    permissions: Optional[List[str]] = None

class AdminPasswordReset(BaseModel):
    new_password: str
    force_change: bool = True


def _ensure_password_strength(password: str):
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters long")
    if not any(ch.isupper() for ch in password):
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
    if not any(ch.islower() for ch in password):
        raise HTTPException(status_code=400, detail="Password must contain at least one lowercase letter")
    if not any(ch.isdigit() for ch in password):
        raise HTTPException(status_code=400, detail="Password must contain at least one digit")

@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Authenticate user and return access token (session token)."""
    svc = UserService(db)
    user = svc.authenticate_user(form_data.username, form_data.password, ip_address=get_client_ip(request))
    if not user:
        logging.warning(f"Login failed for username='{form_data.username}' from IP={get_client_ip(request)} user_agent='{get_user_agent(request)}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create a session token and return it
    session = svc.create_user_session(user, ip_address=get_client_ip(request), user_agent=get_user_agent(request))
    logging.info(f"Login success username='{form_data.username}' session_id={session.id} IP={get_client_ip(request)}")
    return {"access_token": session.session_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user = Depends(require_auth)):
    """Get current user information."""
    return current_user

@router.put("/me/password")
async def change_password(
    password_data: PasswordChange,
    current_user = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Change current user's password."""
    from auth import verify_password

    _ensure_password_strength(password_data.new_password)
    
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )
    
    current_user.hashed_password = get_password_hash(password_data.new_password)
    current_user.must_change_password = False
    db.commit()
    
    return {"message": "Password updated successfully"}

@router.post("/logout")
async def logout(
    request: Request,
    current_user = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Logout current session by invalidating the bearer token if it is a session token."""
    svc = UserService(db)
    # Extract token from Authorization header
    auth_header = request.headers.get("authorization", "")
    token = auth_header.split(" ")[-1] if auth_header else None
    if token:
        svc.invalidate_session(token)
    return {"message": "Logged out"}

@router.get("/users", response_model=List[UserResponse])
async def list_users(
    current_user = Depends(require_user_view),
    db: Session = Depends(get_db)
):
    """List all users (permission-based)."""
    users = db.query(User).all()
    return users

@router.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    current_user = Depends(require_user_create),
    db: Session = Depends(get_db)
):
    """Create a new user (permission-based)."""
    # Check if user already exists
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Validate role
    # Use roles defined in DB
    valid_roles = [r.name for r in db.query(Role).all()]
    if user_data.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {valid_roles}"
        )
    
    # Create user
    hashed_password = get_password_hash(user_data.password)
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
        role=user_data.role,
        is_active=True
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return user

@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user = Depends(require_user_edit),
    db: Session = Depends(get_db)
):
    """Update a user (permission-based)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    updates = {}
    # Update fields
    if user_data.email is not None:
        # Check email uniqueness
        existing_user = db.query(User).filter(
            User.email == user_data.email, User.id != user_id
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        updates["email"] = str(user_data.email)

    if user_data.role is not None:
        valid_roles = [r.name for r in db.query(Role).all()]
        if user_data.role not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role. Must be one of: {valid_roles}"
            )
        # Prevent demoting the last active admin if this user is currently an admin
        from sqlalchemy import and_
        is_target_user_admin = db.query(User).filter(User.id == user_id, User.role == "admin", User.is_active == True).count() == 1
        if is_target_user_admin and user_data.role != "admin":
            active_admins = db.query(User).filter(and_(User.role == "admin", User.is_active == True)).count()
            if active_admins <= 1:
                raise HTTPException(status_code=400, detail="Cannot demote the last active admin")
        updates["role"] = user_data.role

    if user_data.is_active is not None:
        # Prevent deactivating last active admin if this user is admin
        if user_data.is_active is False:
            from sqlalchemy import and_
            is_target_user_admin = db.query(User).filter(User.id == user_id, User.role == "admin", User.is_active == True).count() == 1
            if is_target_user_admin:
                active_admins = db.query(User).filter(and_(User.role == "admin", User.is_active == True)).count()
                if active_admins <= 1:
                    raise HTTPException(status_code=400, detail="Cannot deactivate the last active admin")
        updates["is_active"] = bool(user_data.is_active)

    if updates:
        db.query(User).filter(User.id == user_id).update(updates)
        db.commit()
    
    # Return updated user
    user = db.query(User).filter(User.id == user_id).first()
    return user

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user = Depends(require_user_delete),
    db: Session = Depends(get_db)
):
    """Delete (deactivate) a user (permission-based)."""
    svc = UserService(db)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Prevent admin from deleting themselves
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    try:
        svc.delete_user(user_id, deleted_by=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {"message": "User deactivated and sessions revoked"}

@router.post("/users/{user_id}/password-reset")
async def admin_reset_password(
    user_id: int,
    payload: AdminPasswordReset,
    current_user = Depends(require_permission("user.password.reset")),
    db: Session = Depends(get_db)
):
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters long")
    _ensure_password_strength(payload.new_password)
    svc = UserService(db)
    try:
        svc.reset_user_password(user_id, payload.new_password, payload.force_change, updated_by=current_user.id)
        return {"message": "Password reset"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/users/{user_id}/unlock")
async def admin_unlock_user(
    user_id: int,
    current_user = Depends(require_user_edit),
    db: Session = Depends(get_db)
):
    svc = UserService(db)
    try:
        svc.unlock_user(user_id, updated_by=current_user.id)
        return {"message": "User unlocked"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/users/{user_id}/sessions/revoke-all")
async def admin_revoke_all_sessions(
    user_id: int,
    current_user = Depends(require_permission("user.sessions.revoke")),
    db: Session = Depends(get_db)
):
    svc = UserService(db)
    count = svc.invalidate_user_sessions(user_id)
    return {"message": "Sessions revoked", "count": count}

@router.get("/sessions", response_model=List[dict])
async def list_my_sessions(
    current_user = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """List current user's active sessions."""
    sessions = db.query(UserSession).filter(UserSession.user_id == current_user.id, UserSession.is_active == True).all()
    return [
        {
            "id": s.id,
            "ip_address": s.ip_address,
            "user_agent": s.user_agent,
            "created_at": s.created_at,
            "expires_at": s.expires_at,
            "is_active": s.is_active
        } for s in sessions
    ]

@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: int,
    current_user = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Revoke a session. Users can revoke their own sessions; users with user.sessions.revoke can revoke any."""
    svc = UserService(db)
    session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        # Check permission: user.sessions.revoke
        if not UserService(db).user_has_permission(current_user, "user.sessions.revoke"):
            raise HTTPException(status_code=403, detail="Not allowed to revoke others' sessions")
    # Use bulk update to avoid attribute typing issues
    db.query(UserSession).filter(UserSession.id == session_id).update({"is_active": False})
    db.commit()
    return {"message": "Session revoked"}

@router.get("/roles", response_model=List[dict])
async def list_roles(
    current_user = Depends(require_user_manage_roles),
    db: Session = Depends(get_db)
):
    roles = db.query(Role).all()
    return [
        {
            "name": r.name,
            "description": r.description,
            "permissions": r.permissions,
            "is_system": r.is_system,
        } for r in roles
    ]

@router.post("/roles", response_model=dict)
async def create_role(
    payload: RoleCreate,
    current_user = Depends(require_permission("role.edit")),
    db: Session = Depends(get_db)
):
    svc = UserService(db)
    try:
        role = svc.create_role(payload.name, payload.description, payload.permissions)
        return {
            "name": role.name,
            "description": role.description,
            "permissions": role.permissions,
            "is_system": role.is_system,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/roles/{name}", response_model=dict)
async def update_role(
    name: str,
    payload: RoleUpdate,
    current_user = Depends(require_permission("role.edit")),
    db: Session = Depends(get_db)
):
    svc = UserService(db)
    try:
        role = svc.update_role(name, payload.description, payload.permissions)
        return {
            "name": role.name,
            "description": role.description,
            "permissions": role.permissions,
            "is_system": role.is_system,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/roles/{name}")
async def delete_role(
    name: str,
    current_user = Depends(require_permission("role.edit")),
    db: Session = Depends(get_db)
):
    svc = UserService(db)
    try:
        svc.delete_role(name)
        return {"message": "Role deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))