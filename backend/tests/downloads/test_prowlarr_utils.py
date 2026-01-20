"""
Unit tests for Prowlarr utilities.

Tests format detection, language detection, and helper functions.
"""
import pytest
from app.downloads.prowlarr.utils import (
    extract_format,
    extract_language,
    is_audiobook,
    normalize_title,
    build_search_queries,
    calculate_quality_score,
    extract_series_info,
    AUDIOBOOK_FORMATS,
    EBOOK_FORMATS,
)


class TestExtractFormat:
    """Test format extraction from titles"""

    def test_extract_epub(self):
        assert extract_format("Book Title [EPUB]") == "epub"
        assert extract_format("Book.Title.epub") == "epub"
        assert extract_format("Book Title EPUB") == "epub"

    def test_extract_mobi(self):
        assert extract_format("Book Title [MOBI]") == "mobi"
        assert extract_format("Book.Title.mobi") == "mobi"

    def test_extract_pdf(self):
        assert extract_format("Book Title [PDF]") == "pdf"
        assert extract_format("document.pdf") == "pdf"

    def test_extract_m4b(self):
        assert extract_format("Audiobook.m4b") == "m4b"
        assert extract_format("Book Title M4B") == "m4b"

    def test_extract_mp3(self):
        assert extract_format("Audiobook.mp3") == "mp3"
        assert extract_format("Book Title MP3") == "mp3"

    def test_prefer_filename_over_title(self):
        result = extract_format("Generic Title", filename="book.epub")
        assert result == "epub"

    def test_audiobook_formats_prioritized(self):
        # If both ebook and audiobook format present, audiobook wins
        result = extract_format("Book.Title.m4b.pdf")
        assert result == "m4b"

    def test_no_format_found(self):
        assert extract_format("Book Title No Format") is None
        assert extract_format("") is None
        assert extract_format(None) is None

    def test_azw3_format(self):
        assert extract_format("Book [AZW3]") == "azw3"
        assert extract_format("book.azw3") == "azw3"

    def test_case_insensitive(self):
        assert extract_format("book.EPUB") == "epub"
        assert extract_format("BOOK.Mobi") == "mobi"


class TestExtractLanguage:
    """Test language extraction from titles"""

    def test_extract_english(self):
        assert extract_language("Book Title [en]") == "en"
        assert extract_language("Book Title (en)") == "en"
        assert extract_language("Book in English") == "en"

    def test_extract_spanish(self):
        assert extract_language("Libro [es]") == "es"
        assert extract_language("Libro en español") == "es"
        assert extract_language("Spanish Book") == "es"

    def test_extract_german(self):
        assert extract_language("Buch [de]") == "de"
        assert extract_language("Buch auf deutsch") == "de"
        assert extract_language("German Book") == "de"

    def test_extract_french(self):
        assert extract_language("Livre [fr]") == "fr"
        assert extract_language("Livre en français") == "fr"

    def test_no_language_found(self):
        assert extract_language("Book Title No Language") is None
        assert extract_language("") is None
        assert extract_language(None) is None

    def test_case_insensitive(self):
        assert extract_language("Book ENGLISH") == "en"
        assert extract_language("Book En") == "en"


class TestIsAudiobook:
    """Test audiobook detection"""

    def test_detect_by_category(self):
        # 3030 = Audiobooks category
        assert is_audiobook("Some Title", categories=[3030]) is True

    def test_detect_by_audio_category_range(self):
        # 3000-3999 are audio categories
        assert is_audiobook("Title", categories=[3000]) is True
        assert is_audiobook("Title", categories=[3500]) is True
        assert is_audiobook("Title", categories=[3999]) is True

    def test_not_audiobook_by_category(self):
        # 7000 = Ebooks
        assert is_audiobook("Title", categories=[7000]) is False

    def test_detect_by_format(self):
        assert is_audiobook("Book.m4b") is True
        assert is_audiobook("Book.mp3") is True
        assert is_audiobook("Book [M4B]") is True

    def test_not_audiobook_by_format(self):
        assert is_audiobook("Book.epub") is False
        assert is_audiobook("Book [PDF]") is False

    def test_detect_by_keyword(self):
        assert is_audiobook("Book Title Audiobook") is True
        assert is_audiobook("Book Title audio book") is True
        assert is_audiobook("Book Title (Unabridged)") is True
        assert is_audiobook("Book Title Narrated by John Doe") is True

    def test_no_indicators(self):
        assert is_audiobook("Plain Book Title") is False


