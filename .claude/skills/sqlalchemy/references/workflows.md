# SQLAlchemy Workflows Reference

## Contents
- Creating New Models
- Database Migrations
- Background Job Queries
- Testing Database Code
- Handling Race Conditions

## Creating New Models

### Workflow Checklist

Copy this checklist and track progress:
- [ ] Step 1: Add model class to `backend/app/models.py`
- [ ] Step 2: Add indexes for frequently queried columns
- [ ] Step 3: Create Alembic migration
- [ ] Step 4: Add Pydantic schemas to `backend/app/schemas.py`
- [ ] Step 5: Test migration with `alembic upgrade head`

### Model Template

```python
# backend/app/models.py
class NewModel(Base):
    __tablename__ = "new_models"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    
    # Foreign keys
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="new_models")
```

## Database Migrations

### Generate Migration

```bash
cd backend
alembic revision --autogenerate -m "add_new_feature"
```

### Migration Pattern

```python
# backend/alembic/versions/022_add_download_system.py
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()

def upgrade():
    if not table_exists('new_table'):
        op.create_table(
            'new_table',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_new_table_name', 'new_table', ['name'], unique=True)

def downgrade():
    if table_exists('new_table'):
        op.drop_index('ix_new_table_name', table_name='new_table')
        op.drop_table('new_table')
```

### Apply Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## Background Job Queries

Background jobs in `backend/app/tasks.py` create their own sessions:

```python
# backend/app/tasks.py:73-76
from app.database import SessionLocal

async def refresh_seed_data():
    db: Session = SessionLocal()
    try:
        # Query and process data
        job = db.query(JobSchedule).filter(
            JobSchedule.job_name == "refresh_seed_data"
        ).first()
        
        # Batch process to avoid memory issues
        existing_ids = set(
            row[0] for row in db.query(Book.hardcover_id).filter(
                Book.hardcover_id.isnot(None)
            ).all()
        )
        
        # Commit changes
        db.commit()
    finally:
        db.close()
```

## Testing Database Code

See the **pytest** skill for full testing patterns.

```python
# backend/tests/test_books.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_create_book(db_session):
    book = Book(title="Test Book", author="Test Author")
    db_session.add(book)
    db_session.commit()
    
    assert book.id is not None
    assert book.created_at is not None
```

## Handling Race Conditions

### Upsert with IntegrityError Handling

```python
# backend/app/routers/books.py:185-212
from sqlalchemy.exc import IntegrityError

try:
    db_book = models.Book(**book_dict)
    db.add(db_book)
    db.flush()  # Catch constraint violations early
    db.commit()
    db.refresh(db_book)
except IntegrityError:
    db.rollback()
    # Book was inserted between check and insert
    existing = db.query(models.Book).filter(
        models.Book.hardcover_id == book_dict["hardcover_id"]
    ).first()
    if existing:
        for key, value in book_dict.items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        db_book = existing
    else:
        raise HTTPException(
            status_code=400,
            detail="Duplicate constraint violation"
        )
```

### Double-Check Pattern

```python
# backend/app/routers/books.py:169-182
# First check
if book_dict.get("hardcover_id"):
    existing = db.query(models.Book).filter(
        models.Book.hardcover_id == book_dict["hardcover_id"]
    ).first()
    if existing:
        # Update existing
        return existing

# Double-check before inserting (handle race conditions)
final_check = db.query(models.Book).filter(
    models.Book.hardcover_id == book_dict["hardcover_id"]
).first()
if final_check:
    # Book was inserted between checks
    return final_check

# Safe to create
db_book = models.Book(**book_dict)
```

## Validation Feedback Loop

When working with database operations:

1. Make changes to model/migration
2. Validate: `cd backend && alembic upgrade head`
3. If migration fails, check SQL syntax and column types
4. Test query: `python -c "from app.database import SessionLocal; ..."`
5. Only proceed when validation passes