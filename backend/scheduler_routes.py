from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database import get_db
from models import ScheduledTask, User
from auth import require_auth, require_moderator
from scheduler import get_scheduler

router = APIRouter(prefix="/schedule", tags=["scheduling"])

# Pydantic models
class ScheduledTaskCreate(BaseModel):
    name: str
    task_type: str  # backup, restart, command, cleanup
    server_name: Optional[str] = None  # null for global tasks
    cron_expression: str  # e.g., "0 2 * * *" for daily at 2 AM
    command: Optional[str] = None  # for command tasks

class ScheduledTaskUpdate(BaseModel):
    name: Optional[str] = None
    cron_expression: Optional[str] = None
    command: Optional[str] = None
    is_active: Optional[bool] = None

class ScheduledTaskResponse(BaseModel):
    id: int
    name: str
    task_type: str
    server_name: Optional[str]
    cron_expression: str
    command: Optional[str]
    is_active: bool
    created_at: datetime
    last_run: Optional[datetime]
    next_run: Optional[datetime]
    
    class Config:
        from_attributes = True

@router.get("/tasks", response_model=List[ScheduledTaskResponse])
async def list_scheduled_tasks(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """List all scheduled tasks."""
    tasks = db.query(ScheduledTask).all()
    
    # Calculate next run times
    scheduler = get_scheduler()
    for task in tasks:
        if task.is_active:
            task.next_run = scheduler.get_next_run_time(task.cron_expression)
    
    return tasks

@router.post("/tasks", response_model=ScheduledTaskResponse)
async def create_scheduled_task(
    task_data: ScheduledTaskCreate,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Create a new scheduled task."""
    # Validate task type
    valid_types = ["backup", "restart", "command", "cleanup"]
    if task_data.task_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid task type. Must be one of: {valid_types}"
        )
    
    # Validate cron expression
    scheduler = get_scheduler()
    try:
        next_run = scheduler.get_next_run_time(task_data.cron_expression)
        if next_run is None:
            raise ValueError("Invalid cron expression")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid cron expression: {str(e)}"
        )
    
    # Validate required fields for specific task types
    if task_data.task_type in ["backup", "restart"] and not task_data.server_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"server_name is required for {task_data.task_type} tasks"
        )
    
    if task_data.task_type == "command" and not task_data.command:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="command is required for command tasks"
        )
    
    # Create task
    task = ScheduledTask(
        name=task_data.name,
        task_type=task_data.task_type,
        server_name=task_data.server_name,
        cron_expression=task_data.cron_expression,
        command=task_data.command,
        created_by=current_user.id,
        is_active=True
    )
    
    db.add(task)
    db.commit()
    db.refresh(task)
    
    # Add to scheduler
    try:
        scheduler.add_scheduled_task(task)
        task.next_run = scheduler.get_next_run_time(task.cron_expression)
    except Exception as e:
        # Rollback if scheduler fails
        db.delete(task)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to schedule task: {str(e)}"
        )
    
    return task

@router.get("/tasks/{task_id}", response_model=ScheduledTaskResponse)
async def get_scheduled_task(
    task_id: int,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get a specific scheduled task."""
    task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # Calculate next run time
    if task.is_active:
        scheduler = get_scheduler()
        task.next_run = scheduler.get_next_run_time(task.cron_expression)
    
    return task

@router.put("/tasks/{task_id}", response_model=ScheduledTaskResponse)
async def update_scheduled_task(
    task_id: int,
    task_data: ScheduledTaskUpdate,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Update a scheduled task."""
    task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # Update fields
    if task_data.name is not None:
        task.name = task_data.name
    
    if task_data.command is not None:
        task.command = task_data.command
    
    if task_data.is_active is not None:
        task.is_active = task_data.is_active
    
    # Handle cron expression change
    if task_data.cron_expression is not None:
        scheduler = get_scheduler()
        try:
            next_run = scheduler.get_next_run_time(task_data.cron_expression)
            if next_run is None:
                raise ValueError("Invalid cron expression")
            task.cron_expression = task_data.cron_expression
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid cron expression: {str(e)}"
            )
    
    db.commit()
    db.refresh(task)
    
    # Update scheduler
    scheduler = get_scheduler()
    if task.is_active:
        scheduler.add_scheduled_task(task)
        task.next_run = scheduler.get_next_run_time(task.cron_expression)
    else:
        scheduler.remove_scheduled_task(task.id)
    
    return task

@router.delete("/tasks/{task_id}")
async def delete_scheduled_task(
    task_id: int,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Delete a scheduled task."""
    task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # Remove from scheduler
    scheduler = get_scheduler()
    scheduler.remove_scheduled_task(task.id)
    
    # Delete from database
    db.delete(task)
    db.commit()
    
    return {"message": "Task deleted successfully"}

@router.post("/tasks/{task_id}/run")
async def run_task_now(
    task_id: int,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Manually execute a scheduled task now."""
    task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # Execute task based on type
    scheduler = get_scheduler()
    try:
        if task.task_type == "backup":
            await scheduler.execute_backup_task(task.id)
        elif task.task_type == "restart":
            await scheduler.execute_restart_task(task.id)
        elif task.task_type == "command":
            await scheduler.execute_command_task(task.id)
        elif task.task_type == "cleanup":
            await scheduler.execute_cleanup_task(task.id)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown task type: {task.task_type}"
            )
        
        return {"message": f"Task '{task.name}' executed successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Task execution failed: {str(e)}"
        )