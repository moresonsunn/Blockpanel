from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")  # admin, moderator, user
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    # Relationships
    scheduled_tasks = relationship("ScheduledTask", back_populates="created_by_user")

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

class ServerTemplate(Base):
    __tablename__ = "server_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    server_type = Column(String, nullable=False)
    minecraft_version = Column(String, nullable=False)
    loader_version = Column(String, nullable=True)
    min_ram = Column(String, default="1024M")
    max_ram = Column(String, default="2048M")
    java_version = Column(String, default="21")
    
    # JSON field for additional configuration
    config = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))

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
