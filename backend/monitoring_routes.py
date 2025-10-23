from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, cast
from datetime import datetime, timedelta

from database import get_db
from models import User, ServerPerformance
from auth import require_auth, require_admin, require_moderator, get_user_permissions, verify_token, get_user_by_username
from runtime_adapter import get_runtime_manager_or_docker
from fastapi.responses import StreamingResponse
import asyncio
import json

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

_manager_cache = None


def get_docker_manager():
    global _manager_cache
    if _manager_cache is None:
        _manager_cache = get_runtime_manager_or_docker()
    return _manager_cache

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


@router.get("/dashboard-data")
async def get_dashboard_data(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Compact dashboard payload expected by the frontend.
    Returns system health summary and a short list of servers with statuses
    and a small alerts summary. Lightweight and permission-guarded.
    """
    try:
        # Reuse system health
        health = await get_system_health(current_user=current_user)

        dm = get_docker_manager()
        servers = dm.list_servers()
        # Provide a small set of server fields for the dashboard
        servers_summary = [
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "status": s.get("status"),
                "host_port": s.get("host_port") if isinstance(s.get("host_port"), (str, int)) else None,
                "memory_mb": s.get("memory_mb") if s.get("memory_mb") is not None else None,
            }
            for s in servers
        ]

        # Lightweight alerts summary derived from simple heuristics
        total = len(servers_summary)
        running = len([s for s in servers_summary if s.get("status") == "running"])
        stopped = total - running

        alerts_summary = {
            "total_servers": total,
            "running": running,
            "stopped": stopped,
            "critical": 0,
            "warnings": 0,
        }

        return {"health": health, "servers": servers_summary, "alerts_summary": alerts_summary}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build dashboard data: {e}")


@router.get("/alerts")
async def get_alerts(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Return current monitoring alerts. This implementation is a lightweight
    mirror of the alerts previously composed in the SSE handler.
    """
    try:
        dm = get_docker_manager()
        servers = dm.list_servers()

        alerts: List[Dict[str, Any]] = []
        alert_id = 1

        # System-level alert: too many servers down
        total = len(servers)
        running = len([s for s in servers if s.get("status") == "running"])
        if total > 0 and running / total < 0.5:
            alerts.append({
                "id": alert_id,
                "type": "critical",
                "severity": "high",
                "message": f"More than half of servers are down ({running}/{total} running)",
                "timestamp": datetime.utcnow(),
                "acknowledged": False,
                "server_name": None,
                "category": "system"
            })
            alert_id += 1

        # Add a simple healthy summary alert
        if running > 0:
            alerts.append({
                "id": alert_id,
                "type": "info",
                "severity": "info",
                "message": f"{running} server{'s' if running != 1 else ''} running",
                "timestamp": datetime.utcnow(),
                "acknowledged": True,
                "server_name": None,
                "category": "system"
            })
            alert_id += 1

        return {"alerts": alerts, "summary": {"total": len(alerts)}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
            server_name=cast(str, metric.server_name),
            timestamp=cast(datetime, metric.timestamp),
            tps=cast(Optional[str], metric.tps),
            cpu_usage=cast(Optional[str], metric.cpu_usage),
            memory_usage=cast(Optional[str], metric.memory_usage),
            memory_total=cast(Optional[str], metric.memory_total),
            player_count=int(getattr(metric, "player_count", 0) or 0),
            metrics=cast(Optional[Dict[str, Any]], getattr(metric, "metrics", None))
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
        async def event_generator():
            """Simple SSE generator: streams container resource stats if `container_id` is set,
            otherwise streams a light system summary (server list + counts).
            This avoids complex logic in the generator and prevents use of undefined
            local variables that previously caused indentation/syntax errors.
            """
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    payload = {}
                    if container_id:
                        try:
                            stats = dm.get_server_stats(container_id)
                            payload = {"type": "resources", "container_id": container_id, "data": stats}
                        except Exception as e:
                            payload = {"type": "error", "message": f"Stats unavailable: {e}"}
                    else:
                        try:
                            servers = dm.list_servers()
                            total = len(servers)
                            running = len([s for s in servers if s.get("status") == "running"])
                            payload = {"type": "system", "total_servers": total, "running_servers": running, "servers": servers}
                        except Exception as e:
                            payload = {"type": "error", "message": f"Server list unavailable: {e}"}

                    # SSE format: data: <json>\n\n
                    yield f"data: {json.dumps(payload, default=str)}\n\n"
                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                return
            except Exception:
                return
            
            # Get server stats for running servers
            try:
                if container_id:
                    stats = docker_manager.get_server_stats(container_id)
                    
                    # High CPU usage alert
                    cpu_percent = stats.get("cpu_percent", 0)
                    if cpu_percent > 80:
                        alerts.append({
                            "id": alert_id,
                            "type": "warning",
                            "severity": "medium",
                            "message": f"High CPU usage on server '{server_name}' ({cpu_percent:.1f}%)",
                            "timestamp": datetime.utcnow() - timedelta(minutes=2),
                            "acknowledged": False,
                            "server_name": server_name,
                            "category": "performance",
                            "metric_value": cpu_percent,
                            "threshold": 80
                        })
                        alert_id += 1
                    
                    # High memory usage alert
                    memory_percent = stats.get("memory_percent", 0)
                    if memory_percent > 90:
                        alerts.append({
                            "id": alert_id,
                            "type": "critical",
                            "severity": "high",
                            "message": f"Critical memory usage on server '{server_name}' ({memory_percent:.1f}%)",
                            "timestamp": datetime.utcnow() - timedelta(minutes=1),
                            "acknowledged": False,
                            "server_name": server_name,
                            "category": "performance",
                            "metric_value": memory_percent,
                            "threshold": 90
                        })
                        alert_id += 1
                    elif memory_percent > 75:
                        alerts.append({
                            "id": alert_id,
                            "type": "warning",
                            "severity": "medium",
                            "message": f"High memory usage on server '{server_name}' ({memory_percent:.1f}%)",
                            "timestamp": datetime.utcnow() - timedelta(minutes=3),
                            "acknowledged": False,
                            "server_name": server_name,
                            "category": "performance",
                            "metric_value": memory_percent,
                            "threshold": 75
                        })
                        alert_id += 1
                    
                    # Low disk space warning (if available)
                    disk_usage = stats.get("disk_usage_percent")
                    if disk_usage and disk_usage > 85:
                        alerts.append({
                            "id": alert_id,
                            "type": "warning",
                            "severity": "medium",
                            "message": f"Low disk space on server '{server_name}' ({disk_usage:.1f}% used)",
                            "timestamp": datetime.utcnow() - timedelta(minutes=10),
                            "acknowledged": False,
                            "server_name": server_name,
                            "category": "storage",
                            "metric_value": disk_usage,
                            "threshold": 85
                        })
                        alert_id += 1
            
            except Exception as e:
                # Server stats unavailable alert
                alerts.append({
                    "id": alert_id,
                    "type": "warning",
                    "severity": "medium",
                    "message": f"Unable to retrieve stats for server '{server_name}': {str(e)[:100]}",
                    "timestamp": datetime.utcnow() - timedelta(minutes=5),
                    "acknowledged": False,
                    "server_name": server_name,
                    "category": "monitoring"
                })
                alert_id += 1
        
        # System-wide alerts
        total_servers = len(servers)
        running_servers = len([s for s in servers if s.get("status") == "running"])
        
        if total_servers > 0 and running_servers / total_servers < 0.5:
            alerts.append({
                "id": alert_id,
                "type": "critical",
                "severity": "high",
                "message": f"More than half of servers are down ({running_servers}/{total_servers} running)",
                "timestamp": datetime.utcnow() - timedelta(minutes=1),
                "acknowledged": False,
                "server_name": None,
                "category": "system"
            })
            alert_id += 1
        
        # Add some positive alerts for healthy servers
        healthy_servers = [s for s in servers if s.get("status") == "running"]
        if len(healthy_servers) > 0:
            alerts.append({
                "id": alert_id,
                "type": "success",
                "severity": "info",
                "message": f"{len(healthy_servers)} server{'s' if len(healthy_servers) != 1 else ''} running smoothly",
                "timestamp": datetime.utcnow() - timedelta(minutes=1),
                "acknowledged": True,
                "server_name": None,
                "category": "system"
            })
            alert_id += 1
        
        # Sort alerts by severity and timestamp
        severity_order = {"critical": 0, "error": 1, "warning": 2, "info": 3, "success": 4}
        alerts.sort(key=lambda x: (severity_order.get(x["type"], 3), x["timestamp"]))
        
        return {
            "alerts": alerts,
            "summary": {
                "total": len(alerts),
                "critical": len([a for a in alerts if a["type"] == "critical"]),
                "warnings": len([a for a in alerts if a["type"] == "warning"]),
                "errors": len([a for a in alerts if a["type"] == "error"]),
                "unacknowledged": len([a for a in alerts if not a["acknowledged"]])
            }
        }
        
    except Exception as e:
        # Fallback to basic system alert
        return {
            "alerts": [{
                "id": 1,
                "type": "error",
                "severity": "high",
                "message": f"Monitoring system error: {str(e)}",
                "timestamp": datetime.utcnow(),
                "acknowledged": False,
                "server_name": None,
                "category": "system"
            }],
            "summary": {
                "total": 1,
                "critical": 0,
                "warnings": 0,
                "errors": 1,
                "unacknowledged": 1
            }
        }

@router.get("/events")
async def stream_events(
    request: Request,
    container_id: str | None = None,
    token: str | None = Query(None, description="Auth token for SSE when headers aren't supported"),
    db: Session = Depends(get_db)
):
    """Server-Sent Events stream for real-time resources and alerts.
    Requires authentication. Accepts `Authorization: Bearer` header or `token` query parameter
    (useful for browsers' EventSource which cannot set headers).
    If `container_id` is provided, streams that server's resources; otherwise streams system health summary.
    """
    # Extract token from Authorization header if present
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()

    # Validate token -> resolve user
    user: User | None = None
    if token:
        try:
            payload = verify_token(token)
        except Exception:
            payload = None
        if payload and isinstance(payload, dict):
            username = payload.get("sub")
            if username:
                try:
                    user = get_user_by_username(db, username)
                except Exception:
                    user = None
        if user is None:
            try:
                # Fallback: treat token as session token
                from user_service import UserService  # local import to avoid circular
                user_service = UserService(db)
                user = user_service.get_user_by_session_token(token)
            except Exception:
                user = None

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    # Permission check
    perms = get_user_permissions(user, db)
    role_val = str(getattr(user, "role", "") or "")
    if not (role_val == "admin" or "*" in perms or "system.monitoring.view" in perms):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: system.monitoring.view required")

    dm = get_docker_manager()
    async def event_generator():
        """Yield SSE events: simple container resources when container_id is set,
        otherwise a light system summary. Keep implementation minimal to avoid
        heavy processing and undefined variable use.
        """
        try:
            while True:
                if await request.is_disconnected():
                    break
                if container_id:
                    try:
                        stats = dm.get_server_stats(container_id)
                        payload = {"type": "resources", "container_id": container_id, "data": stats}
                    except Exception as e:
                        payload = {"type": "error", "message": f"Stats unavailable: {e}"}
                else:
                    try:
                        servers = dm.list_servers()
                        total = len(servers)
                        running = len([s for s in servers if s.get("status") == "running"])
                        payload = {"type": "system", "total_servers": total, "running_servers": running}
                    except Exception as e:
                        payload = {"type": "error", "message": f"Server list unavailable: {e}"}

                yield f"data: {json.dumps(payload, default=str)}\n\n"
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            return
        except Exception:
            return

    # Return a proper StreamingResponse so EventSource sees correct Content-Type
    return StreamingResponse(event_generator(), media_type="text/event-stream")

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
