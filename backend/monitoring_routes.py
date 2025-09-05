from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from database import get_db
from models import User, ServerPerformance
from auth import require_auth, require_admin, require_moderator
from docker_manager import DockerManager

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

class ServerMetrics(BaseModel):
    server_name: str
    timestamp: datetime
    tps: Optional[str]
    cpu_usage: Optional[str] 
    memory_usage: Optional[str]
    memory_total: Optional[str]
    player_count: int
    metrics: Optional[Dict[str, Any]]

class SystemHealth(BaseModel):
    total_servers: int
    running_servers: int
    stopped_servers: int
    total_memory_gb: float
    used_memory_gb: float
    cpu_usage_percent: float
    disk_usage_percent: Optional[float]
    uptime_hours: Optional[float]

class AlertRule(BaseModel):
    id: Optional[int]
    name: str
    server_name: Optional[str]  # None for global rules
    metric_type: str  # cpu, memory, tps, player_count
    threshold_value: float
    comparison: str  # greater_than, less_than, equals
    is_active: bool
    created_at: Optional[datetime]

def get_docker_manager() -> DockerManager:
    return DockerManager()

@router.get("/system-health", response_model=SystemHealth)
async def get_system_health(
    current_user: User = Depends(require_auth)
):
    """Get overall system health metrics."""
    try:
        docker_manager = get_docker_manager()
        servers = docker_manager.list_servers()
        
        total_servers = len(servers)
        running_servers = len([s for s in servers if s.get("status") == "running"])
        stopped_servers = total_servers - running_servers
        
        # Calculate memory usage across all servers
        total_memory_gb = 0.0
        used_memory_gb = 0.0
        cpu_usage_total = 0.0
        server_count_with_stats = 0
        
        for server in servers:
            try:
                stats = docker_manager.get_server_stats(server.get("id"))
                if stats and "memory_limit_mb" in stats and "memory_usage_mb" in stats:
                    total_memory_gb += stats["memory_limit_mb"] / 1024.0
                    used_memory_gb += stats["memory_usage_mb"] / 1024.0
                    
                if stats and "cpu_percent" in stats:
                    cpu_usage_total += stats["cpu_percent"]
                    server_count_with_stats += 1
                    
            except Exception:
                continue  # Skip servers that can't provide stats
        
        avg_cpu_usage = cpu_usage_total / server_count_with_stats if server_count_with_stats > 0 else 0.0
        
        # Get system disk usage (simplified)
        import shutil
        try:
            disk_usage = shutil.disk_usage("/")
            disk_usage_percent = (disk_usage.used / disk_usage.total) * 100
        except:
            disk_usage_percent = None
        
        return SystemHealth(
            total_servers=total_servers,
            running_servers=running_servers,
            stopped_servers=stopped_servers,
            total_memory_gb=round(total_memory_gb, 2),
            used_memory_gb=round(used_memory_gb, 2),
            cpu_usage_percent=round(avg_cpu_usage, 2),
            disk_usage_percent=round(disk_usage_percent, 2) if disk_usage_percent else None,
            uptime_hours=None  # Could be implemented with system uptime
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get system health: {e}")

@router.get("/servers/{server_name}/metrics", response_model=List[ServerMetrics])
async def get_server_metrics(
    server_name: str,
    hours: int = Query(24, description="Hours of metrics to retrieve"),
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get historical metrics for a specific server."""
    start_time = datetime.utcnow() - timedelta(hours=hours)
    
    metrics = db.query(ServerPerformance).filter(
        ServerPerformance.server_name == server_name,
        ServerPerformance.timestamp >= start_time
    ).order_by(ServerPerformance.timestamp.desc()).all()
    
    return [
        ServerMetrics(
            server_name=metric.server_name,
            timestamp=metric.timestamp,
            tps=metric.tps,
            cpu_usage=metric.cpu_usage,
            memory_usage=metric.memory_usage,
            memory_total=metric.memory_total,
            player_count=metric.player_count or 0,
            metrics=metric.metrics
        )
        for metric in metrics
    ]

@router.post("/servers/{server_name}/metrics")
async def record_server_metrics(
    server_name: str,
    metrics_data: Dict[str, Any],
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Record new metrics for a server."""
    try:
        # Extract key metrics
        tps = str(metrics_data.get("tps", "")) if metrics_data.get("tps") else None
        cpu_usage = str(metrics_data.get("cpu_usage", "")) if metrics_data.get("cpu_usage") else None
        memory_usage = str(metrics_data.get("memory_usage", "")) if metrics_data.get("memory_usage") else None
        memory_total = str(metrics_data.get("memory_total", "")) if metrics_data.get("memory_total") else None
        player_count = int(metrics_data.get("player_count", 0))
        
        # Store metrics
        performance_record = ServerPerformance(
            server_name=server_name,
            timestamp=datetime.utcnow(),
            tps=tps,
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            memory_total=memory_total,
            player_count=player_count,
            metrics=metrics_data
        )
        
        db.add(performance_record)
        db.commit()
        
        return {"message": "Metrics recorded successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record metrics: {e}")

@router.get("/servers/{server_name}/current-stats")
async def get_current_server_stats(
    server_name: str,
    current_user: User = Depends(require_auth)
):
    """Get real-time stats for a server."""
    try:
        docker_manager = get_docker_manager()
        servers = docker_manager.list_servers()
        
        # Find the server
        target_server = None
        for server in servers:
            if server.get("name") == server_name:
                target_server = server
                break
        
        if not target_server:
            raise HTTPException(status_code=404, detail="Server not found")
        
        container_id = target_server.get("id")
        if not container_id:
            raise HTTPException(status_code=404, detail="Container ID not found")
        
        # Get current stats
        stats = docker_manager.get_server_stats(container_id)
        
        # Get server info for additional context
        info = docker_manager.get_server_info(container_id)
        
        # Combine stats with server info
        current_stats = {
            **stats,
            "server_name": server_name,
            "status": target_server.get("status"),
            "java_version": info.get("java_version"),
            "server_type": info.get("type"),
            "server_version": info.get("version"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return current_stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get current stats: {e}")

@router.get("/alerts")
async def get_monitoring_alerts(
    current_user: User = Depends(require_moderator)
):
    """Get monitoring alerts/notifications."""
    # This is a placeholder for a more sophisticated alerting system
    # In practice, you'd have a database table for alerts and rules
    
    sample_alerts = [
        {
            "id": 1,
            "type": "warning",
            "message": "High CPU usage detected on server 'survival-world'",
            "timestamp": datetime.utcnow() - timedelta(minutes=15),
            "acknowledged": False
        },
        {
            "id": 2,
            "type": "info",
            "message": "Server 'creative-build' restarted successfully",
            "timestamp": datetime.utcnow() - timedelta(hours=2),
            "acknowledged": True
        }
    ]
    
    return {"alerts": sample_alerts}

@router.get("/dashboard-data")
async def get_dashboard_data(
    current_user: User = Depends(require_auth)
):
    """Get comprehensive dashboard data."""
    try:
        docker_manager = get_docker_manager()
        servers = docker_manager.list_servers()
        
        # Server status overview
        server_overview = []
        for server in servers:
            try:
                container_id = server.get("id")
                stats = docker_manager.get_server_stats(container_id) if container_id else {}
                
                server_overview.append({
                    "name": server.get("name"),
                    "status": server.get("status"),
                    "cpu_percent": stats.get("cpu_percent", 0),
                    "memory_percent": stats.get("memory_percent", 0),
                    "memory_usage_mb": stats.get("memory_usage_mb", 0),
                    "player_count": 0,  # Would need to parse from logs or use RCON
                })
            except Exception:
                server_overview.append({
                    "name": server.get("name", "Unknown"),
                    "status": "error",
                    "cpu_percent": 0,
                    "memory_percent": 0,
                    "memory_usage_mb": 0,
                    "player_count": 0
                })
        
        # System totals
        total_servers = len(servers)
        running_servers = len([s for s in server_overview if s["status"] == "running"])
        total_cpu = sum(s["cpu_percent"] for s in server_overview)
        avg_cpu = total_cpu / len(server_overview) if server_overview else 0
        total_memory_mb = sum(s["memory_usage_mb"] for s in server_overview)
        
        return {
            "system_overview": {
                "total_servers": total_servers,
                "running_servers": running_servers,
                "stopped_servers": total_servers - running_servers,
                "avg_cpu_percent": round(avg_cpu, 2),
                "total_memory_mb": round(total_memory_mb, 2)
            },
            "server_overview": server_overview,
            "recent_alerts": [],  # Would come from alerts system
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard data: {e}")

@router.delete("/metrics/cleanup")
async def cleanup_old_metrics(
    days: int = Query(30, description="Delete metrics older than this many days"),
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Clean up old performance metrics."""
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    deleted_count = db.query(ServerPerformance).filter(
        ServerPerformance.timestamp < cutoff_date
    ).delete()
    
    db.commit()
    
    return {
        "message": f"Cleaned up {deleted_count} old metric records older than {days} days"
    }
