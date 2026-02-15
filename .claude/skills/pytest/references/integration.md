# Integration Testing Reference

## Contents
- Database Integration Tests
- Session Fixture Patterns
- Testing Relationships
- Transaction Rollback Patterns
- API Integration Testing

## Database Integration Tests

Integration tests use real database sessions to verify ORM behavior.

```python
# backend/tests/downloads/test_models.py

from app.models import Book, DownloadClient, DownloadTask
from app.database import SessionLocal, engine, Base


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test"""
    Base.metadata.create_all(bind=engine)
    
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
```

**Why `scope="function"`:** Each test gets an isolated database state. Avoids test pollution where one test's data affects another.

## Dependent Fixtures

Build fixtures that depend on other fixtures:

```python
@pytest.fixture
def sample_book(db_session: Session):
    """Create a sample book for testing"""
    book = Book(
        title="Test Book",
        author="Test Author",
        isbn="1234567890",
        hardcover_id=12345,
    )
    db_session.add(book)
    db_session.commit()
    db_session.refresh(book)
    return book


class TestDownloadTaskModel:
    def test_create_task(self, db_session: Session, sample_book: Book):
        task = DownloadTask(
            book_id=sample_book.id,
            format="ebook",
            source="prowlarr",
            state="queued",
        )
        db_session.add(task)
        db_session.commit()
        
        assert task.id is not None
        assert task.book_id == sample_book.id
```

## Testing Relationships

### Forward Relationship

```python
def test_task_book_relationship(self, db_session: Session, sample_book: Book):
    task = DownloadTask(book_id=sample_book.id, format="ebook", ...)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    # Access book via relationship
    assert task.book.id == sample_book.id
    assert task.book.title == "Test Book"
```

### Reverse Relationship

```python
def test_book_tasks_relationship(self, db_session: Session, sample_book: Book):
    task = DownloadTask(book_id=sample_book.id, ...)
    db_session.add(task)
    db_session.commit()
    
    db_session.refresh(sample_book)
    assert len(sample_book.download_tasks) == 1
    assert sample_book.download_tasks[0].id == task.id
```

### Cascade Delete

```python
def test_cascade_delete(self, db_session: Session, sample_book: Book):
    task1 = DownloadTask(book_id=sample_book.id, ...)
    task2 = DownloadTask(book_id=sample_book.id, ...)
    db_session.add_all([task1, task2])
    db_session.commit()

    # Delete parent
    db_session.delete(sample_book)
    db_session.commit()

    # Verify children deleted
    remaining = db_session.query(DownloadTask).filter(
        DownloadTask.book_id == sample_book.id
    ).count()
    assert remaining == 0
```

## Testing Constraints

```python
def test_unique_name_constraint(self, db_session: Session):
    client1 = DownloadClient(name="TestClient", type="qbittorrent", ...)
    db_session.add(client1)
    db_session.commit()

    client2 = DownloadClient(name="TestClient", ...)  # Same name
    db_session.add(client2)

    with pytest.raises(Exception):  # IntegrityError
        db_session.commit()
```

## JSON Field Testing

```python
def test_path_mappings_json(self, db_session: Session):
    import json

    mappings = [
        {"remote": "/downloads", "local": "/data/downloads"},
        {"remote": "/media", "local": "/data/media"},
    ]

    client = DownloadClient(
        name="Docker-qBittorrent",
        path_mappings_json=json.dumps(mappings),
        ...
    )
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    loaded = json.loads(client.path_mappings_json)
    assert len(loaded) == 2
    assert loaded[0]["remote"] == "/downloads"
```

## WARNING: Test Database Configuration

Ensure tests use a separate test database or in-memory SQLite. Never run integration tests against production data.

See the **postgresql** skill for database configuration patterns.