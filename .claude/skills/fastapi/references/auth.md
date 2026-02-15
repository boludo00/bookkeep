# Authentication Reference

## Contents
- JWT Token Flow
- Authentication Dependencies
- Permission Checks
- Token Creation
- Anti-Patterns

---

## JWT Token Flow

Bookkeep uses JWT tokens for stateless authentication:
1. User logs in with username/password
2. Server returns access token (30min) + refresh token (7 days)
3. Client includes access token in `Authorization: Bearer <token>` header
4. When access token expires, client uses refresh token to get new access token

### Token Configuration

```python
# backend/app/jwt.py
import os
from datetime import timedelta

SECRET_KEY = os.getenv("BOOKKEEP_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("BOOKKEEP_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("BOOKKEEP_REFRESH_TOKEN_EXPIRE_DAYS", "7"))
```

---

## Authentication Dependencies

### Get Current User (Required)

```python
# backend/app/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db)
) -> models.User:
    """Requires valid token. Returns 401 if invalid/missing."""
    if credentials is None:
        raise credentials_exception

    token_data = verify_access_token(credentials.credentials)
    if token_data is None:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == token_data.user_id).first()
    if not user or not user.is_active:
        raise credentials_exception

    return user
```

### Get Current User (Optional)

```python
async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db)
) -> models.User | None:
    """Returns user if authenticated, None otherwise. Never raises 401."""
    if credentials is None:
        return None

    token_data = verify_access_token(credentials.credentials)
    if token_data is None:
        return None

    user = db.query(models.User).filter(models.User.id == token_data.user_id).first()
    if not user or not user.is_active:
        return None

    return user
```

### Require Admin

```python
def require_admin(
    current_user: models.User = Depends(get_current_user)
) -> models.User:
    """Requires admin privileges. Returns 403 if not admin."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user
```

---

## Permission Checks

### Route-Level Permissions

```python
# Admin-only endpoint
@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    ...

# Authenticated endpoint
@router.post("/requests")
async def create_request(
    request: schemas.RequestCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    ...

# Public endpoint (no auth required)
@router.get("/books/{book_id}")
async def get_book(book_id: int, db: Session = Depends(get_db)):
    ...
```

### In-Route Permission Checks

```python
@router.post("/requests")
async def create_request(
    request: schemas.BookRequestCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Check format-specific permissions
    if request.format == "ebook" and not current_user.can_request_ebook:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to request ebooks"
        )

    if request.format == "audiobook" and not current_user.can_request_audiobook:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to request audiobooks"
        )

    # Check ownership for actions
    existing = db.query(models.BookRequest).filter(
        models.BookRequest.id == request_id
    ).first()

    if existing.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this request"
        )
```

---

## Token Creation

### Login Endpoint

```python
# backend/app/routers/auth.py
from app.jwt import create_tokens, verify_password

@router.post("/login", response_model=schemas.TokenResponse)
def login(request: schemas.LoginRequest, db: Session = Depends(get_db)):
    # Find user
    user = db.query(models.User).filter(
        models.User.username == request.username
    ).first()

    if not user:
        logger.warning("login_failed_user_not_found", username=request.username)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Verify password
    if not verify_password(request.password, user.hashed_password):
        logger.warning("login_failed_invalid_password", username=request.username)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Check active status
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")

    logger.info("login_success", user_id=user.id, username=user.username)

    return create_tokens(
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin
    )
```

### Token Refresh

```python
@router.post("/refresh", response_model=schemas.AccessTokenResponse)
def refresh_token(request: schemas.RefreshRequest, db: Session = Depends(get_db)):
    token_data = verify_refresh_token(request.refresh_token)

    if token_data is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Verify user still exists and is active
    user = db.query(models.User).filter(models.User.id == token_data.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Create new access token only
    access_token = create_access_token(
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin
    )

    return schemas.AccessTokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
```

---

## WARNING: Auth Anti-Patterns

### Exposing Sensitive Data in Tokens

**The Problem:**

```python
# BAD - Password hash in token payload
def create_access_token(user: models.User):
    to_encode = {
        "user_id": user.id,
        "password_hash": user.hashed_password,  # NEVER DO THIS
        "email": user.email
    }
    return jwt.encode(to_encode, SECRET_KEY, ALGORITHM)
```

**Why This Breaks:**
1. JWT payloads are base64-encoded, not encrypted
2. Anyone can decode and read the contents
3. Password hashes could be brute-forced

**The Fix:**

```python
# GOOD - Only include identifiers
def create_access_token(user_id: int, username: str, is_admin: bool):
    to_encode = {
        "sub": str(user_id),  # Standard claim for subject
        "username": username,
        "is_admin": is_admin,
        "token_type": "access",
        "exp": expire_time
    }
    return jwt.encode(to_encode, SECRET_KEY, ALGORITHM)
```

### Trusting Token Data Without DB Check

**The Problem:**

```python
# BAD - Token says admin, but user might be demoted
async def get_current_user(credentials):
    token_data = decode_token(credentials.credentials)
    # Trusting is_admin from token without checking DB
    return FakeUser(id=token_data.user_id, is_admin=token_data.is_admin)
```

**The Fix:**

```python
# GOOD - Always verify current state from database
async def get_current_user(credentials, db):
    token_data = verify_access_token(credentials.credentials)
    user = db.query(models.User).filter(models.User.id == token_data.user_id).first()

    if not user or not user.is_active:  # Check CURRENT state
        raise credentials_exception

    return user  # Fresh data from DB
```

### Hardcoded Secret Key

**The Problem:**

```python
# BAD - Secret in code
SECRET_KEY = "my-super-secret-key-12345"
```

**The Fix:**

```python
# GOOD - Environment variable with random fallback for dev
import secrets
SECRET_KEY = os.getenv("BOOKKEEP_SECRET_KEY", secrets.token_urlsafe(32))

# WARNING: Random fallback means sessions lost on restart
# Always set BOOKKEEP_SECRET_KEY in production
```
