from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Permission(Base):
    __tablename__ = "permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)  # e.g., "server.create", "user.delete"
    description = Column(String, nullable=True)
    category = Column(String, nullable=False)  # "server", "user", "system", etc.
    created_at = Column(DateTime, default=datetime.utcnow)

class Role(Base):
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)  # admin, moderator, user
    description = Column(String, nullable=True)
    permissions = Column(JSON, default=list)  # List of permission names
    is_system = Column(Boolean, default=False)  # Cannot be deleted
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")  # References Role.name
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    last_login_ip = Column(String, nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    must_change_password = Column(Boolean, default=False)
    
    # Profile information
    full_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    timezone = Column(String, default="UTC")
    language = Column(String, default="en")
    
    # Settings as JSON
    preferences = Column(JSON, default=dict)
    
    # Relationships
    scheduled_tasks = relationship("ScheduledTask", back_populates="created_by_user")
    audit_logs = relationship("AuditLog", back_populates="user")
    user_sessions = relationship("UserSession", back_populates="user")

class UserSession(Base):
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_token = Column(String, unique=True, nullable=False)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Relationship
    user = relationship("User", back_populates="user_sessions")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)  # "user.create", "server.start", etc.
    resource_type = Column(String, nullable=True)  # "user", "server", "backup"
    resource_id = Column(String, nullable=True)  # ID of the affected resource
    details = Column(JSON, nullable=True)  # Additional context
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    user = relationship("User", back_populates="audit_logs")

class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    task_type = Column(String, nullable=False)  # backup, restart, command, cleanup
    server_name = Column(String, nullable=True)  # null for global tasks
    cron_expression = Column(String, nullable=False)  # cron format
    command = Column(String, nullable=True)  # for command tasks
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    
    # Foreign key to user
    created_by = Column(Integer, ForeignKey("users.id"))
    created_by_user = relationship("User", back_populates="scheduled_tasks")

## Legacy note: ServerTemplate model removed as curated templates feature was dropped.
## Existing databases will be cleaned up by init_db() dropping the legacy table if present.

class BackupTask(Base):
    __tablename__ = "backup_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    server_name = Column(String, nullable=False)
    backup_file = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    compression_type = Column(String, default="zip")
    retention_days = Column(Integer, default=30)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Auto-cleanup based on retention
    is_auto_created = Column(Boolean, default=False)

class ServerPerformance(Base):
    __tablename__ = "server_performance"
    
    id = Column(Integer, primary_key=True, index=True)
    server_name = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Performance metrics
    tps = Column(String, nullable=True)  # Ticks per second
    cpu_usage = Column(String, nullable=True)
    memory_usage = Column(String, nullable=True)
    memory_total = Column(String, nullable=True)
    player_count = Column(Integer, default=0)
    
    # Additional metrics as JSON
    metrics = Column(JSON, nullable=True)

class PlayerAction(Base):
    __tablename__ = "player_actions"
    
    id = Column(Integer, primary_key=True, index=True)
    server_name = Column(String, nullable=False)
    player_name = Column(String, nullable=False)
    action_type = Column(String, nullable=False)  # whitelist, ban, kick, op, deop
    reason = Column(String, nullable=True)
    performed_by = Column(Integer, ForeignKey("users.id"))
    performed_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)  # for bans/whitelist status