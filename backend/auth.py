from datetime import datetime, timedelta
from typing import Optional, List
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import get_db, DatabaseSession
from models import User
import os
import logging
import time
from functools import lru_cache
import secrets

logger = logging.getLogger(__name__)

# Configuration
_raw_secret = os.getenv("SECRET_KEY")
if not _raw_secret or _raw_secret == "your-secret-key-change-this-in-production":
    # Generate an ephemeral secret so deployments without SECRET_KEY do not share a predictable token key.
    _raw_secret = secrets.token_urlsafe(64)
    logging.warning("SECRET_KEY was not set; generated a temporary secret. Configure SECRET_KEY for stable auth tokens.")

SECRET_KEY = _raw_secret
ALGORITHM = "HS256"
# Keep JWT access tokens short-lived; session tokens are now authoritative.
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Token authentication
security = HTTPBearer(auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

# Cache for user lookups to reduce database hits
_user_cache = {}
_cache_ttl = 60  # Cache TTL in seconds

def _get_cache_key(prefix: str, value: str) -> str:
    return f"{prefix}:{value}"

def _is_cache_valid(cache_entry: dict) -> bool:
    return time.time() - cache_entry['timestamp'] < _cache_ttl

def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Get user by username with caching to reduce database load."""
    cache_key = _get_cache_key("username", username)
    
    # Check cache first
    if cache_key in _user_cache and _is_cache_valid(_user_cache[cache_key]):
        return _user_cache[cache_key]['user']
    
    try:
        # Use optimized query with explicit session management
        user = db.query(User).filter(User.username == username).first()
        
        # Cache the result (including None results)
        _user_cache[cache_key] = {
            'user': user,
            'timestamp': time.time()
        }
        
        return user
    except Exception as e:
        logger.error(f"Error querying user by username {username}: {e}")
        # Clear cache entry on error
        _user_cache.pop(cache_key, None)
        raise

def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Get user by ID with caching to reduce database load."""
    cache_key = _get_cache_key("user_id", str(user_id))
    
    # Check cache first
    if cache_key in _user_cache and _is_cache_valid(_user_cache[cache_key]):
        return _user_cache[cache_key]['user']
    
    try:
        # Use optimized query with explicit session management
        user = db.query(User).filter(User.id == user_id).first()
        
        # Cache the result
        _user_cache[cache_key] = {
            'user': user,
            'timestamp': time.time()
        }
        
        return user
    except Exception as e:
        logger.error(f"Error querying user by ID {user_id}: {e}")
        # Clear cache entry on error
        _user_cache.pop(cache_key, None)
        raise

def clear_user_cache():
    """Clear the user cache (call when user data changes)."""
    global _user_cache
    _user_cache.clear()
    logger.info("User cache cleared")

def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """Authenticate a user with username and password."""
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
    
def get_client_ip(request: Request) -> str:
    """Get client IP address from request."""
    if "x-forwarded-for" in request.headers:
        return request.headers["x-forwarded-for"].split(",")[0]
    if "x-real-ip" in request.headers:
        return request.headers["x-real-ip"]
    return request.client.host

def get_user_agent(request: Request) -> str:
    """Get user agent from request."""
    return request.headers.get("user-agent", "Unknown")

def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get current user from session token, returning None if not authenticated."""
    if not credentials:
        return None
    
    # Try JWT token first for backward compatibility
    payload = verify_token(credentials.credentials)
    if payload is not None:
        username = payload.get("sub")
        if username:
            user = get_user_by_username(db, username)
            if user:
                return user
    
    # Try session token
    try:
        # Import here to avoid circular import
        from user_service import UserService
        user_service = UserService(db)
        user = user_service.get_user_by_session_token(credentials.credentials, refresh_expiry=True)
        return user
    except ImportError:
        logger.warning("UserService not available, using legacy JWT authentication only")
        return None

def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Require authentication - raises exception if not authenticated."""
    user = get_current_user(request, credentials, db)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    return user

def get_user_permissions(user: User, db: Session) -> List[str]:
    """Get permissions for a user based on their role."""
    try:
        # Import here to avoid circular import
        from user_service import UserService
        user_service = UserService(db)
        return user_service.get_user_permissions(user)
    except ImportError:
        # Fallback to basic role-based permissions if UserService not available
        if user.role in ("admin", "owner"):
            return ["*"]
        elif user.role == "moderator":
            return ["server.view", "server.start", "server.stop", "server.console", "server.files", "server.config"]
        else:
            return ["server.view"]

def require_permission(permission: str):
    """Decorator factory to require specific permission."""
    def permission_dependency(
        user: User = Depends(require_auth),
        db: Session = Depends(get_db)
    ) -> User:
        permissions = get_user_permissions(user, db)
        
        # Admin/Owner have all permissions
        if user.role in ("admin", "owner") or "*" in permissions:
            return user
            
        if permission not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission} required"
            )
        
        return user
    
    return permission_dependency

