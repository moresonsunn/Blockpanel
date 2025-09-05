from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta
import logging
from passlib.context import CryptContext
import secrets

from models import User, Role, Permission, UserSession, AuditLog
from database import get_db

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Default permissions for the system
DEFAULT_PERMISSIONS = {
    # Server permissions
    "server.view": {"description": "View server list and details", "category": "server"},
    "server.create": {"description": "Create new servers", "category": "server"},
    "server.start": {"description": "Start servers", "category": "server"},
    "server.stop": {"description": "Stop servers", "category": "server"},
    "server.delete": {"description": "Delete servers", "category": "server"},
    "server.console": {"description": "Access server console", "category": "server"},
    "server.files": {"description": "Access server files", "category": "server"},
    "server.config": {"description": "Modify server configuration", "category": "server"},
    
    # User management permissions
    "user.view": {"description": "View user list and details", "category": "user"},
    "user.create": {"description": "Create new users", "category": "user"},
    "user.edit": {"description": "Edit user details", "category": "user"},
    "user.delete": {"description": "Delete users", "category": "user"},
    "user.manage_roles": {"description": "Manage user roles", "category": "user"},
    
    # System permissions
    "system.backup": {"description": "Create and manage backups", "category": "system"},
    "system.schedule": {"description": "Manage scheduled tasks", "category": "system"},
    "system.monitoring": {"description": "View system monitoring", "category": "system"},
    "system.audit": {"description": "View audit logs", "category": "system"},
    "system.settings": {"description": "Manage system settings", "category": "system"},
}

# Default roles with their permissions
DEFAULT_ROLES = {
    "admin": {
        "description": "Full system administrator",
        "permissions": list(DEFAULT_PERMISSIONS.keys()),
        "is_system": True
    },
    "moderator": {
        "description": "Server moderator with limited admin rights",
        "permissions": [
            "server.view", "server.start", "server.stop", "server.console",
            "server.files", "server.config", "system.backup", "user.view"
        ],
        "is_system": True
    },
    "user": {
        "description": "Regular user with basic access",
        "permissions": ["server.view"],
        "is_system": True
    }
}

