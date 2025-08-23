from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.asyncio import AsyncIOExecutor
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import logging
import asyncio
from typing import Dict, Any

from database import SessionLocal
from models import ScheduledTask, BackupTask
from backup_manager import create_backup
from docker_manager import DockerManager

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
    
    def get_docker_manager(self) -> DockerManager:
        """Get or create Docker manager instance."""
        if self.docker_manager is None:
            self.docker_manager = DockerManager()
        return self.docker_manager
    
    def load_scheduled_tasks(self):
        """Load all active scheduled tasks from database."""
        db = SessionLocal()
        try:
            tasks = db.query(ScheduledTask).filter(ScheduledTask.is_active == True).all()
            for task in tasks:
                try:
                    self.add_scheduled_task(task)
                    logger.info(f"Loaded scheduled task: {task.name}")
                except Exception as e:
                    logger.error(f"Failed to load task {task.name}: {e}")
        finally:
            db.close()
    
    def add_scheduled_task(self, task: ScheduledTask):
        """Add a scheduled task to the scheduler."""
        job_id = f"task_{task.id}"
        
        # Remove existing job if it exists
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        
        # Parse cron expression
        cron_parts = task.cron_expression.split()
        if len(cron_parts) != 5:
            raise ValueError(f"Invalid cron expression: {task.cron_expression}")
        
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
        
        # Add job based on task type
        if task.task_type == "backup":
            self.scheduler.add_job(
                self.execute_backup_task,
                trigger=trigger,
                id=job_id,
                args=[task.id],
                max_instances=1
            )
        elif task.task_type == "restart":
            self.scheduler.add_job(
                self.execute_restart_task,
                trigger=trigger,
                id=job_id,
                args=[task.id],
                max_instances=1
            )
        elif task.task_type == "command":
            self.scheduler.add_job(
                self.execute_command_task,
                trigger=trigger,
                id=job_id,
                args=[task.id],
                max_instances=1
            )
        elif task.task_type == "cleanup":
            self.scheduler.add_job(
                self.execute_cleanup_task,
                trigger=trigger,
                id=job_id,
                args=[task.id],
                max_instances=1
            )
        else:
            raise ValueError(f"Unknown task type: {task.task_type}")
    
    def remove_scheduled_task(self, task_id: int):
        """Remove a scheduled task from the scheduler."""
        job_id = f"task_{task_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed scheduled task: {task_id}")
    
    async def execute_backup_task(self, task_id: int):
        """Execute a backup task."""
        db = SessionLocal()
        try:
            task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not task or not task.is_active:
                return
            
            logger.info(f"Executing backup task: {task.name}")
            
            # Update last run time
            task.last_run = datetime.utcnow()
            
            try:
                # Create backup
                result = create_backup(task.server_name)
                
                # Record backup in database
                backup_record = BackupTask(
                    server_name=task.server_name,
                    backup_file=result["file"],
                    file_size=result["size"],
                    is_auto_created=True
                )
                db.add(backup_record)
                
                logger.info(f"Backup completed for {task.server_name}: {result['file']}")
                
            except Exception as e:
                logger.error(f"Backup task failed for {task.server_name}: {e}")
            
            db.commit()
            
        finally:
            db.close()
    
    async def execute_restart_task(self, task_id: int):
        """Execute a server restart task."""
        db = SessionLocal()
        try:
            task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not task or not task.is_active:
                return
            
            logger.info(f"Executing restart task: {task.name}")
            
            # Update last run time
            task.last_run = datetime.utcnow()
            
            try:
                docker_manager = self.get_docker_manager()
                servers = docker_manager.list_servers()
                
                # Find server by name
                target_server = None
                for server in servers:
                    if server.get("name") == task.server_name:
                        target_server = server
                        break
                
                if target_server:
                    container_id = target_server.get("id")
                    if container_id:
                        # Stop and start server
                        docker_manager.stop_server(container_id)
                        await asyncio.sleep(5)  # Wait for graceful shutdown
                        docker_manager.start_server(container_id)
                        logger.info(f"Restarted server: {task.server_name}")
                    else:
                        logger.error(f"No container ID found for server: {task.server_name}")
                else:
                    logger.error(f"Server not found: {task.server_name}")
                    
            except Exception as e:
                logger.error(f"Restart task failed for {task.server_name}: {e}")
            
            db.commit()
            
        finally:
            db.close()
    
    async def execute_command_task(self, task_id: int):
        """Execute a command task."""
        db = SessionLocal()
        try:
            task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not task or not task.is_active:
                return
            
            logger.info(f"Executing command task: {task.name}")
            
            # Update last run time
            task.last_run = datetime.utcnow()
            
            try:
                docker_manager = self.get_docker_manager()
                servers = docker_manager.list_servers()
                
                # Find server by name
                target_server = None
                for server in servers:
                    if server.get("name") == task.server_name:
                        target_server = server
                        break
                
                if target_server:
                    container_id = target_server.get("id")
                    if container_id and task.command:
                        # Send command to server
                        docker_manager.send_command(container_id, task.command)
                        logger.info(f"Executed command '{task.command}' on {task.server_name}")
                    else:
                        logger.error(f"No container ID or command for server: {task.server_name}")
                else:
                    logger.error(f"Server not found: {task.server_name}")
                    
            except Exception as e:
                logger.error(f"Command task failed for {task.server_name}: {e}")
            
            db.commit()
            
        finally:
            db.close()
    
    async def execute_cleanup_task(self, task_id: int):
        """Execute a cleanup task."""
        db = SessionLocal()
        try:
            task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not task or not task.is_active:
                return
            
            logger.info(f"Executing cleanup task: {task.name}")
            
            # Update last run time
            task.last_run = datetime.utcnow()
            
            try:
                # Clean up old backups based on retention policy
                cutoff_date = datetime.utcnow() - timedelta(days=30)
                old_backups = db.query(BackupTask).filter(
                    BackupTask.is_auto_created == True,
                    BackupTask.created_at < cutoff_date
                ).all()
                
                for backup in old_backups:
                    try:
                        # Delete backup file
                        from pathlib import Path
                        backup_path = Path("backups") / backup.server_name / backup.backup_file
                        if backup_path.exists():
                            backup_path.unlink()
                        
                        # Remove from database
                        db.delete(backup)
                        logger.info(f"Cleaned up old backup: {backup.backup_file}")
                        
                    except Exception as e:
                        logger.error(f"Failed to clean up backup {backup.backup_file}: {e}")
                
                logger.info(f"Cleanup completed, removed {len(old_backups)} old backups")
                
            except Exception as e:
                logger.error(f"Cleanup task failed: {e}")
            
            db.commit()
            
        finally:
            db.close()
    
    def get_next_run_time(self, cron_expression: str) -> datetime:
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
            
            return trigger.get_next_fire_time(None, datetime.utcnow())
            
        except Exception as e:
            logger.error(f"Failed to calculate next run time: {e}")
            return None

# Global scheduler instance
task_scheduler = TaskScheduler()

def get_scheduler() -> TaskScheduler:
    """Get the global scheduler instance."""
    return task_scheduler
