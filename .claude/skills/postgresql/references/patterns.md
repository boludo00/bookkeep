# PostgreSQL Patterns Reference

## Contents
- Query Patterns
- Transaction Handling
- N+1 Prevention
- Race Condition Handling
- Data Type Patterns
- Anti-Patterns

---

## Query Patterns

### Basic CRUD Operations

```python
# backend/app/routers/books.py

# READ single record
db_book = db.query(Book).filter(Book.id == book_id).first()

# READ with pagination
books = db.query(Book).offset(skip).limit(limit).all()

# READ with multiple filters
requests = db.query(BookRequest).filter(
    BookRequest.book_id == request.book_id,
    BookRequest.format == request.format,
    BookRequest.status != "denied"
).first()

# CREATE
db_book = Book(**book_dict)
db.add(db_book)
db.commit()
db.refresh(db_book)

# UPDATE
for key, value in book_dict.items():
    setattr(db_book, key, value)
db.commit()

# DELETE
db.delete(db_book)
db.commit()
```

### Complex Filtering

```python
from sqlalchemy import or_

# OR conditions
books = db.query(Book).filter(
    or_(
        Book.ebook_available == True,
        Book.audiobook_available == True
    )
).all()

# IN clause (backend/app/routers/downloads.py:69)
existing_task = db.query(DownloadTask).filter(
    DownloadTask.book_id == book_id,
    DownloadTask.state.in_(['queued', 'downloading', 'complete', 'seeding'])
).first()

# Aggregation
admin_count = db.query(User).filter(User.is_admin == True).count()
```

---

## Transaction Handling

### Explicit Flush for Early Constraint Detection

```python
# backend/app/routers/books.py:99-124
try:
    db_book = Book(**book_dict)
    db.add(db_book)
    db.flush()  # Triggers INSERT, catches constraint violations
    db.commit()
    db.refresh(db_book)
except IntegrityError:
    db.rollback()
    # Handle duplicate gracefully
```

### Multi-Object Atomic Updates

```python
# Update related objects in single transaction
if ebook_available:
    requests = db.query(BookRequest).filter(
        BookRequest.book_id == book.id,
        BookRequest.status != "denied",
    ).all()
    
    for request in requests:
        if request.format == "ebook":
            request.status = "available"
            db.add(request)  # Mark for update
    
    db.add(book)
    db.commit()  # All changes committed atomically
```

### Background Tasks with New Sessions

```python
# backend/app/tasks.py - Background jobs create own sessions
async def refresh_seed_data():
    db: Session = SessionLocal()
    try:
        job = db.query(JobSchedule).filter(
            JobSchedule.job_name == "refresh_seed_data"
        ).first()
        # ... work with db ...
        db.commit()
    finally:
        db.close()  # CRITICAL: Always close
```

---

## N+1 Prevention

### WARNING: Missing joinedload Causes N+1

**The Problem:**

```python
# BAD - N+1 queries: 1 + len(requests) queries
requests = db.query(BookRequest).all()
for r in requests:
    print(r.book.title)  # Each access triggers SELECT
```

**The Fix:**

```python
# GOOD - Single query with JOIN
from sqlalchemy.orm import joinedload

requests = db.query(BookRequest).options(
    joinedload(BookRequest.book),
    joinedload(BookRequest.user)
).all()
```

---

## Race Condition Handling

### Check-Then-Create Pattern

```python
# backend/app/routers/books.py
existing = db.query(Book).filter(Book.hardcover_id == id).first()
if existing:
    return existing

try:
    db.add(Book(**data))
    db.flush()
    db.commit()
except IntegrityError:
    db.rollback()
    # Concurrent insert won - use their record
    return db.query(Book).filter(Book.hardcover_id == id).first()
```

---

## Data Type Patterns

### JSON Storage for Flexible Data

```python
# backend/app/models.py - Store JSON as Text
path_mappings_json = Column(Text, nullable=True)
indexer_ids_json = Column(Text, nullable=True)
release_data_json = Column(Text, nullable=True)

# Application handles serialization
import json
hashes = json.loads(book.downloaded_release_hashes) if book.downloaded_release_hashes else []
book.downloaded_release_hashes = json.dumps(hashes)
```

### Large Integers for Byte Counts

```python
# Use BigInteger for file sizes (bytes can exceed 2^31)
size_bytes = Column(BigInteger, nullable=True)
downloaded_bytes = Column(BigInteger, nullable=True)
```

### Strings for Enums (Flexible)

```python
# No ENUM type - strings allow easy additions
format = Column(String)   # 'ebook', 'audiobook'
status = Column(String)   # 'pending', 'approved', 'denied', 'processing', 'available'
state = Column(String)    # 'queued', 'downloading', 'complete', 'error'
```

---

## Anti-Patterns

### WARNING: Creating Sessions Without Closing

**The Problem:**

```python
# BAD - Connection leak
def process_data():
    db = SessionLocal()
    result = db.query(Book).all()
    return result  # Session never closed!
```

**The Fix:**

```python
# GOOD - Always use try/finally or context manager
def process_data():
    db = SessionLocal()
    try:
        return db.query(Book).all()
    finally:
        db.close()
```

### WARNING: Committing Inside Loops

**The Problem:**

```python
# BAD - 100 separate transactions, 100x slower
for book in books:
    book.status = "processed"
    db.commit()  # Commits on every iteration
```

**The Fix:**

```python
# GOOD - Single transaction
for book in books:
    book.status = "processed"
db.commit()  # One commit at the end
```

### WARNING: Using refresh() Before commit()

**The Problem:**

```python
# BAD - refresh() before commit() is meaningless
db.add(book)
db.refresh(book)  # Object not yet in DB!
db.commit()
```

**The Fix:**

```python
# GOOD - Commit first, then refresh to get DB-generated values
db.add(book)
db.commit()
db.refresh(book)  # Now has id, created_at, etc.
```