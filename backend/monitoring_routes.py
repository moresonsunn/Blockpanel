from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, cast
from datetime import datetime, timedelta

from database import get_db
from models import User, ServerPerformance, IntegrityReport
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


class IntegrityIssue(BaseModel):
    code: Optional[str]
    message: Optional[str]
    path: Optional[str]
    details: Optional[Dict[str, Any]]


class IntegrityReportItem(BaseModel):
    id: int
    server_name: Optional[str]
    status: str
    issues: List[IntegrityIssue]
    issue_count: int
    metadata: Optional[Dict[str, Any]]
    metric_value: Optional[float]
    threshold: Optional[float]
    checked_at: datetime
    task_id: Optional[int]
    task_name: Optional[str]


class IntegrityReportSummary(BaseModel):
    total: int
    by_status: Dict[str, int]
    server_status: Dict[str, str]


class IntegrityReportList(BaseModel):
    reports: List[IntegrityReportItem]
    summary: IntegrityReportSummary

_manager_cache = None


def get_docker_manager():
    global _manager_cache
    if _manager_cache is None:
        _manager_cache = get_runtime_manager_or_docker()
    return _manager_cache


def _coerce_issue_entries(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
            if isinstance(parsed, dict):
                return [parsed]
        except Exception:
            return []
    return []


def _coerce_metadata(raw: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
    return None

@router.get("/system-health", response_model=SystemHealth)
async def get_system_health(
    current_user: User = Depends(require_auth)
):
    """Get overall system health metrics."""
    try:
        docker_manager = get_docker_manager()
        servers = docker_manager.list_servers()
        stats_cache = docker_manager.get_bulk_server_stats(ttl_seconds=5)
        
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
                container_id = cast(Optional[str], server.get("id"))
                if not container_id:
                    continue
                stats = stats_cache.get(container_id) if isinstance(stats_cache, dict) else docker_manager.get_server_stats_cached(container_id)
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

@router.get("/integrity-reports", response_model=IntegrityReportList)
async def list_integrity_reports(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db),
    server_name: Optional[str] = Query(None, description="Filter by server name"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (ok|warning|error)"),
    limit: int = Query(10, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """Return recent integrity reports with lightweight summary metadata."""

    base_query = db.query(IntegrityReport)
    if server_name:
        base_query = base_query.filter(IntegrityReport.server_name == server_name)

    if status_filter:
        base_query = base_query.filter(IntegrityReport.status == status_filter.lower())

    total = base_query.count()

    reports_db = (
        base_query
        .options(joinedload(IntegrityReport.task))
        .order_by(IntegrityReport.checked_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    by_status: Dict[str, int] = {}
    server_status: Dict[str, str] = {}
    response_reports: List[IntegrityReportItem] = []

    for report in reports_db:
        status_value = str(getattr(report, "status", "") or "").lower() or "unknown"
        by_status[status_value] = by_status.get(status_value, 0) + 1

        server_name_val = cast(Optional[str], getattr(report, "server_name", None))
        if server_name_val and server_name_val not in server_status:
            server_status[server_name_val] = status_value

        issue_entries = _coerce_issue_entries(getattr(report, "issues", []))
        issues_serialized = [
            IntegrityIssue(
                code=item.get("code"),
                message=item.get("message"),
                path=item.get("path"),
                details=item.get("details") if isinstance(item.get("details"), dict) else None
            )
            for item in issue_entries
        ]

        metadata_obj = _coerce_metadata(getattr(report, "metadata_payload", None))

        response_reports.append(
            IntegrityReportItem(
                id=cast(int, getattr(report, "id")),
                server_name=server_name_val,
                status=status_value,
                issues=issues_serialized,
                issue_count=len(issues_serialized),
                metadata=metadata_obj,
                metric_value=cast(Optional[float], getattr(report, "metric_value", None)),
                threshold=cast(Optional[float], getattr(report, "threshold", None)),
                checked_at=cast(datetime, getattr(report, "checked_at")),
                task_id=cast(Optional[int], getattr(report, "task_id", None)),
                task_name=cast(Optional[str], getattr(getattr(report, "task", None), "name", None))
            )
        )

    for key in ("ok", "warning", "error"):
        by_status.setdefault(key, 0)

    summary = IntegrityReportSummary(
        total=total,
        by_status=by_status,
        server_status=server_status
    )

    return IntegrityReportList(reports=response_reports, summary=summary)

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
    """Return the latest known stats for a server."""
    try:
        docker_manager = get_docker_manager()
        servers = docker_manager.list_servers()

        target_server = next((s for s in servers if s.get("name") == server_name), None)
        if not target_server:
            raise HTTPException(status_code=404, detail="Server not found")

        container_id = cast(Optional[str], target_server.get("id"))
        stats: Dict[str, Any] = {}
        if container_id:
            try:
                fetched = docker_manager.get_server_stats(container_id)
                if isinstance(fetched, dict):
                    stats = fetched
            except Exception:
                stats = {}

        players_raw = stats.get("player_count")
        if isinstance(players_raw, list):
            player_count = len(players_raw)
        else:
            try:
                player_count = int(players_raw) if players_raw is not None else 0
            except Exception:
                player_count = 0

        return {
            "id": target_server.get("id"),
            "container_id": container_id,
            "name": target_server.get("name"),
            "status": target_server.get("status"),
            "server_type": target_server.get("type") or target_server.get("server_type"),
            "server_version": target_server.get("version") or target_server.get("server_version"),
            "java_version": target_server.get("java_version"),
            "cpu_percent": stats.get("cpu_percent"),
            "memory_usage_mb": stats.get("memory_usage_mb"),
            "memory_percent": stats.get("memory_percent"),
            "player_count": player_count,
            "uptime_seconds": stats.get("uptime_seconds") or target_server.get("uptime_seconds"),
            "started_at": stats.get("started_at") or target_server.get("started_at"),
            "last_exit_code": target_server.get("last_exit_code"),
            "raw_stats": stats,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get server stats: {e}")

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
