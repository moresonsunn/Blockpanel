# pyright: reportGeneralTypeIssues=false, reportAttributeAccessIssue=false
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta
import logging
import os
from passlib.context import CryptContext
import secrets

from models import User, Role, Permission, UserSession, AuditLog
from database import get_db

logger = logging.getLogger(__name__)

# Idle timeout for session tokens (minutes)
def _load_idle_timeout() -> int:
    try:
        val = int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", "5"))
        return max(val, 1)
    except Exception:
        return 5

SESSION_IDLE_TIMEOUT_MINUTES = _load_idle_timeout()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Comprehensive permission system inspired by Crafty Controller
DEFAULT_PERMISSIONS = {
    # Server Control Permissions
    "server.view": {"description": "View server list and basic details", "category": "server_control", "level": 1},
    "server.create": {"description": "Create new servers", "category": "server_control", "level": 3},
    "server.start": {"description": "Start servers", "category": "server_control", "level": 2},
    "server.stop": {"description": "Stop servers", "category": "server_control", "level": 2},
    "server.restart": {"description": "Restart servers", "category": "server_control", "level": 2},
    "server.kill": {"description": "Force kill servers", "category": "server_control", "level": 3},
    "server.delete": {"description": "Delete servers permanently", "category": "server_control", "level": 4},
    "server.clone": {"description": "Clone/duplicate servers", "category": "server_control", "level": 3},
    
    # Server Console & Commands
    "server.console.view": {"description": "View server console output", "category": "server_console", "level": 1},
    "server.console.send": {"description": "Send commands to server console", "category": "server_console", "level": 2},
    "server.console.history": {"description": "Access console command history", "category": "server_console", "level": 2},
    
    # Server Configuration
    "server.config.view": {"description": "View server configuration files", "category": "server_config", "level": 1},
    "server.config.edit": {"description": "Edit server configuration files", "category": "server_config", "level": 3},
    "server.properties.edit": {"description": "Edit server.properties", "category": "server_config", "level": 2},
    "server.startup.edit": {"description": "Modify server startup parameters", "category": "server_config", "level": 3},
    
    # File Management
    "server.files.view": {"description": "Browse server files and folders", "category": "server_files", "level": 1},
    "server.files.download": {"description": "Download files from server", "category": "server_files", "level": 2},
    "server.files.upload": {"description": "Upload files to server", "category": "server_files", "level": 2},
    "server.files.edit": {"description": "Edit text files on server", "category": "server_files", "level": 2},
    "server.files.delete": {"description": "Delete server files", "category": "server_files", "level": 3},
    "server.files.create": {"description": "Create new files and folders", "category": "server_files", "level": 2},
    "server.files.compress": {"description": "Create/extract archives", "category": "server_files", "level": 2},
    
    # Player Management
    "server.players.view": {"description": "View online players and stats", "category": "server_players", "level": 1},
    "server.players.kick": {"description": "Kick players from server", "category": "server_players", "level": 2},
    "server.players.ban": {"description": "Ban/unban players", "category": "server_players", "level": 2},
    "server.players.whitelist": {"description": "Manage server whitelist", "category": "server_players", "level": 2},
    "server.players.op": {"description": "Grant/revoke operator status", "category": "server_players", "level": 3},
    "server.players.chat": {"description": "Send messages as server/view chat", "category": "server_players", "level": 2},
    
    # Backup Management
    "server.backup.view": {"description": "View server backups", "category": "server_backup", "level": 1},
    "server.backup.create": {"description": "Create server backups", "category": "server_backup", "level": 2},
    "server.backup.restore": {"description": "Restore server from backup", "category": "server_backup", "level": 3},
    "server.backup.delete": {"description": "Delete server backups", "category": "server_backup", "level": 3},
    "server.backup.download": {"description": "Download backup files", "category": "server_backup", "level": 2},
    "server.backup.schedule": {"description": "Schedule automatic backups", "category": "server_backup", "level": 3},
    
    # User Management Permissions
    "user.view": {"description": "View user list and basic details", "category": "user_management", "level": 2},
    "user.create": {"description": "Create new users", "category": "user_management", "level": 3},
    "user.edit": {"description": "Edit user details and settings", "category": "user_management", "level": 3},
    "user.delete": {"description": "Delete users from system", "category": "user_management", "level": 4},
    "user.password.reset": {"description": "Reset user passwords", "category": "user_management", "level": 3},
    "user.sessions.view": {"description": "View active user sessions", "category": "user_management", "level": 3},
    "user.sessions.revoke": {"description": "Revoke user sessions", "category": "user_management", "level": 3},
    
    # Role & Permission Management
    "role.view": {"description": "View roles and permissions", "category": "role_management", "level": 2},
    "role.create": {"description": "Create custom roles", "category": "role_management", "level": 4},
    "role.edit": {"description": "Modify role permissions", "category": "role_management", "level": 4},
    "role.delete": {"description": "Delete custom roles", "category": "role_management", "level": 4},
    "role.assign": {"description": "Assign roles to users", "category": "role_management", "level": 3},
    
    # System Administration
    "system.monitoring.view": {"description": "View system monitoring and stats", "category": "system_admin", "level": 2},
    "system.logs.view": {"description": "View system and application logs", "category": "system_admin", "level": 2},
    "system.audit.view": {"description": "View audit logs and security events", "category": "system_admin", "level": 3},
    "system.settings.view": {"description": "View system settings", "category": "system_admin", "level": 2},
    "system.settings.edit": {"description": "Modify system settings", "category": "system_admin", "level": 4},
    "system.maintenance": {"description": "Perform system maintenance tasks", "category": "system_admin", "level": 4},
    "system.updates": {"description": "Manage system updates", "category": "system_admin", "level": 4},
    
    # Scheduling & Automation
    "schedule.view": {"description": "View scheduled tasks", "category": "automation", "level": 2},
    "schedule.create": {"description": "Create scheduled tasks", "category": "automation", "level": 3},
    "schedule.edit": {"description": "Modify scheduled tasks", "category": "automation", "level": 3},
    "schedule.delete": {"description": "Delete scheduled tasks", "category": "automation", "level": 3},
    "schedule.execute": {"description": "Manually execute scheduled tasks", "category": "automation", "level": 3},
    
    # Plugin & Mod Management
    "plugins.view": {"description": "View installed plugins/mods", "category": "plugin_management", "level": 1},
    "plugins.install": {"description": "Install new plugins/mods", "category": "plugin_management", "level": 3},
    "plugins.remove": {"description": "Remove plugins/mods", "category": "plugin_management", "level": 3},
    "plugins.configure": {"description": "Configure plugin settings", "category": "plugin_management", "level": 2},
    "plugins.update": {"description": "Update plugins/mods", "category": "plugin_management", "level": 3},
}

