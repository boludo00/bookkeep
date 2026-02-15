# Error Handling Reference

## Contents
- HTTPException Patterns
- Status Code Guide
- Logging with structlog
- Pydantic Validation
- Global Exception Handling
- Anti-Patterns

---

## HTTPException Patterns

### Standard Error Response

```python
from fastapi import HTTPException, status

# 404 Not Found
book = db.query(models.Book).filter(models.Book.id == book_id).first()
if not book:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Book not found"
    )

# 400 Bad Request (client error)
if request.format not in ["ebook", "audiobook"]:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Format must be 'ebook' or 'audiobook'"
    )

# 401 Unauthorized (authentication required)
raise HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"}
)

# 403 Forbidden (authenticated but not permitted)
if not current_user.is_admin:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin privileges required"
    )

# 409 Conflict (duplicate/conflict with current state)
existing = db.query(models.BookRequest).filter(
    models.BookRequest.book_id == book_id,
    models.BookRequest.format == format
).first()
if existing:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Request already exists for this book"
    )

# 503 Service Unavailable (external dependency down)
if not hardcover_token:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Hardcover API not configured"
    )
```

---

## Status Code Guide

| Code | Constant | When to Use |
|------|----------|-------------|
| 200 | `HTTP_200_OK` | Successful GET, PUT, PATCH |
| 201 | `HTTP_201_CREATED` | Successful POST creating resource |
| 204 | `HTTP_204_NO_CONTENT` | Successful DELETE |
| 400 | `HTTP_400_BAD_REQUEST` | Invalid request data |
| 401 | `HTTP_401_UNAUTHORIZED` | Missing/invalid authentication |
| 403 | `HTTP_403_FORBIDDEN` | Authenticated but not permitted |
| 404 | `HTTP_404_NOT_FOUND` | Resource doesn't exist |
| 409 | `HTTP_409_CONFLICT` | Duplicate or state conflict |
| 422 | `HTTP_422_UNPROCESSABLE_ENTITY` | Validation error (auto by Pydantic) |
| 500 | `HTTP_500_INTERNAL_SERVER_ERROR` | Unexpected server error |
| 503 | `HTTP_503_SERVICE_UNAVAILABLE` | External service unavailable |

---

## Logging with structlog

### Logger Setup

```python
# backend/app/routers/auth.py
import structlog

logger = structlog.get_logger(__name__)
```

### Logging Patterns

```python
# Info - successful operations
logger.info("login_success", user_id=user.id, username=user.username)
logger.info("book_created", book_id=book.id, title=book.title)

# Warning - expected failures, potential issues
logger.warning("login_failed_user_not_found", username=request.username)
logger.warning("rate_limit_exceeded", user_id=current_user.id, endpoint="/api/search")

# Error - unexpected failures
logger.error("hardcover_api_error", status_code=response.status_code, error=str(e))
logger.error("database_error", error=str(e), query="get_book")

# Debug - development troubleshooting
logger.debug("cache_hit", key=cache_key)
logger.debug("query_executed", query=str(query), params=params)
```

### Structured Log Fields

```python
# GOOD - Structured key-value pairs
logger.info(
    "request_created",
    request_id=request.id,
    book_id=request.book_id,
    user_id=current_user.id,
    format=request.format,
    status=request.status
)

# BAD - Unstructured string concatenation
logger.info(f"Request {request.id} created by user {current_user.id} for book {request.book_id}")
```

---

## Pydantic Validation

### Schema-Level Validation

```python
# backend/app/schemas.py
from pydantic import BaseModel, EmailStr, field_validator, model_validator

class UserCreate(BaseModel):
    email: EmailStr  # Auto-validates email format
    username: str
    password: str

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters')
        if not v.isalnum():
            raise ValueError('Username must be alphanumeric')
        return v

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v
```

### Cross-Field Validation

```python
class DateRangeRequest(BaseModel):
    start_date: date
    end_date: date

    @model_validator(mode='after')
    def validate_date_range(self):
        if self.end_date < self.start_date:
            raise ValueError('end_date must be after start_date')
        return self
```

### Handling None Values

```python
class UserResponse(BaseModel):
    id: int
    can_request_ebook: bool = True
    can_request_audiobook: bool = True

    @model_validator(mode='before')
    @classmethod
    def handle_none_values(cls, data):
        """Convert None to defaults for boolean fields"""
        if isinstance(data, dict):
            if data.get('can_request_ebook') is None:
                data['can_request_ebook'] = True
            if data.get('can_request_audiobook') is None:
                data['can_request_audiobook'] = True
        return data

    class Config:
        from_attributes = True  # ORM mode
```

---

## Global Exception Handling

### Custom Exception Handler

```python
# backend/main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        error_type=type(exc).__name__
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
```

### Specific Exception Handlers

```python
from sqlalchemy.exc import IntegrityError

@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    logger.warning("database_integrity_error", error=str(exc))
    return JSONResponse(
        status_code=409,
        content={"detail": "Resource already exists or constraint violated"}
    )
```

---

## WARNING: Error Anti-Patterns

### Exposing Internal Errors

**The Problem:**

```python
# BAD - Leaks internal details to client
@router.get("/books/{book_id}")
async def get_book(book_id: int, db: Session = Depends(get_db)):
    try:
        book = db.query(models.Book).filter(models.Book.id == book_id).first()
        return book
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))  # Exposes stack trace!
```

**Why This Breaks:**
1. Reveals database schema, file paths, internal logic
2. Security vulnerability (information disclosure)
3. Confusing for API consumers

**The Fix:**

```python
# GOOD - Log internally, return generic message
@router.get("/books/{book_id}")
async def get_book(book_id: int, db: Session = Depends(get_db)):
    try:
        book = db.query(models.Book).filter(models.Book.id == book_id).first()
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
        return book
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error("get_book_error", book_id=book_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
```

### Silent Error Swallowing

**The Problem:**

```python
# BAD - Errors are silently ignored
async def sync_books():
    for book_id in book_ids:
        try:
            await fetch_book_data(book_id)
        except Exception:
            pass  # Silent failure - impossible to debug
```

**The Fix:**

```python
# GOOD - Log errors, continue processing if appropriate
async def sync_books():
    failed = []
    for book_id in book_ids:
        try:
            await fetch_book_data(book_id)
        except Exception as e:
            logger.error("sync_book_failed", book_id=book_id, error=str(e))
            failed.append(book_id)

    if failed:
        logger.warning("sync_completed_with_errors", failed_count=len(failed))
```

### Wrong Status Code

**The Problem:**

```python
# BAD - Using 500 for client errors
if not book:
    raise HTTPException(status_code=500, detail="Book not found")  # Should be 404!

# BAD - Using 400 for auth failures
if not current_user:
    raise HTTPException(status_code=400, detail="Not logged in")  # Should be 401!
```

**The Fix:**

```python
# GOOD - Correct status codes
if not book:
    raise HTTPException(status_code=404, detail="Book not found")

if not current_user:
    raise HTTPException(status_code=401, detail="Authentication required")
```
