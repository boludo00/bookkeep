# Database Reference

## Contents
- Session Management
- Query Patterns
- Transactions
- Connection Pooling
- N+1 Prevention
- Anti-Patterns

---

## Session Management

See the **sqlalchemy** skill for ORM patterns and the **postgresql** skill for database setup.

### Dependency Injection Pattern

```python
# backend/app/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """FastAPI dependency for database sessions"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### Usage in Routes

```python
from app.database import get_db

@router.get("/books")
async def list_books(db: Session = Depends(get_db)):
    return db.query(models.Book).all()
```

### Manual Session (Background Tasks)

```python
# For background jobs that don't use FastAPI dependencies
async def background_task():
    db = SessionLocal()
    try:
        # Do work
        books = db.query(models.Book).filter(...).all()
        db.commit()
    finally:
        db.close()  # ALWAYS close
```

---

## Query Patterns

### Basic CRUD Operations

```python
# Create
def create_book(db: Session, book: schemas.BookCreate) -> models.Book:
    db_book = models.Book(**book.model_dump())
    db.add(db_book)
    db.commit()
    db.refresh(db_book)  # Reload to get generated fields
    return db_book

# Read one
def get_book(db: Session, book_id: int) -> models.Book | None:
    return db.query(models.Book).filter(models.Book.id == book_id).first()

# Read many with pagination
def get_books(db: Session, skip: int = 0, limit: int = 100) -> list[models.Book]:
    return db.query(models.Book).offset(skip).limit(limit).all()

# Update
def update_book(db: Session, book_id: int, data: schemas.BookUpdate) -> models.Book:
    db_book = db.query(models.Book).filter(models.Book.id == book_id).first()
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(db_book, field, value)
    db.commit()
    db.refresh(db_book)
    return db_book

# Delete
def delete_book(db: Session, book_id: int) -> None:
    db_book = db.query(models.Book).filter(models.Book.id == book_id).first()
    db.delete(db_book)
    db.commit()
```

### Filtering Patterns

```python
# Multiple conditions
books = db.query(models.Book).filter(
    models.Book.ebook_available == True,
    models.Book.rating >= 4.0
).all()

# OR conditions
from sqlalchemy import or_
books = db.query(models.Book).filter(
    or_(
        models.Book.ebook_available == True,
        models.Book.audiobook_available == True
    )
).all()

# IN clause
book_ids = [1, 2, 3, 4, 5]
books = db.query(models.Book).filter(models.Book.id.in_(book_ids)).all()

# LIKE pattern
books = db.query(models.Book).filter(
    models.Book.title.ilike(f"%{search_term}%")
).all()
```

---

## Transactions

### Implicit Transaction (Default)

```python
@router.post("/requests")
async def create_request(request: schemas.RequestCreate, db: Session = Depends(get_db)):
    # Everything between db operations and commit is a transaction
    book_request = models.BookRequest(**request.model_dump())
    db.add(book_request)

    # Update book status
    book = db.query(models.Book).filter(models.Book.id == request.book_id).first()
    book.has_pending_request = True

    db.commit()  # Both changes committed together
    return book_request
```

### Explicit Rollback on Error

```python
async def complex_operation(db: Session):
    try:
        # Multiple database operations
        task1 = models.Task(name="task1")
        db.add(task1)
        db.flush()  # Get ID without committing

        task2 = models.Task(name="task2", parent_id=task1.id)
        db.add(task2)

        # External call that might fail
        await external_api_call()

        db.commit()
    except Exception:
        db.rollback()
        raise
```

---

## Connection Pooling

### PostgreSQL Configuration

```python
# backend/app/database.py
engine = create_engine(
    DATABASE_URL,
    pool_size=10,              # Connections kept open
    max_overflow=20,           # Extra connections under load
    pool_timeout=30,           # Wait time for connection
    pool_recycle=1800,         # Recycle connections after 30min
    pool_pre_ping=True,        # Test connections before use
)
```

### SQLite Configuration (Development)

```python
# SQLite needs special handling for threads
engine = create_engine(
    "sqlite:///./data/bookkeep.db",
    connect_args={
        "check_same_thread": False,  # Allow multi-thread access
        "timeout": 30,               # Lock timeout
    }
)

# Enable WAL mode for better concurrency
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()
```

---

## N+1 Prevention

### The Problem

```python
# BAD - N+1 queries: 1 for requests + N for each book
@router.get("/requests")
async def list_requests(db: Session = Depends(get_db)):
    requests = db.query(models.BookRequest).all()
    # Each request.book triggers a separate query!
    return [{"id": r.id, "book_title": r.book.title} for r in requests]
```

### The Fix: Eager Loading

```python
from sqlalchemy.orm import joinedload

# GOOD - Single query with JOIN
@router.get("/requests", response_model=list[schemas.BookRequestResponse])
async def list_requests(db: Session = Depends(get_db)):
    requests = db.query(models.BookRequest).options(
        joinedload(models.BookRequest.book),
        joinedload(models.BookRequest.user)
    ).all()
    return requests
```

### Selective Loading

```python
# Only load specific relationships
from sqlalchemy.orm import selectinload

requests = db.query(models.BookRequest).options(
    selectinload(models.BookRequest.book)  # Separate SELECT with IN clause
).all()
```

---

## WARNING: Database Anti-Patterns

### Query Inside Loop

**The Problem:**

```python
# BAD - N queries for N books
@router.get("/books/availability")
async def check_availability(book_ids: list[int], db: Session = Depends(get_db)):
    results = []
    for book_id in book_ids:
        book = db.query(models.Book).filter(models.Book.id == book_id).first()
        results.append({"id": book_id, "available": book.ebook_available if book else False})
    return results
```

**The Fix:**

```python
# GOOD - Single query with IN clause
@router.get("/books/availability")
async def check_availability(book_ids: list[int], db: Session = Depends(get_db)):
    books = db.query(models.Book).filter(models.Book.id.in_(book_ids)).all()
    book_map = {b.id: b for b in books}
    return [
        {"id": bid, "available": book_map.get(bid, {}).ebook_available if bid in book_map else False}
        for bid in book_ids
    ]
```

### Missing Index

**The Problem:**

```python
# Slow query on unindexed column
requests = db.query(models.BookRequest).filter(
    models.BookRequest.status == "pending"  # Full table scan!
).all()
```

**The Fix:**

```python
# backend/app/models.py - Add index
class BookRequest(Base):
    __tablename__ = "book_requests"
    status = Column(String, index=True)  # Index added

# Or via Alembic migration
# See the **alembic** skill for migration patterns
```

### Session Leak

**The Problem:**

```python
# BAD - Session never closed on exception
def process_data():
    db = SessionLocal()
    result = db.query(models.Book).filter(...).all()
    process(result)  # If this raises, session leaks
    db.close()
```

**The Fix:**

```python
# GOOD - Always use try/finally or context manager
def process_data():
    db = SessionLocal()
    try:
        result = db.query(models.Book).filter(...).all()
        process(result)
    finally:
        db.close()
```
