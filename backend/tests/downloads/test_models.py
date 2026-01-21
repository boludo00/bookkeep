"""
Integration tests for download system database models.

Tests DownloadClient and DownloadTask models with actual database.
"""
import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models import Book, DownloadClient, DownloadTask
from app.database import SessionLocal, engine, Base


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test"""
    # Create tables
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        # Clean up - drop all tables
        Base.metadata.drop_all(bind=engine)


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


class TestDownloadClientModel:
    """Test DownloadClient model"""

    def test_create_qbittorrent_client(self, db_session: Session):
        """Test creating a qBittorrent client"""
        client = DownloadClient(
            name="qBittorrent",
            type="qbittorrent",
            protocol="torrent",
            host="192.168.1.100",
            port=8080,
            username="admin",
            password="adminpass",
            enabled=True,
            priority=10,
            category="books",
        )
        db_session.add(client)
        db_session.commit()
        db_session.refresh(client)

        assert client.id is not None
        assert client.name == "qBittorrent"
        assert client.type == "qbittorrent"
        assert client.protocol == "torrent"
        assert client.host == "192.168.1.100"
        assert client.port == 8080
        assert client.enabled is True
        assert client.priority == 10
        assert client.created_at is not None

    def test_create_nzbget_client(self, db_session: Session):
        """Test creating an NZBGet client"""
        client = DownloadClient(
            name="NZBGet",
            type="nzbget",
            protocol="usenet",
            host="192.168.1.101",
            port=6789,
            username="nzbget",
            password="secret",
            enabled=True,
            priority=5,
        )
        db_session.add(client)
        db_session.commit()
        db_session.refresh(client)

        assert client.type == "nzbget"
        assert client.protocol == "usenet"
        assert client.port == 6789

    def test_unique_name_constraint(self, db_session: Session):
        """Test that client names must be unique"""
        client1 = DownloadClient(
            name="TestClient",
            type="qbittorrent",
            protocol="torrent",
            host="host1",
            port=8080,
        )
        db_session.add(client1)
        db_session.commit()

        # Try to create another with same name
        client2 = DownloadClient(
            name="TestClient",  # Same name!
            type="nzbget",
            protocol="usenet",
            host="host2",
            port=6789,
        )
        db_session.add(client2)

        with pytest.raises(Exception):  # IntegrityError or similar
            db_session.commit()

    def test_path_mappings_json(self, db_session: Session):
        """Test storing path mappings as JSON"""
        import json

        mappings = [
            {"remote": "/downloads", "local": "/data/downloads"},
            {"remote": "/media", "local": "/data/media"},
        ]

        client = DownloadClient(
            name="Docker-qBittorrent",
            type="qbittorrent",
            protocol="torrent",
            host="qbittorrent",
            port=8080,
            path_mappings_json=json.dumps(mappings),
        )
        db_session.add(client)
        db_session.commit()
        db_session.refresh(client)

        # Retrieve and parse
        loaded_mappings = json.loads(client.path_mappings_json)
        assert len(loaded_mappings) == 2
        assert loaded_mappings[0]["remote"] == "/downloads"
        assert loaded_mappings[1]["local"] == "/data/media"

    def test_optional_fields(self, db_session: Session):
        """Test that optional fields can be None"""
        client = DownloadClient(
            name="Minimal",
            type="qbittorrent",
            protocol="torrent",
            host="localhost",
            port=8080,
            # username, password, category, path_mappings_json all None
        )
        db_session.add(client)
        db_session.commit()
        db_session.refresh(client)

        assert client.username is None
        assert client.password is None
        assert client.category is None
        assert client.path_mappings_json is None


class TestDownloadTaskModel:
    """Test DownloadTask model"""

    def test_create_task(self, db_session: Session, sample_book: Book):
        """Test creating a download task"""
        task = DownloadTask(
            book_id=sample_book.id,
            format="ebook",
            source="prowlarr",
            release_title="Test Book [EPUB]",
            download_url="http://indexer.com/download/12345",
            protocol="torrent",
            indexer="test-indexer",
            indexer_id=999,
            size_bytes=2048000,
            state="queued",
            progress=0.0,
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.id is not None
        assert task.book_id == sample_book.id
        assert task.format == "ebook"
        assert task.source == "prowlarr"
        assert task.state == "queued"
        assert task.progress == 0.0
        assert task.created_at is not None

    def test_task_book_relationship(self, db_session: Session, sample_book: Book):
        """Test relationship between task and book"""
        task = DownloadTask(
            book_id=sample_book.id,
            format="audiobook",
            source="prowlarr",
            state="downloading",
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        # Access book via relationship
        assert task.book.id == sample_book.id
        assert task.book.title == "Test Book"

        # Access tasks from book
        db_session.refresh(sample_book)
        assert len(sample_book.download_tasks) == 1
        assert sample_book.download_tasks[0].id == task.id

    def test_cascade_delete(self, db_session: Session, sample_book: Book):
        """Test that deleting book cascades to tasks"""
        task1 = DownloadTask(
            book_id=sample_book.id,
            format="ebook",
            source="prowlarr",
            state="complete",
        )
        task2 = DownloadTask(
            book_id=sample_book.id,
            format="audiobook",
            source="prowlarr",
            state="downloading",
        )
        db_session.add_all([task1, task2])
        db_session.commit()

        # Verify tasks exist
        tasks_before = db_session.query(DownloadTask).filter(
            DownloadTask.book_id == sample_book.id
        ).count()
        assert tasks_before == 2

        # Delete book
        db_session.delete(sample_book)
        db_session.commit()

        # Verify tasks were deleted
        tasks_after = db_session.query(DownloadTask).filter(
            DownloadTask.book_id == sample_book.id
        ).count()
        assert tasks_after == 0

    def test_update_progress(self, db_session: Session, sample_book: Book):
        """Test updating task progress"""
        task = DownloadTask(
            book_id=sample_book.id,
            format="ebook",
            source="prowlarr",
            state="queued",
            progress=0.0,
        )
        db_session.add(task)
        db_session.commit()

        # Update to downloading
        task.state = "downloading"
        task.progress = 25.5
        task.download_speed = 1024000.0
        task.started_at = datetime.now(timezone.utc)
        db_session.commit()

        # Retrieve and verify
        db_session.refresh(task)
        assert task.state == "downloading"
        assert task.progress == 25.5
        assert task.download_speed == 1024000.0
        assert task.started_at is not None

        # Update to complete
        task.state = "complete"
        task.progress = 100.0
        task.completed_at = datetime.now(timezone.utc)
        task.final_path = "/library/Test Author/Test Book.epub"
        db_session.commit()

        db_session.refresh(task)
        assert task.state == "complete"
        assert task.progress == 100.0
        assert task.completed_at is not None
        assert task.final_path is not None

    def test_client_tracking(self, db_session: Session, sample_book: Book):
        """Test tracking which client is handling download"""
        task = DownloadTask(
            book_id=sample_book.id,
            format="ebook",
            source="prowlarr",
            state="downloading",
            client_type="qbittorrent",
            client_download_id="abc123def456",
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.client_type == "qbittorrent"
        assert task.client_download_id == "abc123def456"

    def test_store_release_data_json(self, db_session: Session, sample_book: Book):
        """Test storing full release data as JSON"""
        import json

        release_data = {
            "guid": "https://indexer.com/details/12345",
            "seeders": 10,
            "leechers": 2,
            "publishDate": "2024-01-15T10:30:00Z",
            "categories": [7020, 7000],
            "downloadUrl": "http://indexer.com/download/12345",
        }

        task = DownloadTask(
            book_id=sample_book.id,
            format="ebook",
            source="prowlarr",
            state="queued",
            release_data_json=json.dumps(release_data),
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        # Retrieve and parse
        loaded_data = json.loads(task.release_data_json)
        assert loaded_data["guid"] == "https://indexer.com/details/12345"
        assert loaded_data["seeders"] == 10
        assert loaded_data["categories"] == [7020, 7000]

    def test_hardlink_paths(self, db_session: Session, sample_book: Book):
        """Test storing paths for hardlinking (torrents)"""
        task = DownloadTask(
            book_id=sample_book.id,
            format="ebook",
            source="prowlarr",
            protocol="torrent",
            state="complete",
            download_path="/downloads/torrents/Test Book/Test Book.epub",
            original_download_path="/downloads/torrents/Test Book/Test Book.epub",
            final_path="/library/Test Author/Test Book.epub",
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.download_path is not None
        assert task.original_download_path is not None
        assert task.final_path is not None
        assert task.download_path == task.original_download_path

    def test_query_by_state(self, db_session: Session, sample_book: Book):
        """Test querying tasks by state"""
        # Create tasks in different states
        task1 = DownloadTask(
            book_id=sample_book.id,
            format="ebook",
            source="prowlarr",
            state="queued",
        )
        task2 = DownloadTask(
            book_id=sample_book.id,
            format="audiobook",
            source="prowlarr",
            state="downloading",
        )
        task3 = DownloadTask(
            book_id=sample_book.id,
            format="ebook",
            source="manual",
            state="complete",
        )
        db_session.add_all([task1, task2, task3])
        db_session.commit()

        # Query by state
        queued = db_session.query(DownloadTask).filter(
            DownloadTask.state == "queued"
        ).all()
        assert len(queued) == 1
        assert queued[0].id == task1.id

        downloading = db_session.query(DownloadTask).filter(
            DownloadTask.state == "downloading"
        ).all()
        assert len(downloading) == 1

        complete = db_session.query(DownloadTask).filter(
            DownloadTask.state == "complete"
        ).all()
        assert len(complete) == 1

    def test_multiple_tasks_per_book(self, db_session: Session, sample_book: Book):
        """Test that a book can have multiple download tasks"""
        # Ebook task
        ebook_task = DownloadTask(
            book_id=sample_book.id,
            format="ebook",
            source="prowlarr",
            state="complete",
            completed_at=datetime.now(timezone.utc),
        )
        # Audiobook task
        audiobook_task = DownloadTask(
            book_id=sample_book.id,
            format="audiobook",
            source="prowlarr",
            state="downloading",
        )
        db_session.add_all([ebook_task, audiobook_task])
        db_session.commit()

        # Query tasks for book
        db_session.refresh(sample_book)
        tasks = sample_book.download_tasks
        assert len(tasks) == 2

        formats = {task.format for task in tasks}
        assert "ebook" in formats
        assert "audiobook" in formats
