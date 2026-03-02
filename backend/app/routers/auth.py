"""Authentication router with JWT token support."""
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import User
from app.auth import verify_password
from app.jwt import (
    create_tokens,
    verify_refresh_token,
    create_access_token,
    TokenResponse,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user and return JWT tokens."""
    # Find user by username
    user = db.query(User).filter(User.username == request.username).first()

    if not user:
        logger.warning("login_failed_user_not_found", username=request.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    if not user.hashed_password:
        logger.warning("login_failed_oidc_only_user", username=request.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account uses SSO. Please sign in with the SSO button."
        )

    if not verify_password(request.password, user.hashed_password):
        logger.warning("login_failed_invalid_password", username=request.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    # Check if user is active
    if not user.is_active:
        logger.warning("login_failed_inactive_user", username=request.username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    logger.info("login_success", user_id=user.id, username=user.username, is_admin=user.is_admin)

    # Create and return JWT tokens
    return create_tokens(
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin,
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh_token(request: RefreshRequest, db: Session = Depends(get_db)):
    """Get a new access token using a refresh token."""
    token_data = verify_refresh_token(request.refresh_token)

    if token_data is None:
        logger.warning("refresh_failed_invalid_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    # Verify user still exists and is active
    user = db.query(User).filter(User.id == token_data.user_id).first()

    if not user:
        logger.warning("refresh_failed_user_not_found", user_id=token_data.user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    if not user.is_active:
        logger.warning("refresh_failed_inactive_user", user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    logger.info("token_refreshed", user_id=user.id, username=user.username)

    # Create new access token with current user state
    access_token = create_access_token(
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin,
    )

    return AccessTokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