class TestNormalizeTitle:
    """Test title normalization"""

    def test_remove_format_tags(self):
        assert normalize_title("Book [EPUB]") == "Book"
        assert normalize_title("Book [MOBI]") == "Book"

    def test_remove_year(self):
        assert normalize_title("Book (2024)") == "Book"
        assert normalize_title("Book Title (1999)") == "Book Title"

    def test_remove_quality_tags(self):
        assert normalize_title("Book RETAIL") == "Book"
        assert normalize_title("Book PROPER") == "Book"
        assert normalize_title("Book v2") == "Book"

    def test_remove_group_tags(self):
        assert normalize_title("Book-GROUP") == "Book"
        assert normalize_title("Book Title-RELEASE") == "Book Title"

    def test_replace_dots_underscores(self):
        assert normalize_title("Book.Title.Here") == "Book Title Here"
        assert normalize_title("Book_Title_Here") == "Book Title Here"

    def test_remove_multiple_spaces(self):
        assert normalize_title("Book   Title    Here") == "Book Title Here"

    def test_strip_whitespace(self):
        assert normalize_title("  Book Title  ") == "Book Title"

    def test_complex_normalization(self):
        result = normalize_title("Book.Title.v2.RETAIL-GROUP [EPUB] (2024)")
        assert result == "Book Title"


class TestBuildSearchQueries:
    """Test search query generation"""

    def test_with_isbn_author_title(self):
        queries = build_search_queries(
            title="The Great Book",
            author="John Doe",
            isbn="1234567890"
        )
        # ISBN should be first
        assert queries[0] == "1234567890"
        # Title + Author should be second
        assert "The Great Book John Doe" in queries
        # Just title should be included
        assert "The Great Book" in queries

    def test_with_title_only(self):
        queries = build_search_queries(title="Book Title")
        assert "Book Title" in queries

    def test_remove_article_variant(self):
        queries = build_search_queries(title="The Great Book", include_variants=True)
        assert "Great Book" in queries  # "The" removed

        queries = build_search_queries(title="A Simple Story", include_variants=True)
        assert "Simple Story" in queries  # "A" removed

    def test_remove_subtitle_variant(self):
        queries = build_search_queries(title="Book: The Subtitle", include_variants=True)
        assert "Book" in queries  # Subtitle removed

        queries = build_search_queries(title="Book - A Story", include_variants=True)
        assert "Book" in queries

    def test_without_variants(self):
        queries = build_search_queries(
            title="The Book: A Story",
            include_variants=False
        )
        # Should not include variants without "The" or without subtitle
        variants = [q for q in queries if q == "Book"]
        assert len(variants) == 0

    def test_empty_inputs(self):
        queries = build_search_queries(title="", author="", isbn="")
        # Should still return something (empty title)
        assert len(queries) > 0