def require_any_permission(permissions: List[str]):
    """Decorator factory to require any of the specified permissions."""
    def permission_dependency(
        user: User = Depends(require_auth),
        db: Session = Depends(get_db)
    ) -> User:
        user_permissions = get_user_permissions(user, db)
        
        # Admin/Owner have all permissions
        if user.role in ("admin", "owner") or "*" in user_permissions:
            return user
            
        has_permission = any(perm in user_permissions for perm in permissions)
        
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: One of {permissions} required"
            )
        
        return user
    
    return permission_dependency

def require_role(required_role: str):
    """Decorator factory to require specific role."""
    def role_dependency(
        user: User = Depends(require_auth)
    ) -> User:
        role_hierarchy = {"owner": 4, "admin": 3, "moderator": 2, "user": 1}
        user_level = role_hierarchy.get(user.role, 0)
        required_level = role_hierarchy.get(required_role, 999)
        
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        return user
    return role_dependency
# Convenience role dependencies
require_admin = require_role("admin")
require_moderator = require_role("moderator")
# Require either server.config.edit or system.backup for moderator-or-admin convenience
require_moderator_or_admin = lambda: require_any_permission(["server.config.edit", "system.backup"]) 

# Convenience permission dependencies
require_server_view = require_permission("server.view")
require_server_create = require_permission("server.create")
require_server_start = require_permission("server.start")
require_server_stop = require_permission("server.stop")
require_server_delete = require_permission("server.delete")
require_server_console = require_permission("server.console.view")
require_server_files = require_permission("server.files.view")
require_server_config = require_permission("server.config.view")

require_user_view = require_permission("user.view")
require_user_create = require_permission("user.create")
require_user_edit = require_permission("user.edit")
require_user_delete = require_permission("user.delete")
# Use role.view for viewing roles
require_user_manage_roles = require_permission("role.view")

require_system_backup = require_permission("system.backup")
require_system_schedule = require_permission("system.schedule")
require_system_monitoring = require_permission("system.monitoring.view")
require_system_audit = require_permission("system.audit.view")
require_system_settings = require_permission("system.settings.view")
require_system_settings_edit = require_permission("system.settings.edit")

def log_user_action(user: User, action: str, resource_type: Optional[str] = None,
                   resource_id: Optional[str] = None, details: Optional[dict] = None,
                   request: Optional[Request] = None, db: Optional[Session] = None):
    """Helper to log user actions."""
    if not db:
        return
    
    try:
        # Import here to avoid circular import
        from user_service import UserService
        user_service = UserService(db)
        
        ip_address = None
        user_agent = None
        
        if request:
            ip_address = get_client_ip(request)
            user_agent = get_user_agent(request)
        
        user_service.log_audit_action(
            user_id=user.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent
        )
    except ImportError:
        logger.warning("UserService not available for audit logging")
