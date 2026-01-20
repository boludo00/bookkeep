"""
Unit tests for NZBGet client.

Tests the NZBGetClient implementation which handles usenet downloads
via the NZBGet JSON-RPC API.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import base64
from typing import Dict, Any

from app.downloads import DownloadState
from app.downloads.clients.nzbget import NZBGetClient


@pytest.fixture
def mock_nzbget_client():
    """Create an NZBGetClient with mocked requests"""
    with patch('app.downloads.clients.nzbget.requests.Session') as mock_session_class:
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        # Mock successful RPC calls by default
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "4.2.0", "id": 1}
        mock_session.post.return_value = mock_response

        client = NZBGetClient(
            host="localhost",
            port=6789,
            username="nzbget",
            password="password",
            category="books"
        )

        yield client


@pytest.fixture
def mock_queue_group():
    """Create a mock NZBGet queue group"""
    return {
        "NZBID": 123,
        "NZBName": "Test Book [EPUB]",
        "Status": "DOWNLOADING",
        "FileSizeMB": 5,
        "RemainingSizeMB": 2,
        "DownloadRate": 1048576,  # 1 MB/s
        "Category": "books",
        "DestDir": "/downloads/books/Test Book [EPUB]",
    }


@pytest.fixture
def mock_history_item():
    """Create a mock NZBGet history item"""
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


class TestNZBGetClientInit:
    """Test client initialization"""

    def test_init_basic(self):
        with patch('app.downloads.clients.nzbget.requests.Session'):
            client = NZBGetClient(
                host="localhost",
                port=6789,
                username="admin",
                password="admin"
            )

            assert client.host == "localhost"
            assert client.port == 6789
            assert client.username == "admin"
            assert client.password == "admin"
            assert client.use_ssl is False
            assert client.category is None

    def test_init_with_ssl(self):
        with patch('app.downloads.clients.nzbget.requests.Session'):
            client = NZBGetClient(
                host="nzbget.local",
                port=6791,
                username="admin",
                password="admin",
                use_ssl=True
            )

            assert client.use_ssl is True
            assert "https://" in client.rpc_url

    def test_init_with_category(self):
        with patch('app.downloads.clients.nzbget.requests.Session'):
            client = NZBGetClient(
                host="localhost",
                port=6789,
                username="admin",
                password="admin",
                category="ebooks"
            )

            assert client.category == "ebooks"

    def test_init_with_path_mappings(self):
        with patch('app.downloads.clients.nzbget.requests.Session'):
            path_mappings = {
                "/downloads": "/host/downloads",
                "/data": "/host/data"
            }

            client = NZBGetClient(
                host="localhost",
                port=6789,
                username="admin",
                password="admin",
                path_mappings=path_mappings
            )

            assert client.path_mappings == path_mappings

    def test_init_without_auth(self):
        with patch('app.downloads.clients.nzbget.requests.Session'):
            client = NZBGetClient(
                host="localhost",
                port=6789
            )

            # Should build URL without auth
            assert "@" not in client.rpc_url or client.username == ""

    def test_rpc_url_with_auth(self):
        with patch('app.downloads.clients.nzbget.requests.Session'):
            client = NZBGetClient(
                host="localhost",
                port=6789,
                username="user",
                password="pass"
            )

            assert "user:pass@" in client.rpc_url
            assert "http://user:pass@localhost:6789/jsonrpc" == client.rpc_url


class TestRPCCall:
    """Test RPC call functionality"""

    def test_rpc_call_success(self, mock_nzbget_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "test_result", "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        result = mock_nzbget_client._rpc_call("test_method", ["param1", "param2"])

        assert result == "test_result"

        # Verify request
        call_args = mock_nzbget_client.session.post.call_args
        payload = call_args.kwargs['json']
        assert payload['method'] == "test_method"
        assert payload['params'] == ["param1", "param2"]

    def test_rpc_call_error_response(self, mock_nzbget_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "error": {"code": -1, "message": "Test error"},
            "id": 1
        }
        mock_nzbget_client.session.post.return_value = mock_response

        result = mock_nzbget_client._rpc_call("test_method")

        assert result is None

    def test_rpc_call_http_error(self, mock_nzbget_client):
        import requests
        mock_nzbget_client.session.post.side_effect = requests.exceptions.RequestException("Connection failed")

        result = mock_nzbget_client._rpc_call("test_method")

        assert result is None

    def test_rpc_call_timeout(self, mock_nzbget_client):
        import requests
        mock_nzbget_client.session.post.side_effect = requests.exceptions.Timeout()

        result = mock_nzbget_client._rpc_call("test_method")

        assert result is None


class TestTestConnection:
    """Test connection testing"""

    def test_successful_connection(self, mock_nzbget_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "21.0", "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        result = mock_nzbget_client.test_connection()

        assert result is True

    def test_failed_connection(self, mock_nzbget_client):
        mock_nzbget_client.session.post.side_effect = Exception("Connection failed")

        result = mock_nzbget_client.test_connection()

        assert result is False


class TestAddNZB:
    """Test adding NZBs"""

    def test_add_nzb_by_url(self, mock_nzbget_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": 123, "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        nzb_id = mock_nzbget_client.add_nzb(
            url="http://example.com/book.nzb"
        )

        assert nzb_id == 123

        # Verify RPC call
        call_args = mock_nzbget_client.session.post.call_args
        payload = call_args.kwargs['json']
        assert payload['method'] == "append"
        assert "http://example.com/book.nzb" in payload['params']

    def test_add_nzb_by_file(self, mock_nzbget_client):
        nzb_content = b"<?xml version='1.0'?><nzb>test</nzb>"
        nzb_b64 = base64.b64encode(nzb_content).decode('utf-8')

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": 456, "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        nzb_id = mock_nzbget_client.add_nzb(
            nzb_file=nzb_content,
            nzb_name="test.nzb"
        )

        assert nzb_id == 456

        # Verify base64 encoding
        call_args = mock_nzbget_client.session.post.call_args
        payload = call_args.kwargs['json']
        assert nzb_b64 in payload['params']

    def test_add_nzb_with_category(self, mock_nzbget_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": 789, "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        mock_nzbget_client.add_nzb(
            url="http://example.com/book.nzb",
            category="ebooks"
        )

        # Verify category in params
        call_args = mock_nzbget_client.session.post.call_args
        payload = call_args.kwargs['json']
        assert "ebooks" in payload['params']

    def test_add_nzb_with_priority(self, mock_nzbget_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": 999, "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        mock_nzbget_client.add_nzb(
            url="http://example.com/book.nzb",
            priority=50
        )

        # Verify priority in params
        call_args = mock_nzbget_client.session.post.call_args
        payload = call_args.kwargs['json']
        assert 50 in payload['params']

    def test_add_nzb_no_source(self, mock_nzbget_client):
        with pytest.raises(ValueError, match="Must provide url or nzb_file"):
            mock_nzbget_client.add_nzb()

    def test_add_nzb_file_without_name(self, mock_nzbget_client):
        with pytest.raises(ValueError, match="nzb_name required"):
            mock_nzbget_client.add_nzb(nzb_file=b"content")

    def test_add_nzb_failure(self, mock_nzbget_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": 0, "id": 1}  # 0 = failure
        mock_nzbget_client.session.post.return_value = mock_response

        nzb_id = mock_nzbget_client.add_nzb(
            url="http://example.com/book.nzb"
        )

        assert nzb_id is None


class TestGetDownloadStatus:
    """Test getting download status"""

    def test_get_status_downloading(self, mock_nzbget_client, mock_queue_group):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [mock_queue_group], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        status = mock_nzbget_client.get_download_status(123)

        assert status["state"] == DownloadState.DOWNLOADING
        assert status["progress"] == 60.0  # (5-2)/5 * 100
        assert status["download_speed"] == 1048576
        assert status["name"] == "Test Book [EPUB]"

    def test_get_status_complete(self, mock_nzbget_client, mock_history_item):
        # Empty queue
        mock_response_queue = Mock()
        mock_response_queue.status_code = 200
        mock_response_queue.json.return_value = {"result": [], "id": 1}

        # History with completed item
        mock_response_history = Mock()
        mock_response_history.status_code = 200
        mock_response_history.json.return_value = {"result": [mock_history_item], "id": 1}

        mock_nzbget_client.session.post.side_effect = [
            mock_response_queue,  # listgroups
            mock_response_history,  # history
        ]

        status = mock_nzbget_client.get_download_status(456)

        assert status["state"] == DownloadState.COMPLETE
        assert status["progress"] == 100.0

    def test_get_status_paused(self, mock_nzbget_client, mock_queue_group):
        mock_queue_group["Status"] = "PAUSED"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [mock_queue_group], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        status = mock_nzbget_client.get_download_status(123)

        assert status["state"] == DownloadState.PAUSED

    def test_get_status_processing(self, mock_nzbget_client, mock_queue_group):
        mock_queue_group["Status"] = "UNPACKING"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [mock_queue_group], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        status = mock_nzbget_client.get_download_status(123)

        assert status["state"] == DownloadState.PROCESSING

    def test_get_status_failed(self, mock_nzbget_client, mock_history_item):
        mock_history_item["Status"] = "FAILURE"

        mock_response_queue = Mock()
        mock_response_queue.status_code = 200
        mock_response_queue.json.return_value = {"result": [], "id": 1}

        mock_response_history = Mock()
        mock_response_history.status_code = 200
        mock_response_history.json.return_value = {"result": [mock_history_item], "id": 1}

        mock_nzbget_client.session.post.side_effect = [
            mock_response_queue,
            mock_response_history,
        ]

        status = mock_nzbget_client.get_download_status(456)

        assert status["state"] == DownloadState.ERROR

    def test_get_status_not_found(self, mock_nzbget_client):
        mock_response_queue = Mock()
        mock_response_queue.status_code = 200
        mock_response_queue.json.return_value = {"result": [], "id": 1}

        mock_response_history = Mock()
        mock_response_history.status_code = 200
        mock_response_history.json.return_value = {"result": [], "id": 1}

        mock_nzbget_client.session.post.side_effect = [
            mock_response_queue,
            mock_response_history,
        ]

        status = mock_nzbget_client.get_download_status(999)

        assert status["state"] == DownloadState.ERROR
        assert "not found" in status["message"].lower()

    def test_get_status_with_path_mapping(self, mock_nzbget_client, mock_queue_group):
        mock_nzbget_client.path_mappings = {
            "/downloads": "/host/downloads"
        }

        mock_queue_group["DestDir"] = "/downloads/books/book"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [mock_queue_group], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        status = mock_nzbget_client.get_download_status(123)

        assert status["dest_dir"] == "/host/downloads/books/book"


class TestGetCompletedDownloadPath:
    """Test getting completed download path"""

    def test_get_completed_path(self, mock_nzbget_client, mock_history_item):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [mock_history_item], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        path = mock_nzbget_client.get_completed_download_path(456)

        assert path == "/downloads/completed/Completed Book [EPUB]"

    def test_get_completed_path_incomplete(self, mock_nzbget_client, mock_history_item):
        mock_history_item["Status"] = "DOWNLOADING"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [mock_history_item], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        path = mock_nzbget_client.get_completed_download_path(456)

        assert path is None

    def test_get_completed_path_failed(self, mock_nzbget_client, mock_history_item):
        mock_history_item["Status"] = "FAILURE"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [mock_history_item], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        path = mock_nzbget_client.get_completed_download_path(456)

        assert path is None

    def test_get_completed_path_not_found(self, mock_nzbget_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        path = mock_nzbget_client.get_completed_download_path(999)

        assert path is None

    def test_get_completed_path_with_mapping(self, mock_nzbget_client, mock_history_item):
        mock_nzbget_client.path_mappings = {
            "/downloads": "/host/downloads"
        }

        mock_history_item["DestDir"] = "/downloads/completed/book"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [mock_history_item], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        path = mock_nzbget_client.get_completed_download_path(456)

        assert path == "/host/downloads/completed/book"


class TestRemoveNZB:
    """Test removing NZBs"""

    def test_remove_nzb_success(self, mock_nzbget_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": True, "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        result = mock_nzbget_client.remove_nzb(123, delete_files=False)

        assert result is True

        # Verify RPC call
        call_args = mock_nzbget_client.session.post.call_args
        payload = call_args.kwargs['json']
        assert payload['method'] == "editqueue"
        assert "GroupDelete" in payload['params']

    def test_remove_nzb_delete_files(self, mock_nzbget_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": True, "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        result = mock_nzbget_client.remove_nzb(123, delete_files=True)

        assert result is True

        # Should call editqueue twice (GroupDelete + HistoryDelete)
        assert mock_nzbget_client.session.post.call_count == 2

    def test_remove_nzb_failure(self, mock_nzbget_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": False, "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        result = mock_nzbget_client.remove_nzb(123)

        assert result is False


class TestPauseResume:
    """Test pausing and resuming NZBs"""

    def test_pause_nzb(self, mock_nzbget_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": True, "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        result = mock_nzbget_client.pause_nzb(123)

        assert result is True

        # Verify RPC call
        call_args = mock_nzbget_client.session.post.call_args
        payload = call_args.kwargs['json']
        assert "GroupPause" in payload['params']

    def test_pause_nzb_failure(self, mock_nzbget_client):
        mock_nzbget_client.session.post.side_effect = Exception("Pause failed")

        result = mock_nzbget_client.pause_nzb(123)

        assert result is False

    def test_resume_nzb(self, mock_nzbget_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": True, "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        result = mock_nzbget_client.resume_nzb(123)

        assert result is True

        # Verify RPC call
        call_args = mock_nzbget_client.session.post.call_args
        payload = call_args.kwargs['json']
        assert "GroupResume" in payload['params']

    def test_resume_nzb_failure(self, mock_nzbget_client):
        mock_nzbget_client.session.post.side_effect = Exception("Resume failed")

        result = mock_nzbget_client.resume_nzb(123)

        assert result is False


class TestFindExistingDownload:
    """Test finding existing downloads"""

    def test_find_by_id(self, mock_nzbget_client, mock_queue_group):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [mock_queue_group], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        nzb_id = mock_nzbget_client.find_existing_download(nzb_id=123)

        assert nzb_id == 123

    def test_find_by_name_in_queue(self, mock_nzbget_client, mock_queue_group):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [mock_queue_group], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        nzb_id = mock_nzbget_client.find_existing_download(
            name="Test Book [EPUB]"
        )

        assert nzb_id == 123

    def test_find_by_name_in_history(self, mock_nzbget_client, mock_history_item):
        mock_response_queue = Mock()
        mock_response_queue.status_code = 200
        mock_response_queue.json.return_value = {"result": [], "id": 1}

        mock_response_history = Mock()
        mock_response_history.status_code = 200
        mock_response_history.json.return_value = {"result": [mock_history_item], "id": 1}

        mock_nzbget_client.session.post.side_effect = [
            mock_response_queue,
            mock_response_history,
        ]

        nzb_id = mock_nzbget_client.find_existing_download(
            name="Completed Book [EPUB]"
        )

        assert nzb_id == 456

    def test_find_by_name_and_category(self, mock_nzbget_client, mock_queue_group):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [mock_queue_group], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        nzb_id = mock_nzbget_client.find_existing_download(
            name="Test Book [EPUB]",
            category="books"
        )

        assert nzb_id == 123

    def test_find_category_mismatch(self, mock_nzbget_client, mock_queue_group):
        mock_queue_group["Category"] = "other"

        mock_response_queue = Mock()
        mock_response_queue.status_code = 200
        mock_response_queue.json.return_value = {"result": [mock_queue_group], "id": 1}

        mock_response_history = Mock()
        mock_response_history.status_code = 200
        mock_response_history.json.return_value = {"result": [], "id": 1}

        mock_nzbget_client.session.post.side_effect = [
            mock_response_queue,
            mock_response_history,
        ]

        nzb_id = mock_nzbget_client.find_existing_download(
            name="Test Book [EPUB]",
            category="books"
        )

        assert nzb_id is None

    def test_find_not_found(self, mock_nzbget_client):
        mock_response_queue = Mock()
        mock_response_queue.status_code = 200
        mock_response_queue.json.return_value = {"result": [], "id": 1}

        mock_response_history = Mock()
        mock_response_history.status_code = 200
        mock_response_history.json.return_value = {"result": [], "id": 1}

        mock_nzbget_client.session.post.side_effect = [
            mock_response_queue,
            mock_response_history,
        ]

        nzb_id = mock_nzbget_client.find_existing_download(name="Nonexistent")

        assert nzb_id is None


class TestPathMapping:
    """Test path mapping functionality"""

    def test_map_path_from_container(self, mock_nzbget_client):
        mock_nzbget_client.path_mappings = {
            "/downloads": "/host/downloads",
            "/data": "/host/data"
        }

        mapped = mock_nzbget_client._map_path_from_container("/downloads/books/book")
        assert mapped == "/host/downloads/books/book"

        mapped = mock_nzbget_client._map_path_from_container("/data/ebooks/book")
        assert mapped == "/host/data/ebooks/book"

    def test_map_path_from_container_no_match(self, mock_nzbget_client):
        mock_nzbget_client.path_mappings = {
            "/downloads": "/host/downloads"
        }

        mapped = mock_nzbget_client._map_path_from_container("/other/path/book")
        assert mapped == "/other/path/book"

    def test_map_path_from_container_empty(self, mock_nzbget_client):
        mock_nzbget_client.path_mappings = {"/downloads": "/host/downloads"}

        mapped = mock_nzbget_client._map_path_from_container("")
        assert mapped == ""

    def test_map_path_to_container(self, mock_nzbget_client):
        mock_nzbget_client.path_mappings = {
            "/downloads": "/host/downloads"
        }

        mapped = mock_nzbget_client._map_path_to_container("/host/downloads/books/book")
        assert mapped == "/downloads/books/book"


class TestGetClientInfo:
    """Test getting client info"""

    def test_get_client_info(self, mock_nzbget_client):
        mock_response_version = Mock()
        mock_response_version.status_code = 200
        mock_response_version.json.return_value = {"result": "21.1", "id": 1}

        mock_response_config = Mock()
        mock_response_config.status_code = 200
        mock_response_config.json.return_value = {
            "result": [
                {"Name": "MainDir", "Value": "/downloads"},
                {"Name": "ScriptDir", "Value": "/scripts"},
            ],
            "id": 1
        }

        mock_nzbget_client.session.post.side_effect = [
            mock_response_version,
            mock_response_config,
        ]

        info = mock_nzbget_client.get_client_info()

        assert info["version"] == "21.1"
        assert info["config"]["MainDir"] == "/downloads"
        assert info["config"]["ScriptDir"] == "/scripts"

    def test_get_client_info_failure(self, mock_nzbget_client):
        mock_nzbget_client.session.post.side_effect = Exception("Failed")

        info = mock_nzbget_client.get_client_info()

        assert info == {}


class TestGetQueueAndHistory:
    """Test getting queue and history"""

    def test_get_queue(self, mock_nzbget_client, mock_queue_group):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [mock_queue_group], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        queue = mock_nzbget_client.get_queue()

        assert len(queue) == 1
        assert queue[0]["NZBID"] == 123

    def test_get_history(self, mock_nzbget_client, mock_history_item):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [mock_history_item], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        history = mock_nzbget_client.get_history()

        assert len(history) == 1
        assert history[0]["NZBID"] == 456

    def test_get_history_with_hidden(self, mock_nzbget_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        mock_nzbget_client.get_history(hidden=True)

        # Verify hidden parameter was passed
        call_args = mock_nzbget_client.session.post.call_args
        payload = call_args.kwargs['json']
        assert payload['params'] == [True]


class TestStatusMapping:
    """Test NZBGet status to DownloadState mapping"""

    def test_map_all_statuses(self, mock_nzbget_client):
        status_tests = {
            "DOWNLOADING": DownloadState.DOWNLOADING,
            "PAUSED": DownloadState.PAUSED,
            "QUEUED": DownloadState.QUEUED,
            "FETCHING": DownloadState.DOWNLOADING,
            "PP_QUEUED": DownloadState.PROCESSING,
            "LOADING_PARS": DownloadState.PROCESSING,
            "VERIFYING_SOURCES": DownloadState.CHECKING,
            "REPAIRING": DownloadState.PROCESSING,
            "VERIFYING_REPAIRED": DownloadState.CHECKING,
            "RENAMING": DownloadState.PROCESSING,
            "UNPACKING": DownloadState.PROCESSING,
            "MOVING": DownloadState.PROCESSING,
            "EXECUTING_SCRIPT": DownloadState.PROCESSING,
            "PP_FINISHED": DownloadState.COMPLETE,
        }

        for nzb_status, expected_state in status_tests.items():
            mapped = mock_nzbget_client._map_status_to_state(nzb_status)
            assert mapped == expected_state, f"Failed for status: {nzb_status}"

    def test_map_unknown_status(self, mock_nzbget_client):
        mapped = mock_nzbget_client._map_status_to_state("UNKNOWN_STATUS")
        assert mapped == DownloadState.QUEUED


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_progress_calculation_zero_size(self, mock_nzbget_client, mock_queue_group):
        mock_queue_group["FileSizeMB"] = 0
        mock_queue_group["RemainingSizeMB"] = 0

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [mock_queue_group], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        status = mock_nzbget_client.get_download_status(123)

        assert status["progress"] == 0.0

    def test_history_item_unpack_none(self, mock_nzbget_client, mock_history_item):
        mock_history_item["UnpackStatus"] = "NONE"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [mock_history_item], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        path = mock_nzbget_client.get_completed_download_path(456)

        # NONE is acceptable (no unpacking needed)
        assert path is not None

    def test_find_with_lastid_match(self, mock_nzbget_client, mock_queue_group):
        # Some groups use LastID instead of NZBID
        mock_queue_group["LastID"] = 999
        del mock_queue_group["NZBID"]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [mock_queue_group], "id": 1}
        mock_nzbget_client.session.post.return_value = mock_response

        status = mock_nzbget_client.get_download_status(999)

        assert status["state"] == DownloadState.DOWNLOADING