class TestCalculateQualityScore:
    """Test quality scoring algorithm"""

    def test_base_score(self):
        result = {"title": "Book"}
        score = calculate_quality_score(result)
        assert score == 50.0  # Base score

    def test_format_match_bonus(self):
        result = {"title": "Book [EPUB]"}
        score = calculate_quality_score(result, preferred_format="epub")
        assert score == 70.0  # Base (50) + format match (20)

    def test_no_format_match(self):
        result = {"title": "Book [MOBI]"}
        score = calculate_quality_score(result, preferred_format="epub")
        assert score == 50.0  # No bonus

    def test_seeder_bonus(self):
        result = {"title": "Book", "seeders": 10}
        score = calculate_quality_score(result)
        assert score > 50.0  # Should get seeder bonus

    def test_high_seeders(self):
        result = {"title": "Book", "seeders": 100}
        score = calculate_quality_score(result)
        # Should be near max seeder bonus (50 + 15 = 65)
        assert 60 <= score <= 70

    def test_size_validation_ebook(self):
        # Good size for ebook (5 MB)
        result = {"title": "Book.epub", "size_bytes": 5 * 1024 * 1024}
        score = calculate_quality_score(result)
        assert score == 60.0  # Base (50) + size bonus (10)

    def test_size_validation_audiobook(self):
        # Good size for audiobook (100 MB)
        result = {"title": "Book.m4b", "size_bytes": 100 * 1024 * 1024}
        score = calculate_quality_score(result)
        assert score == 60.0  # Base (50) + size bonus (10)

    def test_size_penalty_too_small(self):
        # Ebook too small (50 KB)
        result = {"title": "Book.epub", "size_bytes": 50 * 1024}
        score = calculate_quality_score(result)
        assert score == 40.0  # Base (50) - penalty (10)

    def test_size_penalty_too_large(self):
        # Ebook too large (1 GB)
        result = {"title": "Book.epub", "size_bytes": 1024 * 1024 * 1024}
        score = calculate_quality_score(result)
        assert score == 40.0  # Base (50) - penalty (10)

    def test_recency_bonus(self):
        from datetime import datetime, timezone, timedelta
        recent_date = datetime.now(timezone.utc) - timedelta(days=15)
        result = {"title": "Book", "publish_date": recent_date}
        score = calculate_quality_score(result)
        assert score == 55.0  # Base (50) + recency (5)

    def test_old_release_no_bonus(self):
        from datetime import datetime, timezone, timedelta
        old_date = datetime.now(timezone.utc) - timedelta(days=100)
        result = {"title": "Book", "publish_date": old_date}
        score = calculate_quality_score(result)
        assert score == 50.0  # No recency bonus

    def test_score_clamped_to_range(self):
        # Test score doesn't go below 0
        result = {
            "title": "Book.epub",
            "size_bytes": 1024 * 1024 * 1024 * 10,  # Way too large
        }
        score = calculate_quality_score(result)
        assert 0 <= score <= 100

    def test_combined_bonuses(self):
        from datetime import datetime, timezone, timedelta
        result = {
            "title": "Book [EPUB]",
            "seeders": 50,
            "size_bytes": 5 * 1024 * 1024,
            "publish_date": datetime.now(timezone.utc) - timedelta(days=10),
        }
        score = calculate_quality_score(result, preferred_format="epub")
        # Base (50) + format (20) + seeders (~13) + size (10) + recency (5) = ~98
        assert score >= 90


class TestExtractSeriesInfo:
    """Test series information extraction"""

    def test_extract_book_number(self):
        result = extract_series_info("The Great Series Book 3")
        assert result is not None
        assert result["name"] == "The Great Series"
        assert result["position"] == 3.0

    def test_extract_with_comma(self):
        result = extract_series_info("Series Name, Book 1")
        assert result is not None
        assert result["name"] == "Series Name"
        assert result["position"] == 1.0

    def test_extract_volume(self):
        result = extract_series_info("Series Name Vol 2")
        assert result is not None
        assert result["name"] == "Series Name"
        assert result["position"] == 2.0

        result = extract_series_info("Series Name Volume 3")
        assert result is not None
        assert result["position"] == 3.0

    def test_extract_hash_number(self):
        result = extract_series_info("Series Name #5")
        assert result is not None
        assert result["name"] == "Series Name"
        assert result["position"] == 5.0

    def test_decimal_position(self):
        result = extract_series_info("Series Book 2.5")
        assert result is not None
        assert result["position"] == 2.5

    def test_no_series_info(self):
        assert extract_series_info("Just A Book Title") is None
        assert extract_series_info("") is None


class TestFormatConstants:
    """Test format constant sets"""

    def test_audiobook_formats_defined(self):
        assert "m4b" in AUDIOBOOK_FORMATS
        assert "mp3" in AUDIOBOOK_FORMATS
        assert "flac" in AUDIOBOOK_FORMATS

    def test_ebook_formats_defined(self):
        assert "epub" in EBOOK_FORMATS
        assert "mobi" in EBOOK_FORMATS
        assert "pdf" in EBOOK_FORMATS

    def test_no_overlap(self):
        # Audiobook and ebook formats should not overlap
        overlap = AUDIOBOOK_FORMATS & EBOOK_FORMATS
        assert len(overlap) == 0
