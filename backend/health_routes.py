from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
import psutil
import sys
import os

from database import get_db, engine
from auth import get_current_active_user
from models import User
from docker_manager import DockerManager

router = APIRouter(prefix="/health", tags=["health"])

class SystemInfo(BaseModel):
    python_version: str
    platform: str
    cpu_count: int
    memory_total_gb: float
    memory_available_gb: float
    memory_used_percent: float
    disk_total_gb: float
    disk_used_gb: float
    disk_used_percent: float
    uptime_hours: float
    load_average: Optional[tuple]

class DatabaseHealth(BaseModel):
    connected: bool
    database_type: str
    total_tables: int
    user_count: int
    error: Optional[str]

class DockerHealth(BaseModel):
    connected: bool
    version: Optional[str]
    containers_running: int
    containers_total: int
    images_count: int
    error: Optional[str]

class ApplicationHealth(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    ai_monitoring: bool
    scheduler_running: bool
    
class OverallHealth(BaseModel):
    status: str  # healthy, warning, error
    timestamp: datetime
    system_info: SystemInfo
    database: DatabaseHealth
    docker: DockerHealth
    application: ApplicationHealth

def get_docker_manager() -> DockerManager:
    return DockerManager()

@router.get("/system-info", response_model=SystemInfo)
async def get_system_info():
    """Get detailed system information."""
    # CPU and memory info
    cpu_count = psutil.cpu_count()
    memory = psutil.virtual_memory()
    memory_total_gb = memory.total / (1024**3)
    memory_available_gb = memory.available / (1024**3)
    memory_used_percent = memory.percent
    
    # Disk info
    disk = psutil.disk_usage('/')
    disk_total_gb = disk.total / (1024**3)
    disk_used_gb = disk.used / (1024**3)
    disk_used_percent = (disk.used / disk.total) * 100
    
    # System uptime
    boot_time = psutil.boot_time()
    uptime_seconds = datetime.now().timestamp() - boot_time
    uptime_hours = uptime_seconds / 3600
    
    # Load average (Unix-like systems only)
    load_average = None
    try:
        if hasattr(os, 'getloadavg'):
            load_average = os.getloadavg()
    except (OSError, AttributeError):
        pass
    
    return SystemInfo(
        python_version=sys.version,
        platform=sys.platform,
        cpu_count=cpu_count,
        memory_total_gb=round(memory_total_gb, 2),
        memory_available_gb=round(memory_available_gb, 2),
        memory_used_percent=round(memory_used_percent, 2),
        disk_total_gb=round(disk_total_gb, 2),
        disk_used_gb=round(disk_used_gb, 2),
        disk_used_percent=round(disk_used_percent, 2),
        uptime_hours=round(uptime_hours, 2),
        load_average=load_average
    )

@router.get("/database", response_model=DatabaseHealth)
async def get_database_health(db: Session = Depends(get_db)):
    """Get database health status."""
    try:
        # Test database connection
        result = db.execute("SELECT 1")
        result.fetchone()
        
        # Get database type
        db_url = str(engine.url)
        if "postgresql" in db_url:
            database_type = "PostgreSQL"
        elif "sqlite" in db_url:
            database_type = "SQLite"
        else:
            database_type = "Unknown"
        
        # Count tables
        inspector = None
        total_tables = 0
        try:
            from sqlalchemy import inspect
            inspector = inspect(engine)
            total_tables = len(inspector.get_table_names())
        except Exception:
            pass
        
        # Count users
        user_count = db.query(User).count()
        
        return DatabaseHealth(
            connected=True,
            database_type=database_type,
            total_tables=total_tables,
            user_count=user_count,
            error=None
        )
        
    except Exception as e:
        return DatabaseHealth(
            connected=False,
            database_type="Unknown",
            total_tables=0,
            user_count=0,
            error=str(e)
        )

@router.get("/docker", response_model=DockerHealth)
async def get_docker_health():
    """Get Docker daemon health status."""
    try:
        docker_manager = get_docker_manager()
        client = docker_manager.client
        
        # Get Docker version
        version_info = client.version()
        version = version_info.get('Version', 'Unknown')
        
        # Count containers
        containers = client.containers.list(all=True)
        containers_total = len(containers)
        containers_running = len([c for c in containers if c.status == 'running'])
        
        # Count images
        images = client.images.list()
        images_count = len(images)
        
        return DockerHealth(
            connected=True,
            version=version,
            containers_running=containers_running,
            containers_total=containers_total,
            images_count=images_count,
            error=None
        )
        
    except Exception as e:
        return DockerHealth(
            connected=False,
            version=None,
            containers_running=0,
            containers_total=0,
            images_count=0,
            error=str(e)
        )

@router.get("/application", response_model=ApplicationHealth)
async def get_application_health():
    """Get application health status."""
    # Application uptime (simplified - would need to track actual start time)
    uptime_seconds = 0  # This would be tracked from app startup
    
    # Check AI monitoring status
    ai_monitoring = False
    try:
        from ai_error_fixer import get_ai_status
        ai_status = get_ai_status()
        ai_monitoring = ai_status.get('monitoring', False)
    except Exception:
        pass
    
    # Check scheduler status
    scheduler_running = False
    try:
        from scheduler import get_scheduler
        scheduler = get_scheduler()
        scheduler_running = scheduler.scheduler.running if scheduler else False
    except Exception:
        pass
    
    return ApplicationHealth(
        status="healthy",
        version="1.0.0",  # This should come from a version file or config
        uptime_seconds=uptime_seconds,
        ai_monitoring=ai_monitoring,
        scheduler_running=scheduler_running
    )

@router.get("/", response_model=OverallHealth)
async def get_overall_health(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive health status."""
    # Get all health components
    system_info = await get_system_info()
    database = await get_database_health(db)
    docker = await get_docker_health()
    application = await get_application_health()
    
    # Determine overall status
    status = "healthy"
    
    if not database.connected or not docker.connected:
        status = "error"
    elif (system_info.memory_used_percent > 90 or 
          system_info.disk_used_percent > 90 or
          docker.containers_running == 0):
        status = "warning"
    
    return OverallHealth(
        status=status,
        timestamp=datetime.utcnow(),
        system_info=system_info,
        database=database,
        docker=docker,
        application=application
    )

@router.get("/quick")
async def get_quick_health():
    """Get a quick health check (no authentication required)."""
    try:
        # Quick database test
        from database import engine
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    
    # Quick Docker test
    try:
        docker_manager = get_docker_manager()
        docker_manager.client.ping()
        docker_ok = True
    except Exception:
        docker_ok = False
    
    # System resources check
    memory = psutil.virtual_memory()
    memory_ok = memory.percent < 95
    
    disk = psutil.disk_usage('/')
    disk_ok = (disk.used / disk.total) < 0.95
    
    overall_status = "ok" if all([db_ok, docker_ok, memory_ok, disk_ok]) else "error"
    
    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {
            "database": db_ok,
            "docker": docker_ok,
            "memory": memory_ok,
            "disk": disk_ok
        }
    }
