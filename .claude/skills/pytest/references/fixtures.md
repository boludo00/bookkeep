# Fixtures Reference

## Contents
- Fixture Scopes
- Fixture Dependencies
- Cleanup Patterns
- Parameterized Fixtures
- Shared Fixtures (conftest.py)

## Fixture Scopes

### Function Scope (Default)

Fresh fixture for each test function:

```python
@pytest.fixture  # scope="function" is default
def mock_client():
    """Fresh client for each test"""
    client = ProwlarrClient(base_url="http://test:9696", api_key="key")
    return client
```

### Class Scope

Shared within a test class:

```python
@pytest.fixture(scope="class")
def expensive_setup():
    """One setup per test class"""
    return load_test_data()
```

### Module Scope

Shared within a test file:

```python
@pytest.fixture(scope="module")
def database_connection():
    """One connection per test module"""
    conn = create_connection()
    yield conn
    conn.close()
```

## Fixture Dependencies

Fixtures can depend on other fixtures:

```python
@pytest.fixture(scope="function")
def db_session():
    """Base database session"""
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def sample_book(db_session: Session):
    """Book fixture depends on db_session"""
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


@pytest.fixture
def sample_task(db_session: Session, sample_book: Book):
    """Task fixture depends on both db_session and sample_book"""
    task = DownloadTask(
        book_id=sample_book.id,
        format="ebook",
        source="prowlarr",
        state="queued",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task
```

## Cleanup Patterns

### Context Manager (yield)

```python
@pytest.fixture
def mock_qb_client():
    """Fixture with setup and teardown"""
    with patch('app.downloads.clients.qbittorrent.QBClient') as mock_class:
        mock_instance = Mock()
        mock_class.return_value = mock_instance
        mock_instance.app.version = "v4.6.0"
        
        client = QBittorrentClient(host="localhost", port=8080, ...)
        yield client  # Test runs here
        # Cleanup happens automatically when context exits
```

### Explicit Teardown

```python
@pytest.fixture
def temp_file():
    """Fixture with explicit cleanup"""
    path = "/tmp/test_file.txt"
    with open(path, "w") as f:
        f.write("test content")
    yield path
    # Cleanup
    if os.path.exists(path):
        os.remove(path)
```

### Database Cleanup

```python
@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)  # Clean slate
```

## Mock Response Fixtures

```python
@pytest.fixture
def mock_queue_group():
    """Mock NZBGet queue group data"""
    return {
        "NZBID": 123,
        "NZBName": "Test Book [EPUB]",
        "Status": "DOWNLOADING",
        "FileSizeMB": 5,
        "RemainingSizeMB": 2,
        "DownloadRate": 1048576,
        "Category": "books",
        "DestDir": "/downloads/books/Test Book [EPUB]",
    }


@pytest.fixture
def mock_history_item():
    """Mock NZBGet history item data"""
    return {
        "NZBID": 456,
        "NZBName": "Completed Book [EPUB]",
        "Status": "SUCCESS",
        "ParStatus": "SUCCESS",
        "UnpackStatus": "SUCCESS",
        "FileSizeMB": 10,
        "Category": "books",
        "DestDir": "/downloads/completed/Completed Book [EPUB]",
    }
```

## Shared Fixtures (conftest.py)

Place fixtures used across multiple test files in `conftest.py`:

```python
# backend/tests/conftest.py

import pytest
from app.database import SessionLocal, engine, Base


@pytest.fixture(scope="function")
def db_session():
    """Shared database session fixture"""
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def api_client():
    """Shared test client for FastAPI"""
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)
```

## WARNING: Fixture Scope Mismatch

Function-scoped fixtures cannot depend on narrower scopes:

```python
# BAD - Will error
@pytest.fixture(scope="module")
def module_fixture(function_fixture):  # Error!
    pass

# GOOD - Wider scope can depend on narrower
@pytest.fixture(scope="function")
def function_fixture(module_fixture):  # OK
    pass
```

## Workflow: Adding New Tests

Copy this checklist:
- [ ] Create test file in appropriate directory
- [ ] Import pytest and unittest.mock
- [ ] Create fixtures for test subjects and dependencies
- [ ] Group tests by functionality in classes
- [ ] Run tests: `uv run pytest tests/path/test_file.py -v`
- [ ] Verify all tests pass before committing

See the **python** skill for Python coding patterns.