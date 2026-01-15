"""
Simple authentication dependency for getting current user.
For now, uses a header-based user_id, but can be extended with JWT tokens later.
"""
from fastapi import Header, HTTPException, status, Depends
from sqlalchemy.orm import Session
from app import database, models
from typing import Optional
import bcrypt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a bcrypt hash."""
    try:
        # Convert to bytes
        password_bytes = plain_password.encode('utf-8')
        
        # Handle potential encoding issues with stored hash
        if isinstance(hashed_password, str):
            hashed_bytes = hashed_password.encode('utf-8')
        else:
            hashed_bytes = hashed_password
        
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False

# Temporary: For development, we'll use a simple header-based approach
# In production, this should use JWT tokens or session-based auth

async def get_current_user(
    x_user_id: Optional[int] = Header(None, alias="X-User-Id"),
    db: Session = Depends(database.get_db)
) -> models.User:
    """
    Get current user from X-User-Id header.
    Defaults to user_id=1 if not provided (for development).
    """
    user_id = x_user_id if x_user_id is not None else 1
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    return user

async def get_current_user_optional(
    x_user_id: Optional[int] = Header(None, alias="X-User-Id"),
    db: Session = Depends(database.get_db)
) -> Optional[models.User]:
    """Get current user optionally (returns None if not provided)"""
    if x_user_id is None:
        return None
    
    user = db.query(models.User).filter(models.User.id == x_user_id).first()
    if user and not user.is_active:
        return None
    return user

def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Require admin privileges"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user

