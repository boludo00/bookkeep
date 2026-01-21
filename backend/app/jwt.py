"""JWT token utilities for authentication."""
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from pydantic import BaseModel


# JWT Configuration
# In production, set BOOKKEEP_SECRET_KEY environment variable
# If not set, a random key is generated (tokens won't persist across restarts)
def get_secret_key() -> str:
    """Get or generate the JWT secret key."""
    key = os.getenv("BOOKKEEP_SECRET_KEY")
    if key:
        return key
    # Generate a random key if not configured (development only)
    # This means tokens won't survive server restarts
    return secrets.token_urlsafe(32)


SECRET_KEY = get_secret_key()
ALGORITHM = "HS256"

# Token expiration times
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("BOOKKEEP_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("BOOKKEEP_REFRESH_TOKEN_EXPIRE_DAYS", "7"))


class TokenData(BaseModel):
    """Data encoded in the JWT token."""
    user_id: int
    username: str
    is_admin: bool
    token_type: str = "access"  # "access" or "refresh"


class TokenResponse(BaseModel):
    """Response containing JWT tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires


def create_access_token(user_id: int, username: str, is_admin: bool) -> str:
    """Create a new access token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": str(user_id),
        "username": username,
        "is_admin": is_admin,
        "token_type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: int, username: str, is_admin: bool) -> str:
    """Create a new refresh token."""
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "sub": str(user_id),
        "username": username,
        "is_admin": is_admin,
        "token_type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_tokens(user_id: int, username: str, is_admin: bool) -> TokenResponse:
    """Create both access and refresh tokens."""
    access_token = create_access_token(user_id, username, is_admin)
    refresh_token = create_refresh_token(user_id, username, is_admin)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def decode_token(token: str) -> Optional[TokenData]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        username = payload.get("username")
        is_admin = payload.get("is_admin", False)
        token_type = payload.get("token_type", "access")

        if user_id is None or username is None:
            return None

        return TokenData(
            user_id=user_id,
            username=username,
            is_admin=is_admin,
            token_type=token_type,
        )
    except (JWTError, ValueError, TypeError):
        return None


def verify_access_token(token: str) -> Optional[TokenData]:
    """Verify an access token and return its data."""
    token_data = decode_token(token)
    if token_data is None:
        return None
    if token_data.token_type != "access":
        return None
    return token_data


def verify_refresh_token(token: str) -> Optional[TokenData]:
    """Verify a refresh token and return its data."""
    token_data = decode_token(token)
    if token_data is None:
        return None
    if token_data.token_type != "refresh":
        return None
    return token_data