class UserService:
    """Comprehensive user management service similar to Crafty Controller."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def initialize_default_permissions_and_roles(self):
        """Initialize default permissions and roles in the database."""
        # Create permissions
        for perm_name, perm_data in DEFAULT_PERMISSIONS.items():
            existing_perm = self.db.query(Permission).filter(Permission.name == perm_name).first()
            if not existing_perm:
                permission = Permission(
                    name=perm_name,
                    description=perm_data["description"],
                    category=perm_data["category"]
                )
                self.db.add(permission)
        
        # Create roles
        for role_name, role_data in DEFAULT_ROLES.items():
            existing_role = self.db.query(Role).filter(Role.name == role_name).first()
            if not existing_role:
                role = Role(
                    name=role_name,
                    description=role_data["description"],
                    permissions=role_data["permissions"],
                    is_system=role_data["is_system"]
                )
                self.db.add(role)
            else:
                # Update permissions for existing system roles
                if existing_role.is_system:
                    existing_role.permissions = role_data["permissions"]
        
        self.db.commit()
        logger.info("Initialized default permissions and roles")
    
    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        return pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        return self.db.query(User).filter(User.id == user_id).first()
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        return self.db.query(User).filter(User.username == username).first()
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        return self.db.query(User).filter(User.email == email).first()
    
    def create_user(self, username: str, email: str, password: str, role: str = "user", 
                   full_name: Optional[str] = None, created_by: Optional[int] = None) -> User:
        """Create a new user."""
        # Check if username or email already exists
        if self.get_user_by_username(username):
            raise ValueError(f"Username '{username}' already exists")
        if self.get_user_by_email(email):
            raise ValueError(f"Email '{email}' already exists")
        
        # Validate role exists
        role_obj = self.db.query(Role).filter(Role.name == role).first()
        if not role_obj:
            raise ValueError(f"Role '{role}' does not exist")
        
        # Create user
        user = User(
            username=username,
            email=email,
            hashed_password=self.hash_password(password),
            role=role,
            full_name=full_name,
            must_change_password=True  # Force password change on first login
        )
        
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        
        # Log the action
        self.log_audit_action(
            user_id=created_by,
            action="user.create",
            resource_type="user",
            resource_id=str(user.id),
            details={"username": username, "email": email, "role": role}
        )
        
        logger.info(f"Created user: {username} with role: {role}")
        return user
    
    def update_user(self, user_id: int, updates: Dict[str, Any], updated_by: Optional[int] = None) -> User:
        """Update user details."""
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError(f"User with ID {user_id} not found")
        
        # Handle password updates
        if "password" in updates:
            updates["hashed_password"] = self.hash_password(updates.pop("password"))
            updates["must_change_password"] = False
        
        # Handle role updates
        if "role" in updates:
            role_obj = self.db.query(Role).filter(Role.name == updates["role"]).first()
            if not role_obj:
                raise ValueError(f"Role '{updates['role']}' does not exist")
        
        # Apply updates
        for key, value in updates.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        self.db.commit()
        self.db.refresh(user)
        
        # Log the action
        self.log_audit_action(
            user_id=updated_by,
            action="user.edit",
            resource_type="user",
            resource_id=str(user.id),
            details={"updates": list(updates.keys())}
        )
        
        logger.info(f"Updated user: {user.username}")
        return user
    
    def delete_user(self, user_id: int, deleted_by: Optional[int] = None) -> bool:
        """Delete a user (soft delete by deactivating)."""
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError(f"User with ID {user_id} not found")
        
        if user.role == "admin" and self.count_active_admins() <= 1:
            raise ValueError("Cannot delete the last active admin user")
        
        # Deactivate user instead of deleting
        user.is_active = False
        self.db.commit()
        
        # Invalidate all user sessions
        self.invalidate_user_sessions(user_id)
        
        # Log the action
        self.log_audit_action(
            user_id=deleted_by,
            action="user.delete",
            resource_type="user",
            resource_id=str(user.id),
            details={"username": user.username}
        )
        
        logger.info(f"Deactivated user: {user.username}")
        return True
    
    def list_users(self, include_inactive: bool = False, page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """List users with pagination."""
        query = self.db.query(User)
        
        if not include_inactive:
            query = query.filter(User.is_active == True)
        
        total = query.count()
        users = query.offset((page - 1) * page_size).limit(page_size).all()
        
        return {
            "users": users,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    
    def count_active_admins(self) -> int:
        """Count active admin users."""
        return self.db.query(User).filter(
            and_(User.role == "admin", User.is_active == True)
        ).count()
    
    def authenticate_user(self, username: str, password: str, ip_address: Optional[str] = None) -> Optional[User]:
        """Authenticate a user and handle login attempts."""
        user = self.get_user_by_username(username)
        if not user:
            return None
        
        # Check if user is locked
        if user.locked_until and user.locked_until > datetime.utcnow():
            logger.warning(f"User {username} is locked until {user.locked_until}")
            return None
        
        if not user.is_active:
            logger.warning(f"Inactive user {username} attempted login")
            return None
        
        if self.verify_password(password, user.hashed_password):
            # Successful login - reset failed attempts
            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login = datetime.utcnow()
            user.last_login_ip = ip_address
            self.db.commit()
            
            # Log successful login
            self.log_audit_action(
                user_id=user.id,
                action="user.login",
                resource_type="user",
                resource_id=str(user.id),
                details={"success": True},
                ip_address=ip_address
            )
            
            logger.info(f"User {username} logged in successfully")
            return user
        else:
            # Failed login - increment attempts
            user.failed_login_attempts += 1
            
            # Lock user after 5 failed attempts
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=30)
                logger.warning(f"User {username} locked due to failed login attempts")
            
            self.db.commit()
            
            # Log failed login
            self.log_audit_action(
                user_id=user.id,
                action="user.login",
                resource_type="user",
                resource_id=str(user.id),
                details={"success": False, "failed_attempts": user.failed_login_attempts},
                ip_address=ip_address
            )
            
            logger.warning(f"Failed login attempt for user {username}")
            return None
    
    def create_user_session(self, user: User, ip_address: Optional[str] = None, 
                           user_agent: Optional[str] = None) -> UserSession:
        """Create a new user session."""
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=24)  # 24 hour sessions
        
        session = UserSession(
            user_id=user.id,
            session_token=session_token,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at
        )
        
        self.db.add(session)
        self.db.commit()
        
        logger.info(f"Created session for user {user.username}")
        return session
    
    def get_user_by_session_token(self, session_token: str) -> Optional[User]:
        """Get user by session token."""
        session = self.db.query(UserSession).filter(
            and_(
                UserSession.session_token == session_token,
                UserSession.is_active == True,
                UserSession.expires_at > datetime.utcnow()
            )
        ).first()
        
        if session:
            return session.user
        return None
    
    def invalidate_session(self, session_token: str) -> bool:
        """Invalidate a session."""
        session = self.db.query(UserSession).filter(
            UserSession.session_token == session_token
        ).first()
        
        if session:
            session.is_active = False
            self.db.commit()
            return True
        return False
    
    def invalidate_user_sessions(self, user_id: int) -> int:
        """Invalidate all sessions for a user."""
        count = self.db.query(UserSession).filter(
            and_(UserSession.user_id == user_id, UserSession.is_active == True)
        ).update({"is_active": False})
        
        self.db.commit()
        logger.info(f"Invalidated {count} sessions for user {user_id}")
        return count
    
    def get_user_permissions(self, user: User) -> List[str]:
        """Get all permissions for a user based on their role."""
        role = self.db.query(Role).filter(Role.name == user.role).first()
        if role:
            return role.permissions or []
        return []
    
    def user_has_permission(self, user: User, permission: str) -> bool:
        """Check if user has a specific permission."""
        permissions = self.get_user_permissions(user)
        return permission in permissions
    
    def log_audit_action(self, action: str, resource_type: Optional[str] = None,
                        resource_id: Optional[str] = None, details: Optional[Dict] = None,
                        user_id: Optional[int] = None, ip_address: Optional[str] = None,
                        user_agent: Optional[str] = None):
        """Log an audit action."""
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        self.db.add(audit_log)
        self.db.commit()
    
    def get_audit_logs(self, user_id: Optional[int] = None, action: Optional[str] = None,
                      page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """Get audit logs with filtering and pagination."""
        query = self.db.query(AuditLog)
        
        if user_id:
            query = query.filter(AuditLog.user_id == user_id)
        if action:
            query = query.filter(AuditLog.action == action)
        
        query = query.order_by(AuditLog.timestamp.desc())
        
        total = query.count()
        logs = query.offset((page - 1) * page_size).limit(page_size).all()
        
        return {
            "logs": logs,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    
    def get_roles(self) -> List[Role]:
        """Get all available roles."""
        return self.db.query(Role).all()
    
    def get_permissions(self) -> List[Permission]:
        """Get all available permissions."""
        return self.db.query(Permission).all()
