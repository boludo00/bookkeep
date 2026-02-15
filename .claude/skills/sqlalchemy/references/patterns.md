# SQLAlchemy Patterns Reference

## Contents
- Model Definition Patterns
- Query Patterns
- Relationship Patterns
- Session Management
- Anti-Patterns

## Model Definition Patterns

### Standard Model Structure

Every model follows this structure in `backend/app/models.py`:

```python
class DownloadTask(Base):
    __tablename__ = "download_tasks"

    # Primary key with index
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign key with index for JOIN performance
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False, index=True)
    
    # Indexed columns for frequent queries
    state = Column(String, default="queued", nullable=False, index=True)
    
    # Timestamps with server defaults
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    book = relationship("Book", back_populates="download_tasks")
```

### Computed Properties on Models

```python
# backend/app/models.py:71-74
class Book(Base):
    ebook_available = Column(Boolean, default=False)
    audiobook_available = Column(Boolean, default=False)

    @property
    def is_available(self):
        """Book is available if either format exists."""
        return self.ebook_available or self.audiobook_available
```

## Query Patterns

### Basic CRUD

```python
# CREATE
db_book = models.Book(**book_dict)
db.add(db_book)
db.commit()
db.refresh(db_book)

# READ
book = db.query(models.Book).filter(models.Book.id == book_id).first()

# UPDATE
for key, value in update_dict.items():
    setattr(book, key, value)
db.commit()

# DELETE
db.delete(book)
db.commit()
```

### Pagination

```python
# backend/app/routers/books.py:236-238
@router.get("/", response_model=list[schemas.BookResponse])
def get_books(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    books = db.query(models.Book).offset(skip).limit(limit).all()
    return books
```

### Filtering with Exclusions

```python
# backend/app/routers/books.py:106-109 - Find requests NOT denied
requests = db.query(models.BookRequest).filter(
    models.BookRequest.book_id == book.id,
    models.BookRequest.status != "denied",
).all()
```

### Extracting Scalar Values

```python
# backend/app/tasks.py:98-99 - Get only hardcover_ids, not full objects
existing_ids = set(
    row[0] for row in db.query(Book.hardcover_id).filter(
        Book.hardcover_id.isnot(None)
    ).all()
)
```

## Relationship Patterns

### Bidirectional One-to-Many

```python
# Parent side
class User(Base):
    requests = relationship("BookRequest", back_populates="user")

# Child side
class BookRequest(Base):
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="requests")
```

### Cascade Delete

```python
# backend/app/models.py:69 - Delete tasks when book is deleted
download_tasks = relationship(
    "DownloadTask", 
    back_populates="book", 
    cascade="all, delete-orphan"
)
```

### Eager Loading with joinedload

```python
# backend/app/routers/requests.py:196-200
from sqlalchemy.orm import joinedload

query = db.query(models.BookRequest).options(
    joinedload(models.BookRequest.book),
    joinedload(models.BookRequest.user)
)
```

## Session Management

### Database Connection (PostgreSQL)

```python
# backend/app/database.py:50-62
pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20"))

engine = create_engine(
    DATABASE_URL,
    pool_size=pool_size,
    max_overflow=max_overflow,
    pool_timeout=30,
    pool_recycle=1800,  # Recycle connections after 30 min
    pool_pre_ping=True,  # Verify connections before use
)
```

### Session Dependency

```python
# backend/app/database.py:68-74
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

## Anti-Patterns

### WARNING: N+1 Query Problem

**The Problem:**

```python
# BAD - Each request triggers a query for book and user
requests = db.query(models.BookRequest).all()
for req in requests:
    print(req.book.title)  # N additional queries
    print(req.user.username)  # N more queries
```

**Why This Breaks:**
1. 100 requests = 201 database queries (1 + 100 + 100)
2. Exponential response time degradation
3. Database connection exhaustion under load

**The Fix:**

```python
# GOOD - One query with JOINs
from sqlalchemy.orm import joinedload

requests = db.query(models.BookRequest).options(
    joinedload(models.BookRequest.book),
    joinedload(models.BookRequest.user)
).all()
```

### WARNING: Missing Session Commit

**The Problem:**

```python
# BAD - Changes not persisted
book.title = "New Title"
db.refresh(book)  # Still has old title!
```

**The Fix:**

```python
# GOOD - Commit before refresh
book.title = "New Title"
db.commit()
db.refresh(book)
```

### WARNING: Using `==` for None Comparison

**The Problem:**

```python
# BAD - SQL generates `column = NULL` which is always false
books = db.query(Book).filter(Book.hardcover_id == None).all()
```

**The Fix:**

```python
# GOOD - Use is_/isnot for NULL checks
books = db.query(Book).filter(Book.hardcover_id.is_(None)).all()
books = db.query(Book).filter(Book.hardcover_id.isnot(None)).all()