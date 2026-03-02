"""
Unit tests for Prowlarr source plugin.

Tests the ProwlarrSource implementation which integrates with Prowlarr API
to search for book releases and convert them to standardized Release objects.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from typing import List

from app.downloads import Release
from app.downloads.prowlarr.source import ProwlarrSource
from app.downloads.prowlarr.api import ProwlarrClient


@pytest.fixture
def mock_prowlarr_source():
    """Create a ProwlarrSource with mocked client"""
    with patch.dict('os.environ', {
        'PROWLARR_URL': 'http://test-prowlarr:9696',
        'PROWLARR_API_KEY': 'test_key'
    }):
        source = ProwlarrSource()
        source.client = Mock(spec=ProwlarrClient)
        return source


class TestProwlarrSourceInit:
    """Test source initialization"""

    def test_init_with_env_vars(self):
        with patch.dict('os.environ', {
            'PROWLARR_URL': 'http://prowlarr-env:9696',
            'PROWLARR_API_KEY': 'env_key'
        }):
            source = ProwlarrSource()
            assert source.client.base_url == 'http://prowlarr-env:9696'
            assert source.client.api_key == 'env_key'

    def test_init_with_explicit_params(self):
        source = ProwlarrSource(
            base_url='http://custom:9696',
            api_key='custom_key',
            timeout=60
        )
        assert source.client.base_url == 'http://custom:9696'
        assert source.client.api_key == 'custom_key'
        assert source.client.timeout == 60

    def test_init_defaults(self):
        with patch.dict('os.environ', {}, clear=True):
            source = ProwlarrSource()
            assert source.client.base_url == 'http://prowlarr:9696'
            assert source.client.api_key == ''

    def test_name_property(self):
        with patch.dict('os.environ', {}):
            source = ProwlarrSource()
            assert source.name == 'prowlarr'


class TestTestConnection:
    """Test connection testing"""

    def test_successful_connection(self, mock_prowlarr_source):
        mock_prowlarr_source.client.test_connection.return_value = True

        result = mock_prowlarr_source.test_connection()

        assert result is True
        mock_prowlarr_source.client.test_connection.assert_called_once()

    def test_failed_connection(self, mock_prowlarr_source):
        mock_prowlarr_source.client.test_connection.return_value = False

        result = mock_prowlarr_source.test_connection()

        assert result is False


class TestSearch:
    """Test search functionality"""

    def test_search_ebook_basic(self, mock_prowlarr_source):
        # Mock search results - include author name in title for author validation
        mock_prowlarr_source.client.search_with_retry.return_value = [
            {
                "title": "Test Book - Test Author [EPUB]",
                "downloadUrl": "http://download/1",
                "size": 2048000,
                "protocol": "torrent",
                "seeders": 10,
                "categories": [{"id": 7000, "name": "Books/Ebook"}]
            }
        ]

        results = mock_prowlarr_source.search(
            title="Test Book",
            author="Test Author",
            format_type="ebook"
        )

        # Verify search was called with ebook category (may be called multiple times for query variants)
        mock_prowlarr_source.client.search_with_retry.assert_called()
        call_args = mock_prowlarr_source.client.search_with_retry.call_args
        assert ProwlarrClient.CATEGORY_EBOOK in call_args.kwargs['categories']

        # Verify results
        assert len(results) == 1
        assert isinstance(results[0], Release)
        assert results[0].source == "prowlarr"
        assert results[0].protocol == "torrent"

    def test_search_audiobook_basic(self, mock_prowlarr_source):
        mock_prowlarr_source.client.search_with_retry.return_value = [
            {
                "title": "Test Book.m4b",
                "downloadUrl": "http://download/1",
                "size": 200000000,
                "protocol": "torrent",
                "seeders": 5,
                "categories": [{"id": 3030, "name": "Audio/Audiobook"}]
            }
        ]

        results = mock_prowlarr_source.search(
            title="Test Book",
            format_type="audiobook"
        )

        # Verify search was called with audiobook category
        call_args = mock_prowlarr_source.client.search_with_retry.call_args
        assert ProwlarrClient.CATEGORY_AUDIOBOOK in call_args.kwargs['categories']

        # Verify results
        assert len(results) == 1
        assert results[0].metadata.get("is_audiobook") is True

    def test_search_with_isbn(self, mock_prowlarr_source):
        mock_prowlarr_source.client.search_with_retry.return_value = []

        mock_prowlarr_source.search(
            title="Test Book",
            isbn="1234567890",
            format_type="ebook"
        )

        # ISBN should be first query
        call_args = mock_prowlarr_source.client.search_with_retry.call_args
        # The function builds queries and tries them in order
        mock_prowlarr_source.client.search_with_retry.assert_called()

    def test_search_no_results(self, mock_prowlarr_source):
        mock_prowlarr_source.client.search_with_retry.return_value = []

        results = mock_prowlarr_source.search(
            title="Nonexistent Book",
            format_type="ebook"
        )

        assert results == []

    def test_search_tries_multiple_queries_and_deduplicates(self, mock_prowlarr_source):
        # Multiple queries may return results, but duplicates should be removed
        mock_prowlarr_source.client.search_with_retry.return_value = [
            {
                "title": "Test Book - Author [EPUB]",
                "downloadUrl": "http://download/1",
                "size": 2048000,
                "protocol": "torrent",
                "categories": []
            }
        ]

        results = mock_prowlarr_source.search(
            title="Test Book",
            author="Author",
            format_type="ebook"
        )

        # Should try multiple query variants (up to 4)
        assert mock_prowlarr_source.client.search_with_retry.call_count >= 1
        # But results should be deduplicated by URL
        assert len(results) == 1

    def test_search_tries_multiple_queries_if_needed(self, mock_prowlarr_source):
        # First query returns nothing, second query returns results
        mock_prowlarr_source.client.search_with_retry.side_effect = [
            [],  # First query (ISBN or first variant)
            [    # Second query
                {
                    "title": "Test Book [EPUB]",
                    "downloadUrl": "http://download/1",
                    "size": 2048000,
                    "protocol": "torrent",
                    "categories": []
                }
            ]
        ]

        results = mock_prowlarr_source.search(
            title="Test Book",
            isbn="1234567890",
            format_type="ebook"
        )

        # Should have tried multiple queries
        assert mock_prowlarr_source.client.search_with_retry.call_count == 2
        assert len(results) == 1


class TestConvertToRelease:
    """Test conversion from Prowlarr results to Release objects"""

    def test_convert_ebook_release(self, mock_prowlarr_source):
        prowlarr_result = {
            "guid": "https://indexer.com/12345",
            "title": "Great Book [EPUB]",
            "indexerId": 1,
            "indexer": "TestIndexer",
            "size": 5242880,  # 5 MB
            "downloadUrl": "http://prowlarr/download/12345",
            "protocol": "torrent",
            "seeders": 10,
            "leechers": 2,
            "categories": [{"id": 7000, "name": "Books/Ebook"}],
            "publishDate": "2024-01-15T10:30:00Z",
        }

        release = mock_prowlarr_source._convert_to_release(prowlarr_result, "ebook")

        assert release is not None
        assert release.source == "prowlarr"
        assert release.title == "Great Book [EPUB]"
        assert release.download_url == "http://prowlarr/download/12345"
        assert release.protocol == "torrent"
        assert release.size_bytes == 5242880
        assert release.seeders == 10
        assert release.format == "epub"
        assert release.metadata.get("is_audiobook") is False
        assert release.quality_score > 0

    def test_convert_audiobook_release(self, mock_prowlarr_source):
        prowlarr_result = {
            "title": "Great Audiobook.m4b",
            "size": 200000000,  # 200 MB
            "downloadUrl": "http://prowlarr/download/67890",
            "protocol": "torrent",
            "seeders": 5,
            "categories": [{"id": 3030, "name": "Audio/Audiobook"}],
        }

        release = mock_prowlarr_source._convert_to_release(prowlarr_result, "audiobook")

        assert release is not None
        assert release.format == "m4b"
        assert release.metadata.get("is_audiobook") is True

    def test_convert_filters_ebook_when_searching_audiobook(self, mock_prowlarr_source):
        prowlarr_result = {
            "title": "Book [EPUB]",
            "downloadUrl": "http://download/1",
            "size": 2048000,
            "protocol": "torrent",
            "categories": [{"id": 7000, "name": "Books/Ebook"}],
        }

        # Should return None when ebook found but searching for audiobook
        release = mock_prowlarr_source._convert_to_release(prowlarr_result, "audiobook")

        assert release is None

    def test_convert_filters_audiobook_when_searching_ebook(self, mock_prowlarr_source):
        prowlarr_result = {
            "title": "Book.m4b",
            "downloadUrl": "http://download/1",
            "size": 200000000,
            "protocol": "torrent",
            "categories": [{"id": 3030, "name": "Audio/Audiobook"}],
        }

        # Should return None when audiobook found but searching for ebook
        release = mock_prowlarr_source._convert_to_release(prowlarr_result, "ebook")

        assert release is None

    def test_convert_missing_title(self, mock_prowlarr_source):
        prowlarr_result = {
            "title": "",
            "downloadUrl": "http://download/1",
            "size": 2048000,
        }

        release = mock_prowlarr_source._convert_to_release(prowlarr_result, "ebook")

        assert release is None

    def test_convert_missing_download_url(self, mock_prowlarr_source):
        prowlarr_result = {
            "title": "Book Title",
            "downloadUrl": "",
            "size": 2048000,
        }

        release = mock_prowlarr_source._convert_to_release(prowlarr_result, "ebook")

        assert release is None

    def test_convert_extracts_language(self, mock_prowlarr_source):
        prowlarr_result = {
            "title": "Book Title [en] [EPUB]",
            "downloadUrl": "http://download/1",
            "size": 2048000,
            "protocol": "torrent",
            "categories": [],
        }

        release = mock_prowlarr_source._convert_to_release(prowlarr_result, "ebook")

        assert release is not None
        assert release.language == "en"

    def test_convert_includes_metadata(self, mock_prowlarr_source):
        prowlarr_result = {
            "guid": "https://indexer.com/12345",
            "title": "Book [EPUB]",
            "indexerId": 1,
            "indexer": "TestIndexer",
            "size": 2048000,
            "downloadUrl": "http://download/1",
            "protocol": "torrent",
            "seeders": 10,
            "categories": [{"id": 7000, "name": "Books/Ebook"}],
        }

        release = mock_prowlarr_source._convert_to_release(prowlarr_result, "ebook")

        assert release is not None
        assert "indexer" in release.metadata
        assert "category_ids" in release.metadata
        assert 7000 in release.metadata["category_ids"]


class TestSearchByISBN:
    """Test ISBN-specific search"""

    def test_search_by_isbn(self, mock_prowlarr_source):
        mock_prowlarr_source.client.search_with_retry.return_value = [
            {
                "title": "Book by ISBN [EPUB]",
                "downloadUrl": "http://download/1",
                "size": 2048000,
                "protocol": "torrent",
                "categories": [],
            }
        ]

        results = mock_prowlarr_source.search_by_isbn("1234567890", format_type="ebook")

        assert len(results) == 1
        mock_prowlarr_source.client.search_with_retry.assert_called()

    def test_search_by_isbn_audiobook(self, mock_prowlarr_source):
        mock_prowlarr_source.client.search_with_retry.return_value = []

        results = mock_prowlarr_source.search_by_isbn("1234567890", format_type="audiobook")

        # Verify audiobook category was used
        call_args = mock_prowlarr_source.client.search_with_retry.call_args
        assert ProwlarrClient.CATEGORY_AUDIOBOOK in call_args.kwargs['categories']


class TestGetIndexers:
    """Test indexer retrieval"""

    def test_get_indexers(self, mock_prowlarr_source):
        mock_prowlarr_source.client.get_indexers.return_value = [
            {"id": 1, "name": "Indexer1", "protocol": "torrent"},
            {"id": 2, "name": "Indexer2", "protocol": "usenet"},
        ]

        indexers = mock_prowlarr_source.get_indexers()

        assert len(indexers) == 2
        assert indexers[0]["name"] == "Indexer1"
        mock_prowlarr_source.client.get_indexers.assert_called_once()


class TestQualitySorting:
    """Test that releases are sorted by quality score"""

    def test_releases_sorted_by_quality(self, mock_prowlarr_source):
        # Return releases with different quality indicators
        mock_prowlarr_source.client.search_with_retry.return_value = [
            {
                "title": "Author - The Great Gatsby.pdf",
                "downloadUrl": "http://download/1",
                "size": 100000,  # Very small
                "protocol": "torrent",
                "seeders": 1,
                "categories": [],
            },
            {
                "title": "Author - The Great Gatsby [EPUB]",
                "downloadUrl": "http://download/2",
                "size": 5242880,  # 5 MB - good size
                "protocol": "torrent",
                "seeders": 50,
                "categories": [],
            },
            {
                "title": "Author - The Great Gatsby [MOBI]",
                "downloadUrl": "http://download/3",
                "size": 3145728,  # 3 MB
                "protocol": "torrent",
                "seeders": 10,
                "categories": [],
            },
        ]

        results = mock_prowlarr_source.search(
            title="The Great Gatsby",
            format_type="ebook"
        )

        # Should be sorted by quality score (highest first)
        assert len(results) == 3
        assert results[0].quality_score >= results[1].quality_score
        assert results[1].quality_score >= results[2].quality_score

        # EPUB should rank highest (preferred format, good size, many seeders)
        assert results[0].format == "epub"


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_search_with_none_values(self, mock_prowlarr_source):
        mock_prowlarr_source.client.search_with_retry.return_value = []

        results = mock_prowlarr_source.search(
            title="Book",
            author=None,
            isbn=None,
            format_type="ebook"
        )

        assert results == []
        mock_prowlarr_source.client.search_with_retry.assert_called()

    def test_search_with_empty_string(self, mock_prowlarr_source):
        mock_prowlarr_source.client.search_with_retry.return_value = []

        results = mock_prowlarr_source.search(
            title="",
            format_type="ebook"
        )

        assert results == []

    def test_convert_with_malformed_categories(self, mock_prowlarr_source):
        prowlarr_result = {
            "title": "Book [EPUB]",
            "downloadUrl": "http://download/1",
            "size": 2048000,
            "protocol": "torrent",
            "categories": ["not_a_dict", {"id": 7000}],  # Mixed types
        }

        release = mock_prowlarr_source._convert_to_release(prowlarr_result, "ebook")

        # Should handle gracefully
        assert release is not None
        assert 7000 in release.metadata["category_ids"]

    def test_convert_with_unknown_protocol(self, mock_prowlarr_source):
        prowlarr_result = {
            "title": "Book [EPUB]",
            "downloadUrl": "http://download/1",
            "size": 2048000,
            "protocol": "unknown_protocol",
            "categories": [],
        }

        release = mock_prowlarr_source._convert_to_release(prowlarr_result, "ebook")

        # Should still create release with unknown protocol
        assert release is not None
        assert release.protocol == "unknown_protocol"


class TestIntegrationScenarios:
    """Test realistic integration scenarios"""

    def test_complete_ebook_search_flow(self, mock_prowlarr_source):
        """Simulate a complete ebook search"""
        # Include author name (Fitzgerald) in titles for author validation
        mock_prowlarr_source.client.search_with_retry.return_value = [
            {
                "guid": "https://indexer.com/1",
                "title": "The Great Gatsby - Fitzgerald [EPUB]",
                "indexerId": 1,
                "indexer": "TestIndexer",
                "size": 1048576,  # 1 MB
                "downloadUrl": "http://prowlarr/download/1",
                "protocol": "torrent",
                "seeders": 25,
                "leechers": 3,
                "categories": [{"id": 7000, "name": "Books/Ebook"}],
                "publishDate": "2024-01-15T10:30:00Z",
            },
            {
                "guid": "https://indexer.com/2",
                "title": "The Great Gatsby - Fitzgerald.mobi",
                "indexerId": 1,
                "indexer": "TestIndexer",
                "size": 900000,
                "downloadUrl": "http://prowlarr/download/2",
                "protocol": "torrent",
                "seeders": 15,
                "categories": [{"id": 7000, "name": "Books/Ebook"}],
            },
        ]

        results = mock_prowlarr_source.search(
            title="The Great Gatsby",
            author="F. Scott Fitzgerald",
            format_type="ebook"
        )

        # Should get both results
        assert len(results) == 2

        # All should be Release objects
        assert all(isinstance(r, Release) for r in results)

        # All should be from prowlarr
        assert all(r.source == "prowlarr" for r in results)

        # Should be sorted by quality
        assert results[0].quality_score >= results[1].quality_score

        # EPUB should rank higher (preferred format)
        assert results[0].format == "epub"

    def test_complete_audiobook_search_flow(self, mock_prowlarr_source):
        """Simulate a complete audiobook search"""
        # Include author name (Weir) in title for author validation
        mock_prowlarr_source.client.search_with_retry.return_value = [
            {
                "title": "Project Hail Mary - Andy Weir.m4b",
                "size": 524288000,  # 500 MB
                "downloadUrl": "http://prowlarr/download/1",
                "protocol": "torrent",
                "seeders": 30,
                "categories": [{"id": 3030, "name": "Audio/Audiobook"}],
            }
        ]

        results = mock_prowlarr_source.search(
            title="Project Hail Mary",
            author="Andy Weir",
            format_type="audiobook"
        )

        assert len(results) == 1
        assert results[0].format == "m4b"
        assert results[0].metadata["is_audiobook"] is True
        assert results[0].size_bytes == 524288000


class TestTitleMatches:
    """Test title matching logic for release filtering"""

    # --- Short title tests (1-2 significant words) ---

    def test_short_title_rejects_false_positive(self, mock_prowlarr_source):
        """'It' should NOT match 'You Like It Darker by Stephen King'"""
        assert mock_prowlarr_source._title_matches(
            "You Like It Darker by Stephen King", "It"
        ) is False

    def test_short_title_exact_segment_after_dash(self, mock_prowlarr_source):
        """'It' should match 'Stephen King - It [EPUB]'"""
        assert mock_prowlarr_source._title_matches(
            "Stephen King - It [EPUB]", "It"
        ) is True

    def test_short_title_exact_segment_before_by(self, mock_prowlarr_source):
        """'It' should match 'It by Stephen King [EPUB]'"""
        assert mock_prowlarr_source._title_matches(
            "It by Stephen King [EPUB]", "It"
        ) is True

    def test_short_title_direct_containment(self, mock_prowlarr_source):
        """Direct containment still works for short titles"""
        assert mock_prowlarr_source._title_matches(
            "It - Stephen King", "It"
        ) is True

    def test_short_title_dune(self, mock_prowlarr_source):
        """'Dune' should match 'Frank Herbert - Dune [EPUB]'"""
        assert mock_prowlarr_source._title_matches(
            "Frank Herbert - Dune [EPUB]", "Dune"
        ) is True

    def test_short_title_dune_rejects_messiah(self, mock_prowlarr_source):
        """'Dune' should NOT match 'Dune Messiah by Frank Herbert'"""
        assert mock_prowlarr_source._title_matches(
            "Dune Messiah by Frank Herbert", "Dune"
        ) is False

    def test_short_title_two_words(self, mock_prowlarr_source):
        """Two-word title 'Dark Matter' should match correctly"""
        assert mock_prowlarr_source._title_matches(
            "Blake Crouch - Dark Matter [EPUB]", "Dark Matter"
        ) is True

    # --- Long title tests (3+ significant words) ---

    def test_long_title_direct_containment(self, mock_prowlarr_source):
        """Full title substring match"""
        assert mock_prowlarr_source._title_matches(
            "The Great Gatsby F Scott Fitzgerald [EPUB]", "The Great Gatsby"
        ) is True

    def test_long_title_subtitle_match(self, mock_prowlarr_source):
        """Subtitle 'The Final Empire' should match in release"""
        assert mock_prowlarr_source._title_matches(
            "Brandon Sanderson - The Final Empire [EPUB]",
            "Mistborn: The Final Empire"
        ) is True

    def test_long_title_word_overlap(self, mock_prowlarr_source):
        """Word overlap >= 60% should match"""
        assert mock_prowlarr_source._title_matches(
            "Gatsby Great American Novel", "The Great Gatsby"
        ) is True

    def test_long_title_insufficient_overlap(self, mock_prowlarr_source):
        """Word overlap < 60% should NOT match"""
        assert mock_prowlarr_source._title_matches(
            "Completely Different Book Title", "The Great Gatsby"
        ) is False

    # --- Empty/None edge cases ---

    def test_empty_expected_title(self, mock_prowlarr_source):
        """Empty expected title should always match (no filter)"""
        assert mock_prowlarr_source._title_matches(
            "Any Release Title", ""
        ) is True

    def test_none_expected_title_in_convert(self, mock_prowlarr_source):
        """No expected_title should skip title validation"""
        prowlarr_result = {
            "title": "Any Book [EPUB]",
            "downloadUrl": "http://download/1",
            "size": 2048000,
            "protocol": "torrent",
            "categories": [],
        }
        release = mock_prowlarr_source._convert_to_release(
            prowlarr_result, "ebook", expected_title=None
        )
        assert release is not None

    # --- Integration: _convert_to_release rejects wrong title ---

    def test_convert_rejects_wrong_title(self, mock_prowlarr_source):
        """_convert_to_release should reject releases with wrong title"""
        prowlarr_result = {
            "title": "You Like It Darker by Stephen King [EPUB]",
            "downloadUrl": "http://download/1",
            "size": 2048000,
            "protocol": "torrent",
            "categories": [{"id": 7000, "name": "Books/Ebook"}],
        }
        release = mock_prowlarr_source._convert_to_release(
            prowlarr_result, "ebook",
            expected_author="Stephen King",
            expected_title="It"
        )
        assert release is None

    def test_convert_accepts_correct_title(self, mock_prowlarr_source):
        """_convert_to_release should accept releases with correct title"""
        prowlarr_result = {
            "title": "Stephen King - It [EPUB]",
            "downloadUrl": "http://download/1",
            "size": 2048000,
            "protocol": "torrent",
            "categories": [{"id": 7000, "name": "Books/Ebook"}],
        }
        release = mock_prowlarr_source._convert_to_release(
            prowlarr_result, "ebook",
            expected_author="Stephen King",
            expected_title="It"
        )
        assert release is not None
        assert release.title == "Stephen King - It [EPUB]"

    # --- Integration: search() passes title through ---

    def test_search_filters_wrong_titles(self, mock_prowlarr_source):
        """search() should filter out releases that don't match the title"""
        mock_prowlarr_source.client.search_with_retry.return_value = [
            {
                "title": "Stephen King - It [EPUB]",
                "downloadUrl": "http://download/1",
                "size": 2048000,
                "protocol": "torrent",
                "categories": [{"id": 7000, "name": "Books/Ebook"}],
            },
            {
                "title": "You Like It Darker by Stephen King [EPUB]",
                "downloadUrl": "http://download/2",
                "size": 3048000,
                "protocol": "torrent",
                "categories": [{"id": 7000, "name": "Books/Ebook"}],
            },
        ]

        results = mock_prowlarr_source.search(
            title="It",
            author="Stephen King",
            format_type="ebook"
        )

        # Only the correct title should survive
        assert len(results) == 1
        assert "Stephen King - It" in results[0].title
