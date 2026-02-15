# Python Types Reference

## Contents
- Schema Inheritance Pattern
- ORM to Pydantic Mapping
- Optional vs Required Fields
- Model Validators
- Function Signatures

---

## Schema Inheritance Pattern

Use a three-layer pattern for CRUD operations:

```python
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

# 1. Base - shared fields
class UserBase(BaseModel):
    email: EmailStr
    username: str
    full_name: Optional[str] = None

# 2. Create - adds required creation fields
class UserCreate(UserBase):
    password: str
    is_admin: Optional[bool] = False

# 3. Response - adds ID, timestamps, computed fields
class UserResponse(UserBase):
    id: int
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True  # Enable ORM mode

# 4. Update - all fields optional
class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    is_active: Optional[bool] = None
```

---

## ORM to Pydantic Mapping

### SQLAlchemy Model

```python
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

class Book(Base):
    __tablename__ = "books"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    hardcover_id = Column(Integer, unique=True, index=True)
    genres = Column(String)  # Comma-separated string in DB
    ebook_available = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    requests = relationship("BookRequest", back_populates="book")
```

### Corresponding Pydantic Schema

```python
class BookResponse(BaseModel):
    id: int
    title: str
    hardcover_id: Optional[int] = None
    genres: List[str] = []  # Transformed from comma-separated
    ebook_available: bool = False
    created_at: datetime
    requests: List["BookRequestResponse"] = []  # Nested relationship

    class Config:
        from_attributes = True
```

### Manual Transformation for Complex Fields

```python
# Router converts comma-separated genres to list
def get_book(book_id: int, db: Session = Depends(get_db)):
    db_book = db.query(models.Book).filter(models.Book.id == book_id).first()
    response_dict = {
        **{k: v for k, v in db_book.__dict__.items() if not k.startswith('_')},
        "genres": [g.strip() for g in db_book.genres.split(',')] if db_book.genres else []
    }
    return schemas.BookResponse(**response_dict)
```

---

## Optional vs Required Fields

| Pattern | When to Use |
|---------|-------------|
| `field: str` | Required, no default |
| `field: str = "default"` | Required with default |
| `field: Optional[str] = None` | Optional, nullable |
| `field: List[str] = []` | Optional list (can be empty) |

```python
class BookRequestCreate(BaseModel):
    book_id: int                           # Required
    format: str                            # Required: "ebook" or "audiobook"
    notes: Optional[str] = None            # Optional user notes
    source: str = "user_request"           # Default value
```

---

## Model Validators

### Normalize None to Defaults

```python
from pydantic import model_validator

class UserResponse(BaseModel):
    can_request_ebook: Optional[bool] = True
    can_download: Optional[bool] = True

    @model_validator(mode='before')
    @classmethod
    def handle_none_values(cls, data):
        """Convert None values to defaults for boolean fields."""
        if isinstance(data, dict):
            if data.get('can_request_ebook') is None:
                data['can_request_ebook'] = True
            if data.get('can_download') is None:
                data['can_download'] = True
        return data

    class Config:
        from_attributes = True
```

---

## Function Type Signatures

### Async Endpoint with Dependencies

```python
async def create_request(
    request: schemas.BookRequestCreate,           # Request body
    db: Session = Depends(database.get_db),       # Injected session
    current_user: models.User = Depends(get_current_user)  # Auth
) -> schemas.BookRequestResponse:
    ...
```

### Optional Return Type

```python
def decode_token(token: str) -> Optional[TokenData]:
    """Returns None on invalid token instead of raising."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenData(user_id=int(payload["sub"]), username=payload["username"])
    except (JWTError, ValueError):
        return None
```

### Tuple Returns

```python
def get_hardcover_token(db: Session) -> tuple[str, str]:
    """Returns (token, source) where source is 'env', 'ui', or 'none'."""
    env_token = os.getenv("HARDCOVER_API_TOKEN", "")
    if env_token:
        return (env_token, "env")
    setting = db.query(AppSettings).filter(AppSettings.key == "hardcover_api_token").first()
    return (setting.value, "ui") if setting else ("", "none")
```

---

## JWT Token Types

```python
class TokenData(BaseModel):
    """Data encoded in JWT."""
    user_id: int
    username: str
    is_admin: bool
    token_type: str = "access"  # "access" or "refresh"

class TokenResponse(BaseModel):
    """API response with tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # Seconds until access token expires