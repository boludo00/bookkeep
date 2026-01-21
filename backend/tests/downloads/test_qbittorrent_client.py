"""
Unit tests for qBittorrent client.

Tests the QBittorrentClient implementation which handles torrent downloads
via the qBittorrent Web API.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, PropertyMock
from typing import Dict, Any

from app.downloads import DownloadState
from app.downloads.clients.qbittorrent import QBittorrentClient


@pytest.fixture
def mock_qb_client():
    """Create a QBittorrentClient with mocked qbittorrentapi.Client"""
    with patch('app.downloads.clients.qbittorrent.QBClient') as mock_client_class:
        # Create mock client instance
        mock_client_instance = Mock()
        mock_client_class.return_value = mock_client_instance

        # Mock app properties
        mock_client_instance.app.version = "v4.6.0"
        mock_client_instance.app.web_api_version = "2.8.19"

        # Initialize QBittorrentClient
        client = QBittorrentClient(
            host="localhost",
            port=8080,
            username="admin",
            password="admin",
            category="books"
        )

        yield client


@pytest.fixture
def mock_torrent():
    """Create a mock torrent object"""
    torrent = Mock()
    torrent.hash = "abc123def456"
    torrent.name = "Test Book [EPUB].epub"
    torrent.state = "downloading"
    torrent.progress = 0.5
    torrent.dlspeed = 1048576  # 1 MB/s
    torrent.upspeed = 524288  # 512 KB/s
    torrent.eta = 120  # 2 minutes
    torrent.save_path = "/downloads/books"
    torrent.content_path = "/downloads/books/Test Book [EPUB].epub"
    torrent.size = 5242880  # 5 MB
    torrent.downloaded = 2621440  # 2.5 MB
    torrent.num_seeds = 10
    torrent.num_leechs = 5
    torrent.ratio = 1.5
    return torrent


class TestQBittorrentClientInit:
    """Test client initialization"""

    def test_init_basic(self):
        with patch('app.downloads.clients.qbittorrent.QBClient') as mock_client_class:
            mock_client_instance = Mock()
            mock_client_class.return_value = mock_client_instance
            mock_client_instance.app.version = "v4.6.0"

            client = QBittorrentClient(
                host="localhost",
                port=8080,
                username="admin",
                password="admin"
            )

            assert client.host == "localhost"
            assert client.port == 8080
            assert client.username == "admin"
            assert client.password == "admin"
            assert client.use_ssl is False
            assert client.category is None

    def test_init_with_ssl(self):
        with patch('app.downloads.clients.qbittorrent.QBClient') as mock_client_class:
            mock_client_instance = Mock()
            mock_client_class.return_value = mock_client_instance
            mock_client_instance.app.version = "v4.6.0"

            client = QBittorrentClient(
                host="qbittorrent.local",
                port=443,
                username="admin",
                password="admin",
                use_ssl=True
            )

            assert client.use_ssl is True

            # Verify QBClient was called with https:// in the host URL
            mock_client_class.assert_called_once()
            call_kwargs = mock_client_class.call_args.kwargs
            assert "https://" in call_kwargs['host']

    def test_init_with_category(self):
        with patch('app.downloads.clients.qbittorrent.QBClient') as mock_client_class:
            mock_client_instance = Mock()
            mock_client_class.return_value = mock_client_instance
            mock_client_instance.app.version = "v4.6.0"

            client = QBittorrentClient(
                host="localhost",
                port=8080,
                username="admin",
                password="admin",
                category="ebooks"
            )

            assert client.category == "ebooks"

    def test_init_with_path_mappings(self):
        with patch('app.downloads.clients.qbittorrent.QBClient') as mock_client_class:
            mock_client_instance = Mock()
            mock_client_class.return_value = mock_client_instance
            mock_client_instance.app.version = "v4.6.0"

            path_mappings = {
                "/downloads": "/host/downloads",
                "/data": "/host/data"
            }

            client = QBittorrentClient(
                host="localhost",
                port=8080,
                username="admin",
                password="admin",
                path_mappings=path_mappings
            )

            assert client.path_mappings == path_mappings

    def test_init_connection_failure(self):
        with patch('app.downloads.clients.qbittorrent.QBClient') as mock_client_class:
            from app.downloads.clients.qbittorrent import APIConnectionError

            mock_client_instance = Mock()
            mock_client_class.return_value = mock_client_instance
            mock_client_instance.auth_log_in.side_effect = APIConnectionError("Connection refused")

            with pytest.raises(APIConnectionError):
                QBittorrentClient(
                    host="invalid-host",
                    port=9999,
                    username="admin",
                    password="admin"
                )

    def test_init_login_failure(self):
        with patch('app.downloads.clients.qbittorrent.QBClient') as mock_client_class:
            from app.downloads.clients.qbittorrent import LoginFailed

            mock_client_instance = Mock()
            mock_client_class.return_value = mock_client_instance
            mock_client_instance.auth_log_in.side_effect = LoginFailed("Invalid credentials")

            with pytest.raises(LoginFailed):
                QBittorrentClient(
                    host="localhost",
                    port=8080,
                    username="wrong",
                    password="wrong"
                )


class TestTestConnection:
    """Test connection testing"""

    def test_successful_connection(self, mock_qb_client):
        result = mock_qb_client.test_connection()

        assert result is True

    def test_failed_connection(self, mock_qb_client):
        # Make the version property raise an exception when accessed
        type(mock_qb_client.client.app).version = property(
            fget=Mock(side_effect=Exception("Connection failed"))
        )

        result = mock_qb_client.test_connection()

        assert result is False


class TestAddTorrent:
    """Test adding torrents"""

    def test_add_torrent_by_url(self, mock_qb_client):
        mock_qb_client.client.torrents_add.return_value = "Ok."
        mock_qb_client.client.torrents_info.return_value = [Mock(hash="abc123")]
        mock_qb_client.client.torrents_categories.return_value = {"books": {}}

        info_hash = mock_qb_client.add_torrent(
            url="http://example.com/book.torrent"
        )

        assert info_hash == "abc123"
        mock_qb_client.client.torrents_add.assert_called_once()

    def test_add_torrent_by_magnet(self, mock_qb_client):
        magnet = "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12&dn=Book"

        mock_qb_client.client.torrents_add.return_value = "Ok."

        info_hash = mock_qb_client.add_torrent(magnet=magnet)

        # Should extract hash from magnet link
        assert info_hash == "abcdef1234567890abcdef1234567890abcdef12"

    def test_add_torrent_by_file(self, mock_qb_client):
        torrent_bytes = b"torrent file content"

        mock_qb_client.client.torrents_add.return_value = "Ok."
        mock_qb_client.client.torrents_info.return_value = [Mock(hash="file123")]
        mock_qb_client.client.torrents_categories.return_value = {}

        info_hash = mock_qb_client.add_torrent(torrent_file=torrent_bytes)

        assert info_hash == "file123"
        mock_qb_client.client.torrents_add.assert_called_once()

    def test_add_torrent_with_category(self, mock_qb_client):
        mock_qb_client.client.torrents_add.return_value = "Ok."
        mock_qb_client.client.torrents_info.return_value = [Mock(hash="cat123")]
        mock_qb_client.client.torrents_categories.return_value = {}

        info_hash = mock_qb_client.add_torrent(
            url="http://example.com/book.torrent",
            category="ebooks"
        )

        # Should create category
        mock_qb_client.client.torrents_create_category.assert_called_once_with(name="ebooks")

    def test_add_torrent_with_save_path(self, mock_qb_client):
        mock_qb_client.client.torrents_add.return_value = "Ok."
        mock_qb_client.client.torrents_info.return_value = [Mock(hash="path123")]
        mock_qb_client.client.torrents_categories.return_value = {}

        mock_qb_client.add_torrent(
            url="http://example.com/book.torrent",
            save_path="/custom/path"
        )

        # Verify save_path was passed
        call_kwargs = mock_qb_client.client.torrents_add.call_args.kwargs
        assert call_kwargs['save_path'] == "/custom/path"

    def test_add_torrent_with_tags(self, mock_qb_client):
        mock_qb_client.client.torrents_add.return_value = "Ok."
        mock_qb_client.client.torrents_info.return_value = [Mock(hash="tag123")]
        mock_qb_client.client.torrents_categories.return_value = {}

        mock_qb_client.add_torrent(
            url="http://example.com/book.torrent",
            tags=["book", "epub"]
        )

        # Verify tags were passed
        call_kwargs = mock_qb_client.client.torrents_add.call_args.kwargs
        assert call_kwargs['tags'] == ["book", "epub"]

    def test_add_torrent_already_exists(self, mock_qb_client):
        from app.downloads.clients.qbittorrent import Conflict409Error

        mock_qb_client.client.torrents_add.side_effect = Conflict409Error("Torrent already added")
        mock_qb_client.client.torrents_info.return_value = [Mock(hash="exists123")]
        mock_qb_client.client.torrents_categories.return_value = {}

        info_hash = mock_qb_client.add_torrent(
            url="http://example.com/book.torrent"
        )

        # Should still return the hash
        assert info_hash == "exists123"

    def test_add_torrent_no_source_provided(self, mock_qb_client):
        with pytest.raises(ValueError, match="Must provide url, magnet, or torrent_file"):
            mock_qb_client.add_torrent()

    def test_add_torrent_failure(self, mock_qb_client):
        mock_qb_client.client.torrents_add.side_effect = Exception("Add failed")

        info_hash = mock_qb_client.add_torrent(
            url="http://example.com/book.torrent"
        )

        assert info_hash is None


class TestGetDownloadStatus:
    """Test getting download status"""

    def test_get_status_downloading(self, mock_qb_client, mock_torrent):
        mock_torrent.state = "downloading"
        mock_torrent.progress = 0.65

        mock_qb_client.client.torrents_info.return_value = [mock_torrent]
        mock_qb_client.client.torrents_files.return_value = [
            Mock(name="book.epub", size=5242880, progress=0.65)
        ]

        status = mock_qb_client.get_download_status("abc123")

        assert status["state"] == DownloadState.DOWNLOADING
        assert status["progress"] == 65.0
        assert status["download_speed"] == 1048576
        assert status["name"] == "Test Book [EPUB].epub"
        assert len(status["files"]) == 1

    def test_get_status_complete(self, mock_qb_client, mock_torrent):
        mock_torrent.state = "uploading"
        mock_torrent.progress = 1.0

        mock_qb_client.client.torrents_info.return_value = [mock_torrent]
        mock_qb_client.client.torrents_files.return_value = []

        status = mock_qb_client.get_download_status("abc123")

        assert status["state"] == DownloadState.SEEDING
        assert status["progress"] == 100.0

    def test_get_status_paused(self, mock_qb_client, mock_torrent):
        mock_torrent.state = "pausedDL"

        mock_qb_client.client.torrents_info.return_value = [mock_torrent]
        mock_qb_client.client.torrents_files.return_value = []

        status = mock_qb_client.get_download_status("abc123")

        assert status["state"] == DownloadState.PAUSED

    def test_get_status_checking(self, mock_qb_client, mock_torrent):
        mock_torrent.state = "checkingDL"

        mock_qb_client.client.torrents_info.return_value = [mock_torrent]
        mock_qb_client.client.torrents_files.return_value = []

        status = mock_qb_client.get_download_status("abc123")

        assert status["state"] == DownloadState.CHECKING

    def test_get_status_error(self, mock_qb_client, mock_torrent):
        mock_torrent.state = "error"

        mock_qb_client.client.torrents_info.return_value = [mock_torrent]
        mock_qb_client.client.torrents_files.return_value = []

        status = mock_qb_client.get_download_status("abc123")

        assert status["state"] == DownloadState.ERROR

    def test_get_status_not_found(self, mock_qb_client):
        mock_qb_client.client.torrents_info.return_value = []

        status = mock_qb_client.get_download_status("notfound")

        assert status["state"] == DownloadState.ERROR
        assert "not found" in status["message"].lower()

    def test_get_status_with_path_mapping(self, mock_qb_client, mock_torrent):
        mock_qb_client.path_mappings = {
            "/downloads": "/host/downloads"
        }

        mock_torrent.save_path = "/downloads/books"
        mock_torrent.content_path = "/downloads/books/book.epub"

        mock_qb_client.client.torrents_info.return_value = [mock_torrent]
        mock_qb_client.client.torrents_files.return_value = []

        status = mock_qb_client.get_download_status("abc123")

        # save_path is mapped from torrent.save_path (not content_path)
        assert status["save_path"] == "/host/downloads/books"


class TestGetCompletedDownloadPath:
    """Test getting completed download path"""

    def test_get_completed_path(self, mock_qb_client, mock_torrent):
        mock_torrent.progress = 1.0
        mock_torrent.content_path = "/downloads/books/Test Book.epub"

        mock_qb_client.client.torrents_info.return_value = [mock_torrent]

        path = mock_qb_client.get_completed_download_path("abc123")

        assert path == "/downloads/books/Test Book.epub"

    def test_get_completed_path_incomplete(self, mock_qb_client, mock_torrent):
        mock_torrent.progress = 0.75

        mock_qb_client.client.torrents_info.return_value = [mock_torrent]

        path = mock_qb_client.get_completed_download_path("abc123")

        assert path is None

    def test_get_completed_path_not_found(self, mock_qb_client):
        mock_qb_client.client.torrents_info.return_value = []

        path = mock_qb_client.get_completed_download_path("notfound")

        assert path is None

    def test_get_completed_path_with_mapping(self, mock_qb_client, mock_torrent):
        mock_qb_client.path_mappings = {
            "/downloads": "/host/downloads"
        }

        mock_torrent.progress = 1.0
        mock_torrent.content_path = "/downloads/books/book.epub"

        mock_qb_client.client.torrents_info.return_value = [mock_torrent]

        path = mock_qb_client.get_completed_download_path("abc123")

        assert path == "/host/downloads/books/book.epub"


class TestRemoveTorrent:
    """Test removing torrents"""

    def test_remove_torrent_keep_files(self, mock_qb_client):
        result = mock_qb_client.remove_torrent("abc123", delete_files=False)

        assert result is True
        mock_qb_client.client.torrents_delete.assert_called_once_with(
            delete_files=False,
            torrent_hashes="abc123"
        )

    def test_remove_torrent_delete_files(self, mock_qb_client):
        result = mock_qb_client.remove_torrent("abc123", delete_files=True)

        assert result is True
        mock_qb_client.client.torrents_delete.assert_called_once_with(
            delete_files=True,
            torrent_hashes="abc123"
        )

    def test_remove_torrent_failure(self, mock_qb_client):
        mock_qb_client.client.torrents_delete.side_effect = Exception("Delete failed")

        result = mock_qb_client.remove_torrent("abc123")

        assert result is False


class TestPauseResume:
    """Test pausing and resuming torrents"""

    def test_pause_torrent(self, mock_qb_client):
        result = mock_qb_client.pause_torrent("abc123")

        assert result is True
        mock_qb_client.client.torrents_pause.assert_called_once_with(torrent_hashes="abc123")

    def test_pause_torrent_failure(self, mock_qb_client):
        mock_qb_client.client.torrents_pause.side_effect = Exception("Pause failed")

        result = mock_qb_client.pause_torrent("abc123")

        assert result is False

    def test_resume_torrent(self, mock_qb_client):
        result = mock_qb_client.resume_torrent("abc123")

        assert result is True
        mock_qb_client.client.torrents_resume.assert_called_once_with(torrent_hashes="abc123")

    def test_resume_torrent_failure(self, mock_qb_client):
        mock_qb_client.client.torrents_resume.side_effect = Exception("Resume failed")

        result = mock_qb_client.resume_torrent("abc123")

        assert result is False


class TestFindExistingDownload:
    """Test finding existing downloads"""

    def test_find_by_hash(self, mock_qb_client, mock_torrent):
        mock_qb_client.client.torrents_info.return_value = [mock_torrent]

        info_hash = mock_qb_client.find_existing_download(info_hash="abc123")

        assert info_hash == "abc123def456"

    def test_find_by_name(self, mock_qb_client, mock_torrent):
        mock_qb_client.client.torrents_info.return_value = [mock_torrent]

        info_hash = mock_qb_client.find_existing_download(
            name="Test Book [EPUB].epub"
        )

        assert info_hash == "abc123def456"

    def test_find_by_name_and_category(self, mock_qb_client, mock_torrent):
        mock_qb_client.client.torrents_info.return_value = [mock_torrent]

        info_hash = mock_qb_client.find_existing_download(
            name="Test Book [EPUB].epub",
            category="books"
        )

        assert info_hash == "abc123def456"

        # Verify category filter was used
        call_kwargs = mock_qb_client.client.torrents_info.call_args.kwargs
        assert call_kwargs.get('category') == "books"

    def test_find_not_found(self, mock_qb_client):
        mock_qb_client.client.torrents_info.return_value = []

        info_hash = mock_qb_client.find_existing_download(info_hash="notfound")

        assert info_hash is None

    def test_find_name_mismatch(self, mock_qb_client, mock_torrent):
        mock_torrent.name = "Different Book.epub"
        mock_qb_client.client.torrents_info.return_value = [mock_torrent]

        info_hash = mock_qb_client.find_existing_download(
            name="Test Book.epub"
        )

        assert info_hash is None


class TestPathMapping:
    """Test path mapping functionality"""

    def test_map_path_from_container(self, mock_qb_client):
        mock_qb_client.path_mappings = {
            "/downloads": "/host/downloads",
            "/data": "/host/data"
        }

        # Test mapping
        mapped = mock_qb_client._map_path_from_container("/downloads/books/book.epub")
        assert mapped == "/host/downloads/books/book.epub"

        mapped = mock_qb_client._map_path_from_container("/data/ebooks/book.epub")
        assert mapped == "/host/data/ebooks/book.epub"

    def test_map_path_from_container_no_match(self, mock_qb_client):
        mock_qb_client.path_mappings = {
            "/downloads": "/host/downloads"
        }

        # No mapping match - should return original
        mapped = mock_qb_client._map_path_from_container("/other/path/book.epub")
        assert mapped == "/other/path/book.epub"

    def test_map_path_from_container_no_mappings(self, mock_qb_client):
        mock_qb_client.path_mappings = {}

        mapped = mock_qb_client._map_path_from_container("/downloads/book.epub")
        assert mapped == "/downloads/book.epub"

    def test_map_path_to_container(self, mock_qb_client):
        mock_qb_client.path_mappings = {
            "/downloads": "/host/downloads"
        }

        mapped = mock_qb_client._map_path_to_container("/host/downloads/books/book.epub")
        assert mapped == "/downloads/books/book.epub"

    def test_map_path_to_container_no_match(self, mock_qb_client):
        mock_qb_client.path_mappings = {
            "/downloads": "/host/downloads"
        }

        mapped = mock_qb_client._map_path_to_container("/other/host/path/book.epub")
        assert mapped == "/other/host/path/book.epub"


class TestGetClientInfo:
    """Test getting client info"""

    def test_get_client_info(self, mock_qb_client):
        mock_prefs = {
            "download_path": "/downloads",
            "max_active_downloads": 3
        }
        mock_qb_client.client.app.preferences = mock_prefs

        info = mock_qb_client.get_client_info()

        assert info["version"] == "v4.6.0"
        assert info["api_version"] == "2.8.19"
        assert info["preferences"] == mock_prefs

    def test_get_client_info_failure(self, mock_qb_client):
        # Make the version property raise an exception when accessed
        type(mock_qb_client.client.app).version = property(
            fget=Mock(side_effect=Exception("Failed"))
        )

        info = mock_qb_client.get_client_info()

        assert info == {}


class TestStateMapping:
    """Test qBittorrent state to DownloadState mapping"""

    def test_map_all_states(self, mock_qb_client):
        # Test all state mappings
        state_tests = {
            "downloading": DownloadState.DOWNLOADING,
            "stalledDL": DownloadState.DOWNLOADING,
            "metaDL": DownloadState.DOWNLOADING,
            "forcedDL": DownloadState.DOWNLOADING,
            "allocating": DownloadState.DOWNLOADING,

            "uploading": DownloadState.SEEDING,
            "stalledUP": DownloadState.SEEDING,
            "forcedUP": DownloadState.SEEDING,

            "pausedDL": DownloadState.PAUSED,
            "pausedUP": DownloadState.PAUSED,

            "checkingDL": DownloadState.CHECKING,
            "checkingUP": DownloadState.CHECKING,
            "checkingResumeData": DownloadState.CHECKING,

            "error": DownloadState.ERROR,
            "missingFiles": DownloadState.ERROR,

            "queuedDL": DownloadState.QUEUED,
            "queuedUP": DownloadState.SEEDING,
        }

        for qb_state, expected_state in state_tests.items():
            mapped = mock_qb_client._map_state(qb_state)
            assert mapped == expected_state, f"Failed for state: {qb_state}"

    def test_map_unknown_state(self, mock_qb_client):
        # Unknown states should default to QUEUED
        mapped = mock_qb_client._map_state("unknownState")
        assert mapped == DownloadState.QUEUED


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_magnet_link_with_additional_params(self, mock_qb_client):
        magnet = "magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12&dn=Book&tr=http://tracker.example.com"

        mock_qb_client.client.torrents_add.return_value = "Ok."

        info_hash = mock_qb_client.add_torrent(magnet=magnet)

        assert info_hash == "abcdef1234567890abcdef1234567890abcdef12"

    def test_magnet_link_short_hash(self, mock_qb_client):
        # Hash too short (not 40 chars)
        magnet = "magnet:?xt=urn:btih:ABC123&dn=Book"

        mock_qb_client.client.torrents_add.return_value = "Ok."
        mock_qb_client.client.torrents_info.return_value = [Mock(hash="fallback123")]
        mock_qb_client.client.torrents_categories.return_value = {}

        info_hash = mock_qb_client.add_torrent(magnet=magnet)

        # Should fallback to finding torrent
        assert info_hash == "fallback123"

    def test_get_status_files_error(self, mock_qb_client, mock_torrent):
        mock_qb_client.client.torrents_info.return_value = [mock_torrent]
        mock_qb_client.client.torrents_files.side_effect = Exception("Files error")

        status = mock_qb_client.get_download_status("abc123")

        # Should still return status, just without files
        assert status["state"] == DownloadState.DOWNLOADING
        assert status["files"] == []

    def test_content_path_none(self, mock_qb_client, mock_torrent):
        mock_torrent.progress = 1.0
        mock_torrent.content_path = None
        mock_torrent.save_path = "/downloads/books"

        mock_qb_client.client.torrents_info.return_value = [mock_torrent]

        path = mock_qb_client.get_completed_download_path("abc123")

        # Should fallback to save_path
        assert path == "/downloads/books"
