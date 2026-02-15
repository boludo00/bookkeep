# Routes Reference

## Contents
- Router Organization
- CRUD Patterns
- Query Parameters
- Response Models
- Anti-Patterns

---

## Router Organization

Routers are organized by resource in `backend/app/routers/`. Each router:
- Creates an `APIRouter()` instance
- Defines endpoints with decorators
- Gets registered in `main.py` with a prefix

```python
# backend/app/routers/books.py
from fastapi import APIRouter
router = APIRouter()

@router.get("/{book_id}", response_model=schemas.BookResponse)
async def get_book(book_id: int, db: Session = Depends(get_db)):
    ...
```

```python
# backend/main.py - Registration
app.include_router(books.router, prefix="/api/books", tags=["books"])
```

---

## CRUD Patterns

### Create with 201 Status

```python
@router.post("/", response_model=schemas.BookResponse, status_code=status.HTTP_201_CREATED)
def create_book(book: schemas.BookCreate, db: Session = Depends(get_db)):
    db_book = models.Book(**book.model_dump())
    db.add(db_book)
    db.commit()
    db.refresh(db_book)
    return db_book
```

### Read with 404 Handling

```python
@router.get("/{book_id}", response_model=schemas.BookResponse)
async def get_book(book_id: int, db: Session = Depends(get_db)):
    book = db.query(models.Book).filter(models.Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book
```

### Update with Partial Data

```python
@router.put("/{book_id}", response_model=schemas.BookResponse)
async def update_book(
    book_id: int,
    book_update: schemas.BookUpdate,
    db: Session = Depends(get_db)
):
    db_book = db.query(models.Book).filter(models.Book.id == book_id).first()
    if not db_book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Only update provided fields
    update_data = book_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_book, field, value)

    db.commit()
    db.refresh(db_book)
    return db_book
```

### Delete with 204 No Content

```python
@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(
    book_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    db_book = db.query(models.Book).filter(models.Book.id == book_id).first()
    if not db_book:
        raise HTTPException(status_code=404, detail="Book not found")
    db.delete(db_book)
    db.commit()
```

---

## Query Parameters

### Pagination Pattern

```python
@router.get("/", response_model=list[schemas.BookResponse])
async def list_books(
    skip: int = Query(0, ge=0, description="Items to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Max items"),
    db: Session = Depends(get_db)
):
    books = db.query(models.Book).offset(skip).limit(limit).all()
    return books
```

### Filtering Pattern

```python
@router.get("/", response_model=list[schemas.BookRequestResponse])
async def list_requests(
    status: str | None = Query(None, description="Filter by status"),
    format: str | None = Query(None, description="Filter by format"),
    db: Session = Depends(get_db)
):
    query = db.query(models.BookRequest)
    if status:
        query = query.filter(models.BookRequest.status == status)
    if format:
        query = query.filter(models.BookRequest.format == format)
    return query.all()
```

---

## Response Models

### Eager Loading for Nested Responses

```python
from sqlalchemy.orm import joinedload

@router.get("/{request_id}", response_model=schemas.BookRequestResponse)
async def get_request(request_id: int, db: Session = Depends(get_db)):
    # Load book and user relationships for nested response
    request = db.query(models.BookRequest).options(
        joinedload(models.BookRequest.book),
        joinedload(models.BookRequest.user)
    ).filter(models.BookRequest.id == request_id).first()

    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    return request
```

---

## WARNING: Route Anti-Patterns

### Business Logic in Route Handlers

**The Problem:**

```python
# BAD - Business logic mixed with HTTP handling
@router.post("/requests")
async def create_request(request: schemas.BookRequestCreate, db: Session = Depends(get_db)):
    # 50+ lines of validation, permission checks, notifications...
    book = db.query(models.Book).filter(models.Book.id == request.book_id).first()
    if not book:
        raise HTTPException(status_code=404)
    if request.format == "ebook" and book.ebook_available:
        raise HTTPException(status_code=409)
    # ... more and more logic
```

**Why This Breaks:**
1. Untestable without HTTP client
2. Logic cannot be reused by background jobs
3. Route files become massive (requests.py is 35KB)

**The Fix:**

```python
# GOOD - Delegate to service layer
from app.services.requests import RequestService

@router.post("/requests", response_model=schemas.BookRequestResponse)
async def create_request(
    request: schemas.BookRequestCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    service = RequestService(db)
    return service.create_request(request, current_user)
```

### Synchronous Blocking Calls

**The Problem:**

```python
# BAD - Blocks the event loop
@router.get("/external-data")
async def get_data():
    import requests
    response = requests.get("https://api.example.com/data")  # BLOCKING!
    return response.json()
```

**The Fix:**

```python
# GOOD - Use async HTTP client
import httpx

@router.get("/external-data")
async def get_data():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/data")
        return response.json()
```

### Missing Response Model

**The Problem:**

```python
# BAD - Returns raw dict, no validation, no OpenAPI schema
@router.get("/users/{user_id}")
async def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    return {"id": user.id, "email": user.email, "password": user.hashed_password}  # LEAK!
```

**The Fix:**

```python
# GOOD - Schema controls what's exposed
@router.get("/users/{user_id}", response_model=schemas.UserResponse)
async def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    return user  # Pydantic filters to only UserResponse fields
```
