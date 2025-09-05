from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, status, Body
from sqlalchemy.orm import Session
from datetime import datetime

from database import get_db
from models import User
from user_service import UserService
from auth import get_current_user, require_auth, require_admin, require_user_view, require_user_create, require_user_edit
from auth import require_user_delete, require_user_manage_roles, log_user_action
from pydantic import BaseModel, EmailStr, Field, validator

# Pydantic models for request/response
class UserBase(BaseModel):
    username: str
    email: EmailStr
    role: str = "user"
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    
    @validator('password')
    def password_strength(cls, v):
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one number')
        return v

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
    
    @validator('password')
    def password_strength(cls, v):
        """Validate password strength if provided."""
        if v is None:
            return v
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one number')
        return v

class UserPasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)
    
    @validator('new_password')
    def password_strength(cls, v):
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one number')
        return v

class UserLoginRequest(BaseModel):
    username: str
    password: str

class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    
    class Config:
        orm_mode = True

class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

class UserSessionResponse(BaseModel):
    session_token: str
    user: UserResponse

class RoleResponse(BaseModel):
    name: str
    description: str
    permissions: List[str]
    is_system: bool

    class Config:
        orm_mode = True

class PermissionResponse(BaseModel):
    name: str
    description: str
    category: str

    class Config:
        orm_mode = True

class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int]
    timestamp: datetime
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    details: Optional[Dict[str, Any]]
    ip_address: Optional[str]

    class Config:
        orm_mode = True

class AuditLogListResponse(BaseModel):
    logs: List[AuditLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

# Create router
router = APIRouter(prefix="/users", tags=["users"])

# Authentication routes
@router.post("/login", response_model=UserSessionResponse)
async def login(
    request: Request,
    login_data: UserLoginRequest,
    db: Session = Depends(get_db)
):
    """Login and get a session token."""
    user_service = UserService(db)
    
    user = user_service.authenticate_user(
        login_data.username, 
        login_data.password,
        get_client_ip(request)
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create session
    session = user_service.create_user_session(
        user,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent")
    )
    
    return {
        "session_token": session.session_token,
        "user": user
    }

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Logout and invalidate session token."""
    user_service = UserService(db)
    # Get session token from Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        session_token = auth_header[7:]
        user_service.invalidate_session(session_token)
    
    # Log the action
    log_user_action(
        user=user,
        action="user.logout",
        resource_type="user",
        resource_id=str(user.id),
        request=request,
        db=db
    )
    
    return None

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    user: User = Depends(require_auth)
):
    """Get information about the current authenticated user."""
    return user

@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    request: Request,
    password_data: UserPasswordChange,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Change user's own password."""
    user_service = UserService(db)
    
    # Verify current password
    if not user_service.verify_password(password_data.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Update password
    updates = {
        "password": password_data.new_password,
        "must_change_password": False
    }
    
    user_service.update_user(user.id, updates, updated_by=user.id)
    
    # Log the action
    log_user_action(
        user=user,
        action="user.change_password",
        resource_type="user",
        resource_id=str(user.id),
        request=request,
        db=db
    )
    
    return None

# User management routes
@router.get("", response_model=UserListResponse)
async def list_users(
    request: Request,
    include_inactive: bool = False,
    page: int = 1,
    page_size: int = 50,
    user: User = Depends(require_user_view),
    db: Session = Depends(get_db)
):
    """List all users with pagination."""
    user_service = UserService(db)
    result = user_service.list_users(include_inactive, page, page_size)
    
    # Log the action
    log_user_action(
        user=user,
        action="user.list",
        resource_type="users",
        details={"page": page, "page_size": page_size, "include_inactive": include_inactive},
        request=request,
        db=db
    )
    
    return result

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_user_view),
    db: Session = Depends(get_db)
):
    """Get a specific user by ID."""
    user_service = UserService(db)
    user = user_service.get_user_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Log the action
    log_user_action(
        user=current_user,
        action="user.view",
        resource_type="user",
        resource_id=str(user_id),
        request=request,
        db=db
    )
    
    return user

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    request: Request,
    current_user: User = Depends(require_user_create),
    db: Session = Depends(get_db)
):
    """Create a new user."""
    user_service = UserService(db)
    
    try:
        user = user_service.create_user(
            username=user_data.username,
            email=user_data.email,
            password=user_data.password,
            role=user_data.role,
            full_name=user_data.full_name,
            created_by=current_user.id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    return user

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    request: Request,
    current_user: User = Depends(require_user_edit),
    db: Session = Depends(get_db)
):
    """Update a user's information."""
    user_service = UserService(db)
    
    # Check if updating role and if user has permission
    if user_data.role is not None and user_data.role != current_user.role:
        # Verify that the current user has permission to manage roles
        if not user_service.user_has_permission(current_user, "user.manage_roles"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: cannot change user roles"
            )
    
    try:
        updates = user_data.dict(exclude_unset=True, exclude_none=True)
        user = user_service.update_user(
            user_id=user_id,
            updates=updates,
            updated_by=current_user.id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    return user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_user_delete),
    db: Session = Depends(get_db)
):
    """Delete (deactivate) a user."""
    user_service = UserService(db)
    
    try:
        user_service.delete_user(
            user_id=user_id,
            deleted_by=current_user.id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    return None

# Role and permission routes
@router.get("/roles", response_model=List[RoleResponse])
async def get_roles(
    request: Request,
    current_user: User = Depends(require_user_manage_roles),
    db: Session = Depends(get_db)
):
    """Get all available roles."""
    user_service = UserService(db)
    roles = user_service.get_roles()
    
    # Log the action
    log_user_action(
        user=current_user,
        action="role.list",
        resource_type="roles",
        request=request,
        db=db
    )
    
    return roles

@router.get("/permissions", response_model=List[PermissionResponse])
async def get_permissions(
    request: Request,
    current_user: User = Depends(require_user_manage_roles),
    db: Session = Depends(get_db)
):
    """Get all available permissions."""
    user_service = UserService(db)
    permissions = user_service.get_permissions()
    
    # Log the action
    log_user_action(
        user=current_user,
        action="permission.list",
        resource_type="permissions",
        request=request,
        db=db
    )
    
    return permissions

# Audit logs
@router.get("/audit-logs", response_model=AuditLogListResponse)
async def get_audit_logs(
    request: Request,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    page: int = 1, 
    page_size: int = 50,
    current_user: User = Depends(require_user_manage_roles),
    db: Session = Depends(get_db)
):
    """Get audit logs with filtering and pagination."""
    user_service = UserService(db)
    result = user_service.get_audit_logs(user_id, action, page, page_size)
    
    # Log the action
    log_user_action(
        user=current_user,
        action="audit.view",
        resource_type="audit_logs",
        details={"user_id": user_id, "action": action, "page": page, "page_size": page_size},
        request=request,
        db=db
    )
    
    return result

def get_client_ip(request: Request) -> str:
    """Get client IP address from request."""
    if "x-forwarded-for" in request.headers:
        return request.headers["x-forwarded-for"].split(",")[0]
    if "x-real-ip" in request.headers:
        return request.headers["x-real-ip"]
    return request.client.host