# Comprehensive role system inspired by Crafty Controller
DEFAULT_ROLES = {
    "owner": {
        "description": "System owner with unrestricted access to everything",
        "permissions": list(DEFAULT_PERMISSIONS.keys()),
        "is_system": True,
        "level": 5,
        "color": "#dc2626"  # Red
    },
    "admin": {
        "description": "System administrator with full server and user management",
        "permissions": [
            # Server Control
            "server.view", "server.create", "server.start", "server.stop", "server.restart",
            "server.kill", "server.delete", "server.clone",
            # Console & Config
            "server.console.view", "server.console.send", "server.console.history",
            "server.config.view", "server.config.edit", "server.properties.edit", "server.startup.edit",
            # Files
            "server.files.view", "server.files.download", "server.files.upload", 
            "server.files.edit", "server.files.delete", "server.files.create", "server.files.compress",
            # Players
            "server.players.view", "server.players.kick", "server.players.ban", 
            "server.players.whitelist", "server.players.op", "server.players.chat",
            # Backups
            "server.backup.view", "server.backup.create", "server.backup.restore", 
            "server.backup.delete", "server.backup.download", "server.backup.schedule",
            # Users
            "user.view", "user.create", "user.edit", "user.password.reset",
            "user.sessions.view", "user.sessions.revoke",
            # Roles (grant admin ability to manage role permissions)
            "role.view", "role.edit",
            # System
            "system.monitoring.view", "system.logs.view", "system.audit.view", "system.settings.view",
            # Scheduling
            "schedule.view", "schedule.create", "schedule.edit", "schedule.delete", "schedule.execute",
            # Plugins
            "plugins.view", "plugins.install", "plugins.remove", "plugins.configure", "plugins.update"
        ],
        "is_system": True,
        "level": 4,
        "color": "#ea580c"  # Orange
    },
    "moderator": {
        "description": "Server moderator with management rights but limited system access",
        "permissions": [
            # Server Control
            "server.view", "server.start", "server.stop", "server.restart",
            # Console & Config
            "server.console.view", "server.console.send", "server.console.history",
            "server.config.view", "server.properties.edit",
            # Files (limited)
            "server.files.view", "server.files.download", "server.files.upload", 
            "server.files.edit", "server.files.create",
            # Players
            "server.players.view", "server.players.kick", "server.players.ban", 
            "server.players.whitelist", "server.players.chat",
            # Backups
            "server.backup.view", "server.backup.create", "server.backup.download",
            # System (view only)
            "system.monitoring.view", "system.logs.view",
            # Plugins (limited)
            "plugins.view", "plugins.configure"
        ],
        "is_system": True,
        "level": 3,
        "color": "#0ea5e9"  # Blue
    },
    "helper": {
        "description": "Server helper with console access and basic management",
        "permissions": [
            # Server Control (basic)
            "server.view", "server.start", "server.stop",
            # Console & Config
            "server.console.view", "server.console.send",
            "server.config.view",
            # Files (view only)
            "server.files.view", "server.files.download",
            # Players (basic)
            "server.players.view", "server.players.kick", "server.players.chat",
            # Backups
            "server.backup.view", "server.backup.create",
            # System (view only)
            "system.monitoring.view",
            # Plugins (view only)
            "plugins.view"
        ],
        "is_system": True,
        "level": 2,
        "color": "#10b981"  # Green
    },
    "user": {
        "description": "Regular user with read-only access to assigned servers",
        "permissions": [
            # Server Control (view only)
            "server.view",
            # Console (view only)
            "server.console.view",
            "server.config.view",
            # Files (view only)
            "server.files.view", "server.files.download",
            # Players (view only)
            "server.players.view",
            # Backups (view only)
            "server.backup.view",
            # Plugins (view only)
            "plugins.view"
        ],
        "is_system": True,
        "level": 1,
        "color": "#6b7280"  # Gray
    },
    "guest": {
        "description": "Guest user with minimal read-only access",
        "permissions": [
            "server.view",
            "server.console.view",
            "server.players.view"
        ],
        "is_system": True,
        "level": 0,
        "color": "#9ca3af"  # Light Gray
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

        # Extract hashed password as str for type checkers
        hashed = str(user.hashed_password or "")
        if self.verify_password(password, hashed):
            # Successful login - reset failed attempts
            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login = datetime.utcnow()
            user.last_login_ip = ip_address
            self.db.commit()

            # Log successful login
            # Best-effort cast for type checkers
            uid = None
            try:
                uid = int(getattr(user, "id"))
            except Exception:
                pass
            self.log_audit_action(
                user_id=uid if uid is not None else None,
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
            # Safely coerce to int without upsetting type checkers
            fa = user.failed_login_attempts
            try:
                current_attempts = fa if isinstance(fa, int) else 0
            except Exception:
                current_attempts = 0
            user.failed_login_attempts = current_attempts + 1

            # Lock user after 5 failed attempts
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=30)
                logger.warning(f"User {username} locked due to failed login attempts")

            self.db.commit()

            # Log failed login
            uid = None
            try:
                uid = int(getattr(user, "id"))
            except Exception:
                pass
            self.log_audit_action(
                user_id=uid if uid is not None else None,
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
        """Create a new user session with short idle timeout."""
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(minutes=SESSION_IDLE_TIMEOUT_MINUTES)
        
        session = UserSession(
            user_id=user.id,
            session_token=session_token,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at
        )
        
        self.db.add(session)
        self.db.commit()
        
        logger.info(f"Created session for user {user.username} with {SESSION_IDLE_TIMEOUT_MINUTES}m idle timeout")
        return session
    
    def get_user_by_session_token(self, session_token: str, refresh_expiry: bool = True) -> Optional[User]:
        """Get user by session token and optionally extend idle expiry."""
        session = self.db.query(UserSession).filter(
            and_(
                UserSession.session_token == session_token,
                UserSession.is_active == True
            )
        ).first()

        if not session:
            return None

        now = datetime.utcnow()
        if not session.expires_at or session.expires_at <= now:
            try:
                session.is_active = False
                self.db.commit()
            except Exception:
                self.db.rollback()
            return None

        if refresh_expiry:
            new_expiry = now + timedelta(minutes=SESSION_IDLE_TIMEOUT_MINUTES)
            # Avoid excessive writes: only bump when inside final minute of the window
            if session.expires_at < new_expiry - timedelta(seconds=30):
                session.expires_at = new_expiry
                try:
                    self.db.commit()
                except Exception:
                    self.db.rollback()

        return session.user
    
    def invalidate_session(self, session_token: str) -> bool:
        """Invalidate a session."""
        updated = self.db.query(UserSession).filter(
            UserSession.session_token == session_token
        ).update({"is_active": False})
        self.db.commit()
        return updated > 0
    
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
            perms = role.permissions or []
            # Ensure list type
            try:
                if isinstance(perms, list):
                    return perms
                # last resort: empty list
                return []
            except Exception:
                return []
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

    def create_role(self, name: str, description: Optional[str], permissions: List[str], is_system: bool = False) -> Role:
        """Create a new custom role."""
        existing = self.db.query(Role).filter(Role.name == name).first()
        if existing:
            raise ValueError(f"Role '{name}' already exists")
        # Validate permissions exist
        valid_perms = {p.name for p in self.get_permissions()}
        invalid = [p for p in permissions if p not in valid_perms]
        if invalid:
            raise ValueError(f"Invalid permissions: {invalid}")
        role = Role(name=name, description=description, permissions=permissions, is_system=is_system)
        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)
        return role

    def update_role(self, name: str, description: Optional[str] = None, permissions: Optional[List[str]] = None) -> Role:
        """Update an existing role by name."""
        role = self.db.query(Role).filter(Role.name == name).first()
        if not role:
            raise ValueError(f"Role '{name}' not found")
        if description is not None:
            role.description = description
        if permissions is not None:
            valid_perms = {p.name for p in self.get_permissions()}
            invalid = [p for p in permissions if p not in valid_perms]
            if invalid:
                raise ValueError(f"Invalid permissions: {invalid}")
            role.permissions = permissions
        self.db.commit()
        self.db.refresh(role)
        return role

    def delete_role(self, name: str) -> bool:
        """Delete a custom role by name."""
        role = self.db.query(Role).filter(Role.name == name).first()
        if not role:
            raise ValueError(f"Role '{name}' not found")
        if role.is_system:
            raise ValueError("Cannot delete system role")
        self.db.delete(role)
        self.db.commit()
        return True

    def reset_user_password(self, user_id: int, new_password: str, force_change: bool = True, updated_by: Optional[int] = None) -> User:
        """Reset a user's password and optionally force change on next login."""
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError(f"User with ID {user_id} not found")
        user.hashed_password = self.hash_password(new_password)
        user.must_change_password = bool(force_change)
        # Also unlock and reset attempts on password reset
        user.failed_login_attempts = 0
        user.locked_until = None
        self.db.commit()
        self.db.refresh(user)
        self.log_audit_action(
            user_id=updated_by,
            action="user.password.reset",
            resource_type="user",
            resource_id=str(user.id),
            details={"force_change": bool(force_change)}
        )
        return user

    def unlock_user(self, user_id: int, updated_by: Optional[int] = None) -> User:
        """Unlock a user's account by clearing lock and failed attempts."""
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError(f"User with ID {user_id} not found")
        user.failed_login_attempts = 0
        user.locked_until = None
        self.db.commit()
        self.db.refresh(user)
        self.log_audit_action(
            user_id=updated_by,
            action="user.unlock",
            resource_type="user",
            resource_id=str(user.id),
            details={}
        )
        return user
