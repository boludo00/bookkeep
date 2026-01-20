"""
Unit tests for download plugin system.

Tests the plugin registry, base classes, and dataclasses.
"""
import pytest
from unittest.mock import Mock
from typing import List, Optional

from app.downloads import (
    DownloadState,
    Release,
    DownloadStatus,
    DownloadTask,
    ReleaseSource,
    DownloadHandler,
    register_source,
    register_handler,
    get_source,
    get_handler,
    list_sources,
    list_handlers,
)


class TestDownloadState:
    """Test DownloadState enum"""

    def test_all_states_exist(self):
        """Test that all expected states exist"""
        expected_states = [
            "QUEUED",
            "DOWNLOADING",
            "COMPLETE",
            "ERROR",
            "SEEDING",
            "PAUSED",
            "CHECKING",
            "PROCESSING",
        ]
        for state_name in expected_states:
            assert hasattr(DownloadState, state_name)

    def test_state_values(self):
        """Test that state values are lowercase strings"""
        assert DownloadState.QUEUED.value == "queued"
        assert DownloadState.DOWNLOADING.value == "downloading"
        assert DownloadState.COMPLETE.value == "complete"


class TestRelease:
    """Test Release dataclass"""

    def test_create_minimal_release(self):
        """Test creating release with only required fields"""
        release = Release(
            source="test",
            title="Test Book",
            download_url="http://example.com/test.torrent",
            protocol="torrent",
            size_bytes=1024000,
        )
        assert release.source == "test"
        assert release.title == "Test Book"
        assert release.protocol == "torrent"
        assert release.seeders is None
        assert release.format is None

    def test_create_full_release(self):
        """Test creating release with all fields"""
        release = Release(
            source="prowlarr",
            title="Test Book [EPUB]",
            download_url="http://example.com/test.torrent",
            protocol="torrent",
            size_bytes=2048000,
            seeders=10,
            leechers=2,
            indexer="test-indexer",
            indexer_id=123,
            category="Books",
            format="epub",
            language="en",
            quality_score=85.0,
            metadata={"custom": "data"},
        )
        assert release.seeders == 10
        assert release.format == "epub"
        assert release.language == "en"
        assert release.quality_score == 85.0
        assert release.metadata == {"custom": "data"}


class TestDownloadStatus:
    """Test DownloadStatus dataclass"""

    def test_create_status(self):
        """Test creating download status"""
        status = DownloadStatus(
            state=DownloadState.DOWNLOADING,
            progress=50.0,
            download_speed=1024000,
            eta_seconds=300,
            message="Downloading...",
        )
        assert status.state == DownloadState.DOWNLOADING
        assert status.progress == 50.0
        assert status.download_speed == 1024000

    def test_complete_property(self):
        """Test the complete property"""
        # Complete state
        status = DownloadStatus(state=DownloadState.COMPLETE, progress=100.0)
        assert status.complete is True

        # Seeding state (also complete)
        status = DownloadStatus(state=DownloadState.SEEDING, progress=100.0)
        assert status.complete is True

        # Downloading state (not complete)
        status = DownloadStatus(state=DownloadState.DOWNLOADING, progress=50.0)
        assert status.complete is False

        # Error state (not complete)
        status = DownloadStatus(state=DownloadState.ERROR, progress=0.0)
        assert status.complete is False


class TestDownloadTask:
    """Test DownloadTask dataclass"""

    def test_create_task(self):
        """Test creating download task"""
        release = Release(
            source="prowlarr",
            title="Test Book",
            download_url="http://example.com/test.torrent",
            protocol="torrent",
            size_bytes=1024000,
        )

        task = DownloadTask(
            task_id="test-123",
            book_id=1,
            format="ebook",
            source="prowlarr",
            release=release,
        )

        assert task.task_id == "test-123"
        assert task.book_id == 1
        assert task.format == "ebook"
        assert task.source == "prowlarr"
        assert task.release == release
        assert task.download_path is None
        assert task.client_type is None


class TestPluginRegistry:
    """Test plugin registration and retrieval"""

    def test_register_and_get_source(self):
        """Test registering and retrieving a source"""

        @register_source("test_source")
        class TestSource(ReleaseSource):
            @property
            def name(self) -> str:
                return "test_source"

            def search(
                self,
                title: str,
                author: Optional[str] = None,
                isbn: Optional[str] = None,
                format_type: str = "ebook",
            ) -> List[Release]:
                return []

            def test_connection(self) -> bool:
                return True

        # Verify it's registered
        assert "test_source" in list_sources()

        # Retrieve it
        source = get_source("test_source")
        assert isinstance(source, TestSource)
        assert source.name == "test_source"
        assert source.test_connection() is True

    def test_register_and_get_handler(self):
        """Test registering and retrieving a handler"""

        @register_handler("test_handler")
        class TestHandler(DownloadHandler):
            @property
            def source_name(self) -> str:
                return "test_handler"

            def download(self, task, cancel_flag, progress_callback, status_callback):
                return "/tmp/test.epub"

            def cleanup(self, task, success):
                pass

        # Verify it's registered
        assert "test_handler" in list_handlers()

        # Retrieve it
        handler = get_handler("test_handler")
        assert isinstance(handler, TestHandler)
        assert handler.source_name == "test_handler"

    def test_get_unknown_source_raises_error(self):
        """Test that getting unknown source raises ValueError"""
        with pytest.raises(ValueError, match="Unknown source"):
            get_source("unknown_source_xyz")

    def test_get_unknown_handler_raises_error(self):
        """Test that getting unknown handler raises ValueError"""
        with pytest.raises(ValueError, match="No handler for source"):
            get_handler("unknown_handler_xyz")


