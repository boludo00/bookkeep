"""Authentication router."""
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import User
from app.auth import verify_password

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user_id: int
    username: str
    is_admin: bool
    message: str = "Login successful"


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user and return user info."""
    # Find user by username
    user = db.query(User).filter(User.username == request.username).first()
    
    if not user:
        logger.warning("login_failed_user_not_found", username=request.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Verify password
    if not verify_password(request.password, user.hashed_password):
        logger.warning("login_failed_invalid_password", username=request.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    logger.info("login_success", user_id=user.id, username=user.username, is_admin=user.is_admin)
    
    return LoginResponse(
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin
    )

