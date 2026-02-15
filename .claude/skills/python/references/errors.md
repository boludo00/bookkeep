# Python Errors Reference

## Contents
- HTTPException Patterns
- Exception Handling Strategies
- Structured Logging
- Race Condition Handling
- Silent Failures

---

## HTTPException Patterns

### Status Code Reference

| Code | Constant | When to Use |
|------|----------|-------------|
| 400 | `HTTP_400_BAD_REQUEST` | Validation errors, malformed input |
| 401 | `HTTP_401_UNAUTHORIZED` | Missing or invalid credentials |
| 403 | `HTTP_403_FORBIDDEN` | Valid credentials, insufficient permissions |
| 404 | `HTTP_404_NOT_FOUND` | Resource doesn't exist |
| 409 | `HTTP_409_CONFLICT` | Duplicate resource, business rule violation |
| 429 | `HTTP_429_TOO_MANY_REQUESTS` | Rate limiting |

### Common Patterns

```python
from fastapi import HTTPException, status

# 404 - Resource not found
db_book = db.query(models.Book).filter(models.Book.id == book_id).first()
if not db_book:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Book not found"
    )

# 401 - Authentication (always use same message)
if not user or not verify_password(password, user.hashed_password):
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or password"  # Never reveal which is wrong
    )

# 403 - Authorization
if not current_user.is_admin:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin privileges required"
    )

# 409 - Business rule conflict
if book.ebook_available:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Ebook is already available"
    )

# 400 - Validation
if len(password) < 8:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Password must be at least 8 characters"
    )
```

---

## Exception Handling Strategies

### Re-raise HTTP Exceptions

```python
# GOOD - Don't swallow HTTPExceptions
try:
    result = await external_api_call()
except HTTPException:
    raise  # Re-raise to preserve status code
except Exception as e:
    logger.error("api_call_failed", error=str(e))
    raise HTTPException(status_code=500, detail="External service error")
```

### WARNING: Bare Except Clauses

**The Problem:**

```python
# BAD - Catches everything including KeyboardInterrupt, SystemExit
try:
    result = process_data()
except:
    return None
```

**Why This Breaks:**
1. Catches `KeyboardInterrupt`, preventing Ctrl+C
2. Catches `SystemExit`, preventing clean shutdown
3. Hides bugs by silently swallowing all errors
4. Makes debugging impossible

**The Fix:**

```python
# GOOD - Catch specific exceptions
try:
    result = process_data()
except (ValueError, TypeError) as e:
    logger.warning("process_failed", error=str(e))
    return None
except Exception as e:  # If you must catch broadly
    logger.error("unexpected_error", error=str(e), exc_info=True)
    raise
```

---

## Structured Logging with structlog

```python
import structlog
logger = structlog.get_logger()

# Info - Significant operations
logger.info("book_created", book_id=book.id, title=book.title, user_id=user.id)

# Warning - Expected failures (external services, user errors)
logger.warning("readarr_check_failed", server_id=server.id, error=str(e))
logger.warning("login_failed_user_not_found", username=request.username)

# Error - Unexpected failures (bugs, system errors)
logger.error("download_orchestration_failed", book_id=book.id, error=str(e), exc_info=True)

# Debug - Detailed tracing (disabled in production)
logger.debug("cache_hit", key=cache_key)
```

### Always Include Context

```python
# GOOD - Include relevant IDs and state
logger.info("request_approved",
    request_id=request.id,
    book_id=request.book_id,
    user_id=request.user_id,
    format=request.format,
    approved_by=admin.id
)

# BAD - Missing context
logger.info("request approved")  # Which request? By whom?
```

---

## Race Condition Handling

### IntegrityError for Duplicate Prevention

```python
from sqlalchemy.exc import IntegrityError

try:
    db_book = models.Book(**book_dict)
    db.add(db_book)
    db.flush()  # Catch constraint violations early
    db.commit()
    db.refresh(db_book)
except IntegrityError:
    db.rollback()
    # Race condition: book inserted between our check and insert
    existing = db.query(models.Book).filter(
        models.Book.hardcover_id == book_dict["hardcover_id"]
    ).first()
    if existing:
        # Update existing instead
        for key, value in book_dict.items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing
    raise HTTPException(status_code=400, detail="Duplicate constraint violation")
```

---

## Silent Failure Patterns

Use silent failures ONLY for non-critical operations:

### Safe JWT Decoding

```python
def decode_token(token: str) -> Optional[TokenData]:
    """Returns None on invalid token instead of raising."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        username = payload.get("username")
        if user_id is None or username is None:
            return None
        return TokenData(user_id=user_id, username=username)
    except (JWTError, ValueError, TypeError):
        return None  # Caller checks for None
```

### Safe Password Verification

```python
def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False  # Never reveal why verification failed
```

### Safe JSON Parsing

```python
def get_downloaded_hashes(book: models.Book) -> list[str]:
    try:
        return json.loads(book.downloaded_release_hashes) if book.downloaded_release_hashes else []
    except (json.JSONDecodeError, TypeError):
        return []  # Default to empty list on parse error
```

---

## Graceful Degradation Pattern

```python
async def check_all_sources(book: models.Book, db: Session) -> dict:
    """Check multiple sources, continue on individual failures."""
    results = {"available": False, "sources_checked": [], "sources_failed": []}
    
    for server in db.query(models.ReadarrServer).all():
        try:
            client = ReadarrClient.from_server(server)
            async with client.session(timeout=10.0) as session:
                if await client.book_exists(session, book.hardcover_id):
                    results["available"] = True
                results["sources_checked"].append(server.name)
        except Exception as e:
            logger.warning("source_check_failed", 
                server_id=server.id, 
                book_id=book.id, 
                error=str(e)
            )
            results["sources_failed"].append(server.name)
            # Continue to next server instead of failing entirely
    
    return results