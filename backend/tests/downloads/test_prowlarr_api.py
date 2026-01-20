"""
Unit tests for Prowlarr API client.

Uses mocking to avoid actual API calls.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import requests

from app.downloads.prowlarr.api import ProwlarrClient


@pytest.fixture
def mock_client():
    """Create a ProwlarrClient with mocked session"""
    client = ProwlarrClient(
        base_url="http://prowlarr:9696",
        api_key="test_api_key",
        timeout=30
    )
    return client


class TestProwlarrClientInit:
    """Test client initialization"""

    def test_init_with_trailing_slash(self):
        client = ProwlarrClient("http://prowlarr:9696/", "key")
        assert client.base_url == "http://prowlarr:9696"

    def test_init_sets_headers(self):
        client = ProwlarrClient("http://prowlarr:9696", "my_key")
        assert client.session.headers["X-Api-Key"] == "my_key"
        assert client.session.headers["Accept"] == "application/json"

    def test_init_sets_timeout(self):
        client = ProwlarrClient("http://prowlarr:9696", "key", timeout=60)
        assert client.timeout == 60


class TestTestConnection:
    """Test connection testing"""

    def test_successful_connection(self, mock_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "version": "1.0.0",
            "appName": "Prowlarr"
        }

        with patch.object(mock_client.session, 'get', return_value=mock_response):
            result = mock_client.test_connection()

        assert result is True

    def test_failed_connection_bad_status(self, mock_client):
        mock_response = Mock()
        mock_response.status_code = 401

        with patch.object(mock_client.session, 'get', return_value=mock_response):
            result = mock_client.test_connection()

        assert result is False

    def test_failed_connection_exception(self, mock_client):
        with patch.object(mock_client.session, 'get', side_effect=requests.exceptions.ConnectionError()):
            result = mock_client.test_connection()

        assert result is False


class TestSearch:
    """Test search functionality"""

    def test_basic_search(self, mock_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"title": "Book 1", "size": 1024},
            {"title": "Book 2", "size": 2048},
        ]

        with patch.object(mock_client.session, 'get', return_value=mock_response) as mock_get:
            results = mock_client.search("test query")

        assert len(results) == 2
        assert results[0]["title"] == "Book 1"

        # Verify request parameters
        call_args = mock_get.call_args
        assert "test query" in str(call_args)

    def test_search_with_categories(self, mock_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch.object(mock_client.session, 'get', return_value=mock_response) as mock_get:
            mock_client.search("query", categories=[7000, 7020])

        # Verify categories were sent
        call_kwargs = mock_get.call_args.kwargs
        assert "params" in call_kwargs
        assert call_kwargs["params"]["categories"] == "7000,7020"

    def test_search_with_indexers(self, mock_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch.object(mock_client.session, 'get', return_value=mock_response) as mock_get:
            mock_client.search("query", indexer_ids=[1, 2, 3])

        call_kwargs = mock_get.call_args.kwargs
        assert call_kwargs["params"]["indexerIds"] == "1,2,3"

    def test_search_with_limit_offset(self, mock_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch.object(mock_client.session, 'get', return_value=mock_response) as mock_get:
            mock_client.search("query", limit=50, offset=100)

        call_kwargs = mock_get.call_args.kwargs
        assert call_kwargs["params"]["limit"] == 50
        assert call_kwargs["params"]["offset"] == 100

    def test_search_timeout(self, mock_client):
        with patch.object(
            mock_client.session,
            'get',
            side_effect=requests.exceptions.Timeout()
        ):
            results = mock_client.search("query")

        assert results == []

    def test_search_http_error(self, mock_client):
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()

        with patch.object(mock_client.session, 'get', return_value=mock_response):
            results = mock_client.search("query")

        assert results == []

    def test_search_generic_exception(self, mock_client):
        with patch.object(
            mock_client.session,
            'get',
            side_effect=Exception("Network error")
        ):
            results = mock_client.search("query")

        assert results == []


class TestSearchWithRetry:
    """Test search with retry logic"""

    def test_retry_without_categories_on_no_results(self, mock_client):
        # First call returns empty
        # Second call (without categories) returns results
        mock_response_empty = Mock()
        mock_response_empty.status_code = 200
        mock_response_empty.json.return_value = []

        mock_response_full = Mock()
        mock_response_full.status_code = 200
        mock_response_full.json.return_value = [{"title": "Book"}]

        with patch.object(
            mock_client.session,
            'get',
            side_effect=[mock_response_empty, mock_response_full]
        ):
            results = mock_client.search_with_retry("query", categories=[7000])

        assert len(results) == 1
        assert results[0]["title"] == "Book"

    def test_no_retry_if_results_found(self, mock_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"title": "Book"}]

        with patch.object(
            mock_client.session,
            'get',
            return_value=mock_response
        ) as mock_get:
            results = mock_client.search_with_retry("query", categories=[7000])

        # Should only call once (no retry needed)
        assert mock_get.call_count == 1
        assert len(results) == 1

    def test_no_retry_if_no_categories_specified(self, mock_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch.object(
            mock_client.session,
            'get',
            return_value=mock_response
        ) as mock_get:
            results = mock_client.search_with_retry("query", categories=None)

        # Should only call once (no categories to remove)
        assert mock_get.call_count == 1
        assert len(results) == 0


class TestGetIndexers:
    """Test indexer retrieval"""

    def test_get_indexers_success(self, mock_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 1, "name": "Indexer1", "protocol": "torrent"},
            {"id": 2, "name": "Indexer2", "protocol": "usenet"},
        ]

        with patch.object(mock_client.session, 'get', return_value=mock_response):
            indexers = mock_client.get_indexers()

        assert len(indexers) == 2
        assert indexers[0]["name"] == "Indexer1"

    def test_get_indexers_error(self, mock_client):
        with patch.object(
            mock_client.session,
            'get',
            side_effect=Exception("Error")
        ):
            indexers = mock_client.get_indexers()

        assert indexers == []


class TestGetIndexer:
    """Test single indexer retrieval"""

    def test_get_indexer_success(self, mock_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 1,
            "name": "TestIndexer",
            "protocol": "torrent"
        }

        with patch.object(mock_client.session, 'get', return_value=mock_response):
            indexer = mock_client.get_indexer(1)

        assert indexer is not None
        assert indexer["name"] == "TestIndexer"

    def test_get_indexer_not_found(self, mock_client):
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()

        with patch.object(mock_client.session, 'get', return_value=mock_response):
            indexer = mock_client.get_indexer(999)

        assert indexer is None


class TestGetIndexerStats:
    """Test indexer statistics"""

    def test_get_stats_success(self, mock_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "indexers": [
                {"indexerId": 1, "numberOfQueries": 100},
                {"indexerId": 2, "numberOfQueries": 50},
            ]
        }

        with patch.object(mock_client.session, 'get', return_value=mock_response):
            stats = mock_client.get_indexer_stats()

        assert len(stats) == 2
        assert stats[0]["numberOfQueries"] == 100

    def test_get_stats_error(self, mock_client):
        with patch.object(
            mock_client.session,
            'get',
            side_effect=Exception("Error")
        ):
            stats = mock_client.get_indexer_stats()

        assert stats == []


class TestParseProwlarrResult:
    """Test result parsing"""

    def test_parse_basic_result(self):
        raw_result = {
            "guid": "https://indexer.com/12345",
            "title": "Book Title [EPUB]",
            "indexerId": 1,
            "indexer": "TestIndexer",
            "size": 2048000,
            "downloadUrl": "http://prowlarr/download/12345",
            "protocol": "torrent",
        }

        parsed = ProwlarrClient.parse_prowlarr_result(raw_result)

        assert parsed["guid"] == "https://indexer.com/12345"
        assert parsed["title"] == "Book Title [EPUB]"
        assert parsed["indexer_id"] == 1
        assert parsed["size_bytes"] == 2048000
        assert parsed["protocol"] == "torrent"

    def test_parse_with_seeders(self):
        raw_result = {
            "title": "Book",
            "size": 1000,
            "downloadUrl": "http://test",
            "protocol": "torrent",
            "seeders": 10,
            "leechers": 2,
        }

        parsed = ProwlarrClient.parse_prowlarr_result(raw_result)

        assert parsed["seeders"] == 10
        assert parsed["leechers"] == 2

    def test_parse_with_categories(self):
        raw_result = {
            "title": "Book",
            "size": 1000,
            "downloadUrl": "http://test",
            "protocol": "torrent",
            "categories": [
                {"id": 7000, "name": "Books/Ebook"},
                {"id": 7020, "name": "Books/Foreign"},
            ]
        }

        parsed = ProwlarrClient.parse_prowlarr_result(raw_result)

        assert parsed["category_ids"] == [7000, 7020]

    def test_parse_with_publish_date(self):
        raw_result = {
            "title": "Book",
            "size": 1000,
            "downloadUrl": "http://test",
            "protocol": "torrent",
            "publishDate": "2024-01-15T10:30:00Z",
        }

        parsed = ProwlarrClient.parse_prowlarr_result(raw_result)

        assert parsed["publish_date"] is not None
        assert isinstance(parsed["publish_date"], datetime)
        assert parsed["publish_date"].year == 2024

    def test_parse_invalid_publish_date(self):
        raw_result = {
            "title": "Book",
            "size": 1000,
            "downloadUrl": "http://test",
            "protocol": "torrent",
            "publishDate": "invalid-date",
        }

        parsed = ProwlarrClient.parse_prowlarr_result(raw_result)

        # Should handle gracefully
        assert parsed["publish_date"] is None

    def test_parse_keeps_raw_data(self):
        raw_result = {
            "title": "Book",
            "size": 1000,
            "downloadUrl": "http://test",
            "protocol": "torrent",
            "customField": "customValue",
        }

        parsed = ProwlarrClient.parse_prowlarr_result(raw_result)

        # Should keep original data
        assert parsed["raw"]["customField"] == "customValue"

    def test_parse_missing_fields(self):
        raw_result = {
            "title": "Book",
            # Missing most fields
        }

        parsed = ProwlarrClient.parse_prowlarr_result(raw_result)

        # Should have defaults
        assert parsed["title"] == "Book"
        assert parsed["size_bytes"] == 0
        assert parsed["download_url"] == ""
        assert parsed["seeders"] is None


class TestCategoryConstants:
    """Test category constants"""

    def test_category_ebook(self):
        assert ProwlarrClient.CATEGORY_EBOOK == 7000

    def test_category_audiobook(self):
        assert ProwlarrClient.CATEGORY_AUDIOBOOK == 3030

    def test_protocol_constants(self):
        assert ProwlarrClient.PROTOCOL_TORRENT == "torrent"
        assert ProwlarrClient.PROTOCOL_USENET == "usenet"
