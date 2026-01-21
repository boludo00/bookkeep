"""
JWT-based authentication for Book Hound.
"""
from fastapi import Header, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app import database, models
from app.jwt import verify_access_token, TokenData
from typing import Optional
import bcrypt


# HTTP Bearer scheme for JWT tokens
security = HTTPBearer(auto_error=False)


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


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(database.get_db)
) -> models.User:
    """
    Get current user from JWT Bearer token.
    Raises 401 if token is missing or invalid.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise credentials_exception

    token = credentials.credentials
    token_data = verify_access_token(token)

    if token_data is None:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == token_data.user_id).first()
    if not user:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(database.get_db)
) -> Optional[models.User]:
    """Get current user optionally (returns None if no valid token)."""
    if credentials is None:
        return None

    token = credentials.credentials
    token_data = verify_access_token(token)

    if token_data is None:
        return None

    user = db.query(models.User).filter(models.User.id == token_data.user_id).first()
    if user and not user.is_active:
        return None
    return user


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Require admin privileges."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user
