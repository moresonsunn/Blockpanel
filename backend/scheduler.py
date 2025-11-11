from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.asyncio import AsyncIOExecutor
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import logging
import asyncio
from typing import Dict, Any, Optional, cast, List

from database import SessionLocal
from models import ScheduledTask, BackupTask, IntegrityReport
from backup_manager import create_backup
from runtime_adapter import get_runtime_manager_or_docker
from config import SERVERS_ROOT
from pathlib import Path

logger = logging.getLogger(__name__)

class TaskScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler(
            executors={'default': AsyncIOExecutor()},
            timezone='UTC'
        )
        self.docker_manager = None
        
    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Task scheduler started")
            
            # Load existing tasks from database
            self.load_scheduled_tasks()
    
    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Task scheduler stopped")
    
    def get_docker_manager(self):
        """Get or create runtime manager instance."""
        if self.docker_manager is None:
            self.docker_manager = get_runtime_manager_or_docker()
        return self.docker_manager
    
    def load_scheduled_tasks(self):
        """Load all active scheduled tasks from database."""
        db = SessionLocal()
        try:
            tasks = db.query(ScheduledTask).filter(ScheduledTask.is_active == True).all()
            for task in tasks:
                try:
                    self.add_scheduled_task(task)
                    logger.info(f"Loaded scheduled task: {self._task_label(task, task.id)}")
                except Exception as e:
                    logger.error(f"Failed to load task {self._task_label(task, task.id)}: {e}")
        finally:
            db.close()
    
    def add_scheduled_task(self, task: ScheduledTask):
        """Add a scheduled task to the scheduler."""
        job_id = f"task_{task.id}"
        
        # Remove existing job if it exists
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        
        # Parse cron expression
        cron_expression = cast(str, task.cron_expression)
        cron_parts = cron_expression.split()
        if len(cron_parts) != 5:
            raise ValueError(f"Invalid cron expression: {cron_expression}")
        
        minute, hour, day, month, day_of_week = cron_parts
        
        # Create trigger
        trigger = CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone='UTC'
        )
        
        task_type = cast(str, task.task_type)

        # Add job based on task type
        if task_type == "backup":
            self.scheduler.add_job(
                self.execute_backup_task,
                trigger=trigger,
                id=job_id,
                args=[task.id],
                max_instances=1
            )
        elif task_type == "restart":
            self.scheduler.add_job(
                self.execute_restart_task,
                trigger=trigger,
                id=job_id,
                args=[task.id],
                max_instances=1
            )
        elif task_type == "command":
            self.scheduler.add_job(
                self.execute_command_task,
                trigger=trigger,
                id=job_id,
                args=[task.id],
                max_instances=1
            )
        elif task_type == "cleanup":
            self.scheduler.add_job(
                self.execute_cleanup_task,
                trigger=trigger,
                id=job_id,
                args=[task.id],
                max_instances=1
            )
        elif task_type == "integrity":
            self.scheduler.add_job(
                self.execute_integrity_task,
                trigger=trigger,
                id=job_id,
                args=[task.id],
                max_instances=1
            )
        else:
            raise ValueError(f"Unknown task type: {task_type}")
    
    def remove_scheduled_task(self, task_id: int):
        """Remove a scheduled task from the scheduler."""
        job_id = f"task_{task_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed scheduled task: {task_id}")

    def _get_task(self, db: Session, task_id: int) -> Optional[ScheduledTask]:
        task_obj = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
        if not task_obj:
            return None
        return cast(ScheduledTask, task_obj)

    def _task_label(self, task: Optional[ScheduledTask], fallback: Any) -> str:
        name_val = None
        if task is not None:
            name_val = getattr(task, "name", None)
        if isinstance(name_val, str) and name_val.strip():
            return name_val
        return str(fallback)

    @staticmethod
    def _combine_status(current: str, new_status: str) -> str:
        order = {"ok": 0, "warning": 1, "error": 2}
        current_rank = order.get(current, 0)
        new_rank = order.get(new_status, 0)
        return new_status if new_rank > current_rank else current
    
    async def execute_backup_task(self, task_id: int):
        """Execute a backup task."""
        db = SessionLocal()
        server_name: Optional[str] = None
        try:
            task_db = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not task_db:
                return

            task = cast(ScheduledTask, task_db)
            if not bool(getattr(task, "is_active", False)):
                return
            
            logger.info(f"Executing backup task: {self._task_label(task, task_id)}")
            
            # Update last run time
            setattr(task, "last_run", datetime.utcnow())
            
            try:
                # Create backup
                server_name = cast(Optional[str], getattr(task, "server_name", None))
                if not server_name:
                    raise ValueError("Backup task has no server_name configured")

                result = create_backup(server_name)
                
                # Record backup in database
                backup_record = BackupTask(
                    server_name=server_name,
                    backup_file=result["file"],
                    file_size=result["size"],
                    is_auto_created=True
                )
                db.add(backup_record)
                
                logger.info(f"Backup completed for {server_name}: {result['file']}")
                
            except Exception as e:
                logger.error(f"Backup task failed for {server_name or 'unknown'}: {e}")
            
            db.commit()
            
        finally:
            db.close()
    
    async def execute_restart_task(self, task_id: int):
        """Execute a server restart task."""
        db = SessionLocal()
        try:
            task = self._get_task(db, task_id)
            if not task or not bool(getattr(task, "is_active", False)):
                return
            
                logger.info(f"Executing restart task: {self._task_label(task, task_id)}")
            
            # Update last run time
            setattr(task, "last_run", datetime.utcnow())
            
            try:
                docker_manager = self.get_docker_manager()
                servers = docker_manager.list_servers()
                
                # Find server by name
                target_server = None
                server_name = cast(Optional[str], getattr(task, "server_name", None))
                for server in servers:
                    if server_name and server.get("name") == server_name:
                        target_server = server
                        break
                
                if target_server:
                    container_id = target_server.get("id")
                    if container_id:
                        # Stop and start server
                        docker_manager.stop_server(container_id)
                        await asyncio.sleep(5)  # Wait for graceful shutdown
                        docker_manager.start_server(container_id)
                        if server_name:
                            logger.info(f"Restarted server: {server_name}")
                    else:
                        logger.error(f"No container ID found for server: {server_name}")
                else:
                    logger.error(f"Server not found for restart task: {server_name}")
                    
            except Exception as e:
                logger.error(f"Restart task failed: {e}")
            
            db.commit()
            
        finally:
            db.close()
    
    async def execute_command_task(self, task_id: int):
        """Execute a command task."""
        db = SessionLocal()
        try:
            task = self._get_task(db, task_id)
            if not task or not bool(getattr(task, "is_active", False)):
                return
            
            task_name = cast(Optional[str], getattr(task, "name", None))
            logger.info(f"Executing command task: {task_name or task_id}")
            
            # Update last run time
            setattr(task, "last_run", datetime.utcnow())
            
            try:
                docker_manager = self.get_docker_manager()
                servers = docker_manager.list_servers()
                
                # Find server by name
                target_server = None
                server_name = cast(Optional[str], getattr(task, "server_name", None))
                for server in servers:
                    if server_name and server.get("name") == server_name:
                        target_server = server
                        break
                
                if target_server:
                    container_id = target_server.get("id")
                    command = cast(Optional[str], getattr(task, "command", None))
                    if container_id and command:
                        # Send command to server
                        docker_manager.send_command(container_id, command)
                        logger.info(f"Executed command '{command}' on {server_name}")
                    else:
                        logger.error(f"No container ID or command for server: {server_name}")
                else:
                    logger.error(f"Server not found for command task: {server_name}")
                    
            except Exception as e:
                logger.error(f"Command task failed: {e}")
            
            db.commit()
            
        finally:
            db.close()
    
    async def execute_cleanup_task(self, task_id: int):
        """Execute a cleanup task."""
        db = SessionLocal()
        try:
            task = self._get_task(db, task_id)
            if not task or not bool(getattr(task, "is_active", False)):
                return
            
            task_name = cast(Optional[str], getattr(task, "name", None))
            logger.info(f"Executing cleanup task: {task_name or task_id}")
            
            # Update last run time
            setattr(task, "last_run", datetime.utcnow())
            
            try:
                # Clean up old backups based on retention policy
                # Parse retention_days from command if provided (e.g., "retention_days=14")
                retention_days = 30
                try:
                    command_str = cast(Optional[str], getattr(task, "command", None))
                    if command_str:
                        parts = dict(
                            kv.split("=", 1) for kv in str(command_str).split(";") if "=" in kv
                        )
                        if 'retention_days' in parts:
                            retention_days = int(parts['retention_days'])
                except Exception:
                    pass

                cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
                q = db.query(BackupTask).filter(
                    BackupTask.is_auto_created == True,
                    BackupTask.created_at < cutoff_date
                )
                server_name = cast(Optional[str], getattr(task, "server_name", None))
                if server_name:
                    q = q.filter(BackupTask.server_name == server_name)
                old_backups = q.all()
                
                for backup in old_backups:
                    try:
                        # Delete backup file
                        backup_path = Path("backups") / backup.server_name / backup.backup_file
                        if backup_path.exists():
                            backup_path.unlink()
                        
                        # Remove from database
                        db.delete(backup)
                        logger.info(f"Cleaned up old backup: {backup.backup_file}")
                        
                    except Exception as e:
                        logger.error(f"Failed to clean up backup {backup.backup_file}: {e}")
                
                logger.info(f"Cleanup completed, removed {len(old_backups)} old backups older than {retention_days} days")
                
            except Exception as e:
                logger.error(f"Cleanup task failed: {e}")
            
            db.commit()
            
        finally:
            db.close()

    async def execute_integrity_task(self, task_id: int):
        """Execute an integrity verification task."""
        db = SessionLocal()
        try:
            task = self._get_task(db, task_id)
            if not task or not bool(getattr(task, "is_active", False)):
                return

            task_name = self._task_label(task, task_id)
            logger.info(f"Executing integrity task: {task_name}")

            setattr(task, "last_run", datetime.utcnow())

            status = "ok"
            issues: List[Dict[str, Any]] = []
            metadata: Dict[str, Any] = {
                "task": task_name,
                "checked_at": datetime.utcnow().isoformat()
            }

            server_name = cast(Optional[str], getattr(task, "server_name", None))

            try:
                servers_root = Path(SERVERS_ROOT)
                metadata["servers_root"] = str(servers_root)

                if server_name:
                    server_path = servers_root / server_name
                    metadata["server_name"] = server_name
                    metadata["server_path"] = str(server_path)

                    if not server_path.exists():
                        status = self._combine_status(status, "error")
                        issues.append({
                            "code": "SERVER_PATH_MISSING",
                            "message": "Server directory not found",
                            "path": str(server_path)
                        })
                    else:
                        jar_files = [jar.name for jar in server_path.glob("*.jar")]
                        metadata["jar_candidates"] = jar_files
                        if not jar_files:
                            status = self._combine_status(status, "warning")
                            issues.append({
                                "code": "JAR_MISSING",
                                "message": "No server JAR found in directory"
                            })

                        world_dir = server_path / "world"
                        metadata["world_exists"] = world_dir.exists()
                        if not world_dir.exists():
                            status = self._combine_status(status, "warning")
                            issues.append({
                                "code": "WORLD_MISSING",
                                "message": "World directory is missing"
                            })

                        latest_backup = (
                            db.query(BackupTask)
                            .filter(BackupTask.server_name == server_name)
                            .order_by(BackupTask.created_at.desc())
                            .first()
                        )

                        if latest_backup:
                            backup_created_at = getattr(latest_backup, "created_at", None)
                            created_at_iso = backup_created_at.isoformat() if isinstance(backup_created_at, datetime) else None
                            metadata["latest_backup"] = {
                                "file": getattr(latest_backup, "backup_file", None),
                                "created_at": created_at_iso,
                                "auto": bool(getattr(latest_backup, "is_auto_created", False))
                            }

                            if isinstance(backup_created_at, datetime):
                                stale_cutoff = datetime.utcnow() - timedelta(days=7)
                                if backup_created_at < stale_cutoff:
                                    status = self._combine_status(status, "warning")
                                    issues.append({
                                        "code": "BACKUP_OUTDATED",
                                        "message": "Latest backup older than 7 days"
                                    })
                        else:
                            status = self._combine_status(status, "warning")
                            issues.append({
                                "code": "NO_BACKUP",
                                "message": "No backups found for server"
                            })
                else:
                    if not servers_root.exists():
                        status = self._combine_status(status, "error")
                        issues.append({
                            "code": "SERVERS_ROOT_MISSING",
                            "message": "Servers root directory missing"
                        })
                    else:
                        metadata["server_count"] = len([p for p in servers_root.iterdir() if p.is_dir()])

            except Exception as integrity_error:
                status = "error"
                issues.append({
                    "code": "INTEGRITY_EXCEPTION",
                    "message": str(integrity_error)
                })
                logger.exception("Integrity task encountered an error")

            report = IntegrityReport(
                server_name=server_name,
                status=status,
                issues=issues,
                metadata_payload=metadata,
                checked_at=datetime.utcnow(),
                task_id=task.id
            )

            db.add(report)

            db.commit()
            logger.info(f"Integrity task completed: {task_name} -> {status}")

        finally:
            db.close()
    
    def get_next_run_time(self, cron_expression: str) -> Optional[datetime]:
        """Calculate next run time for a cron expression."""
        try:
            cron_parts = cron_expression.split()
            if len(cron_parts) != 5:
                raise ValueError("Invalid cron expression")
            
            minute, hour, day, month, day_of_week = cron_parts
            
            trigger = CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
                timezone='UTC'
            )
            
            next_fire = trigger.get_next_fire_time(None, datetime.utcnow())
            return cast(Optional[datetime], next_fire)
            
        except Exception as e:
            logger.error(f"Failed to calculate next run time: {e}")
            return None

# Global scheduler instance
task_scheduler = TaskScheduler()

def get_scheduler() -> TaskScheduler:
    """Get the global scheduler instance."""
    return task_scheduler