class TestReleaseSourceInterface:
    """Test ReleaseSource abstract base class"""

    def test_must_implement_name(self):
        """Test that name property must be implemented"""

        class IncompleteSource(ReleaseSource):
            def search(self, title, author=None, isbn=None, format_type="ebook"):
                return []

            def test_connection(self):
                return True

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteSource()

    def test_must_implement_search(self):
        """Test that search method must be implemented"""

        class IncompleteSource(ReleaseSource):
            @property
            def name(self):
                return "test"

            def test_connection(self):
                return True

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteSource()

    def test_must_implement_test_connection(self):
        """Test that test_connection method must be implemented"""

        class IncompleteSource(ReleaseSource):
            @property
            def name(self):
                return "test"

            def search(self, title, author=None, isbn=None, format_type="ebook"):
                return []

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteSource()


class TestDownloadHandlerInterface:
    """Test DownloadHandler abstract base class"""

    def test_must_implement_source_name(self):
        """Test that source_name property must be implemented"""

        class IncompleteHandler(DownloadHandler):
            def download(self, task, cancel_flag, progress_callback, status_callback):
                return None

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteHandler()

    def test_must_implement_download(self):
        """Test that download method must be implemented"""

        class IncompleteHandler(DownloadHandler):
            @property
            def source_name(self):
                return "test"

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteHandler()

    def test_cleanup_is_optional(self):
        """Test that cleanup method has default implementation"""

        class MinimalHandler(DownloadHandler):
            @property
            def source_name(self):
                return "test"

            def download(self, task, cancel_flag, progress_callback, status_callback):
                return None

        handler = MinimalHandler()
        # Should not raise error
        handler.cleanup(None, True)


class TestCallbackPattern:
    """Test that handlers use callbacks correctly"""

    def test_progress_callback(self):
        """Test progress callback pattern"""

        @register_handler("test_progress")
        class TestProgressHandler(DownloadHandler):
            @property
            def source_name(self):
                return "test_progress"

            def download(self, task, cancel_flag, progress_callback, status_callback):
                # Simulate progress updates
                progress_callback(0.0)
                progress_callback(50.0)
                progress_callback(100.0)
                return "/tmp/test.epub"

        handler = get_handler("test_progress")

        # Mock callbacks
        progress_mock = Mock()
        status_mock = Mock()

        # Create minimal task
        release = Release(
            source="test",
            title="Test",
            download_url="http://test",
            protocol="torrent",
            size_bytes=1000,
        )
        task = DownloadTask(
            task_id="test",
            book_id=1,
            format="ebook",
            source="test",
            release=release,
        )

        # Execute download
        result = handler.download(task, Mock(), progress_mock, status_mock)

        # Verify callbacks were called
        assert progress_mock.call_count == 3
        progress_mock.assert_any_call(0.0)
        progress_mock.assert_any_call(50.0)
        progress_mock.assert_any_call(100.0)
        assert result == "/tmp/test.epub"

    def test_status_callback(self):
        """Test status callback pattern"""

        @register_handler("test_status")
        class TestStatusHandler(DownloadHandler):
            @property
            def source_name(self):
                return "test_status"

            def download(self, task, cancel_flag, progress_callback, status_callback):
                # Simulate status updates
                status_callback(DownloadState.QUEUED, "Queued")
                status_callback(DownloadState.DOWNLOADING, "Downloading")
                status_callback(DownloadState.COMPLETE, "Complete")
                return "/tmp/test.epub"

        handler = get_handler("test_status")

        progress_mock = Mock()
        status_mock = Mock()

        release = Release(
            source="test",
            title="Test",
            download_url="http://test",
            protocol="torrent",
            size_bytes=1000,
        )
        task = DownloadTask(
            task_id="test",
            book_id=1,
            format="ebook",
            source="test",
            release=release,
        )

        result = handler.download(task, Mock(), progress_mock, status_mock)

        assert status_mock.call_count == 3
        status_mock.assert_any_call(DownloadState.QUEUED, "Queued")
        status_mock.assert_any_call(DownloadState.DOWNLOADING, "Downloading")
        status_mock.assert_any_call(DownloadState.COMPLETE, "Complete")


class TestCancellation:
    """Test cancellation support"""

    def test_cancel_flag_checked(self):
        """Test that handlers can check cancel flag"""
        from threading import Event

        @register_handler("test_cancel")
        class TestCancelHandler(DownloadHandler):
            @property
            def source_name(self):
                return "test_cancel"

            def download(self, task, cancel_flag, progress_callback, status_callback):
                if cancel_flag.is_set():
                    return None
                return "/tmp/test.epub"

        handler = get_handler("test_cancel")

        release = Release(
            source="test",
            title="Test",
            download_url="http://test",
            protocol="torrent",
            size_bytes=1000,
        )
        task = DownloadTask(
            task_id="test",
            book_id=1,
            format="ebook",
            source="test",
            release=release,
        )

        # Test without cancellation
        cancel_flag = Event()
        result = handler.download(task, cancel_flag, Mock(), Mock())
        assert result == "/tmp/test.epub"

        # Test with cancellation
        cancel_flag.set()
        result = handler.download(task, cancel_flag, Mock(), Mock())
        assert result is None
