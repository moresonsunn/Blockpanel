from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, validator
import re

# Custom email validation that allows localhost domains for development
def validate_email(email: str) -> str:
    """Custom email validator that allows localhost domains."""
    # Basic email format validation
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    localhost_pattern = r'^[a-zA-Z0-9._%+-]+@localhost$'
    
    if re.match(email_pattern, email) or re.match(localhost_pattern, email):
        return email
    else:
        raise ValueError('Invalid email format')
from typing import List, Optional
from datetime import datetime

from database import get_db
from models import User
from auth import require_auth, require_admin, require_user_view, require_user_create, require_user_edit, require_moderator, get_password_hash

router = APIRouter(prefix="/users", tags=["user_management"])

class UserStats(BaseModel):
    total_users: int
    active_users: int
    admin_users: int
    moderator_users: int
    recent_logins: int  # Users who logged in within last 24 hours

class UserActivity(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True

class UserCreateRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = "user"
    
    @validator('email')
    def validate_email_field(cls, v):
        return validate_email(v)

class UserUpdateRequest(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    
    @validator('email')
    def validate_email_field(cls, v):
        if v is not None:
            return validate_email(v)
        return v

class PasswordResetRequest(BaseModel):
    new_password: str

@router.get("/stats", response_model=UserStats)
async def get_user_stats(
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Get user statistics (moderator+ only)."""
    from datetime import timedelta
    
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    admin_users = db.query(User).filter(User.role == "admin").count()
    moderator_users = db.query(User).filter(User.role == "moderator").count()
    
    # Users who logged in within last 24 hours
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent_logins = db.query(User).filter(
        User.last_login >= yesterday,
        User.is_active == True
    ).count()
    
    return UserStats(
        total_users=total_users,
        active_users=active_users,
        admin_users=admin_users,
        moderator_users=moderator_users,
        recent_logins=recent_logins
    )

@router.get("/activity", response_model=List[UserActivity])
async def get_user_activity(
    limit: int = 50,
    current_user: User = Depends(require_moderator),
    db: Session = Depends(get_db)
):
    """Get recent user activity (moderator+ only)."""
    users = db.query(User).order_by(
        User.last_login.desc().nullslast(),
        User.created_at.desc()
    ).limit(limit).all()
    
    return users

@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    request: PasswordResetRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Reset a user's password (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Hash the new password
    user.hashed_password = get_password_hash(request.new_password)
    db.commit()
    
    return {"message": f"Password reset for user {user.username}"}

@router.post("/{user_id}/toggle-status")
async def toggle_user_status(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Toggle user active/inactive status (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Prevent self-deactivation
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )
    
    user.is_active = not user.is_active
    db.commit()
    
    status_text = "activated" if user.is_active else "deactivated"
    return {"message": f"User {user.username} has been {status_text}"}


@router.get("/sessions")
async def get_active_sessions(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get information about active user sessions (admin only)."""
    from datetime import timedelta
    
    # Users with recent activity (last 30 minutes)
    recent_activity = datetime.utcnow() - timedelta(minutes=30)
    
    # This is a simplified version - in a real app you'd track sessions properly
    active_users = db.query(User).filter(
        User.last_login >= recent_activity,
        User.is_active == True
    ).all()
    
    sessions = []
    for user in active_users:
        sessions.append({
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
            "last_login": user.last_login,
            "is_current_user": user.id == current_user.id
        })
    
    return {"active_sessions": sessions}

@router.post("/bulk-action")
async def bulk_user_action(
    action: str,
    user_ids: List[int],
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Perform bulk actions on multiple users (admin only)."""
    if action not in ["activate", "deactivate", "delete"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid action. Must be 'activate', 'deactivate', or 'delete'"
        )
    
    # Get users
    users = db.query(User).filter(User.id.in_(user_ids)).all()
    
    if not users:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No users found with provided IDs"
        )
    
    # Prevent self-action
    if current_user.id in user_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot perform bulk actions on your own account"
        )
    
    results = []
    for user in users:
        try:
            if action == "activate":
                user.is_active = True
                results.append(f"Activated {user.username}")
            elif action == "deactivate":
                user.is_active = False
                results.append(f"Deactivated {user.username}")
            elif action == "delete":
                db.delete(user)
                results.append(f"Deleted {user.username}")
        except Exception as e:
            results.append(f"Failed to {action} {user.username}: {str(e)}")
    
    db.commit()
    
    return {"results": results}
