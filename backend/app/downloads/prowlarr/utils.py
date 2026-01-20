"""
Utility functions for Prowlarr integration.

Includes format detection, language detection, and title normalization.
"""
import re
from typing import Optional, List, Set
import structlog

logger = structlog.get_logger()


# Format patterns (from Shelfmark)
FORMAT_PATTERNS = {
    # Audiobook formats (check these first - they're more specific)
    "m4b": r"\.m4b\b|M4B",
    "mp3": r"\.mp3\b|MP3(?!\d)",  # Avoid matching "MP3 123" (bitrate)
    "m4a": r"\.m4a\b|M4A",
    "aac": r"\.aac\b|AAC",
    "flac": r"\.flac\b|FLAC",
    "ogg": r"\.ogg\b|OGG",
    "opus": r"\.opus\b|OPUS",

    # Ebook formats
    "epub": r"\.epub\b|EPUB|\[EPUB\]",
    "mobi": r"\.mobi\b|MOBI|\[MOBI\]",
    "azw": r"\.azw\b|AZW",
    "azw3": r"\.azw3\b|AZW3|\[AZW3\]",
    "pdf": r"\.pdf\b|PDF|\[PDF\]",
    "lit": r"\.lit\b|LIT",
    "pdb": r"\.pdb\b|PDB",
    "fb2": r"\.fb2\b|FB2",
    "djvu": r"\.djvu\b|DJVU",
    "cbr": r"\.cbr\b|CBR",
    "cbz": r"\.cbz\b|CBZ",

    # Ebook containers that might contain multiple formats
    "kepub": r"\.kepub\b|KEPUB",
    "ibooks": r"\.ibooks\b|iBooks",
}

# Audiobook-specific formats (prioritize these)
AUDIOBOOK_FORMATS = {"m4b", "mp3", "m4a", "aac", "flac", "ogg", "opus"}

# Ebook-specific formats
EBOOK_FORMATS = {"epub", "mobi", "azw", "azw3", "pdf", "lit", "pdb", "fb2", "djvu", "cbr", "cbz", "kepub", "ibooks"}


# Language code mapping (ISO 639-1)
LANGUAGE_PATTERNS = {
    "en": [
        r"\ben\b",
        r"\benglish\b",
        r"\[en\]",
        r"\(en\)",
    ],
    "es": [
        r"\bes\b",
        r"\bespañol\b",
        r"\bespanol\b",
        r"\bspanish\b",
        r"\[es\]",
    ],
    "fr": [
        r"\bfr\b",
        r"\bfrench\b",
        r"\bfrançais\b",
        r"\bfrancais\b",
        r"\[fr\]",
    ],
    "de": [
        r"\bde\b",
        r"\bgerman\b",
        r"\bdeutsch\b",
        r"\[de\]",
    ],
    "it": [
        r"\bit\b",
        r"\bitalian\b",
        r"\bitaliano\b",
        r"\[it\]",
    ],
    "pt": [
        r"\bpt\b",
        r"\bportuguese\b",
        r"\bportuguês\b",
        r"\bportugues\b",
        r"\[pt\]",
    ],
    "ru": [
        r"\bru\b",
        r"\brussian\b",
        r"\bрусский\b",
        r"\[ru\]",
    ],
    "ja": [
        r"\bja\b",
        r"\bjapanese\b",
        r"\b日本語\b",
        r"\[ja\]",
    ],
    "zh": [
        r"\bzh\b",
        r"\bchinese\b",
        r"\b中文\b",
        r"\[zh\]",
    ],
    "ko": [
        r"\bko\b",
        r"\bkorean\b",
        r"\b한국어\b",
        r"\[ko\]",
    ],
    "ar": [
        r"\bar\b",
        r"\barabic\b",
        r"\bعربي\b",
        r"\[ar\]",
    ],
    "nl": [
        r"\bnl\b",
        r"\bdutch\b",
        r"\bnederlands\b",
        r"\[nl\]",
    ],
    "pl": [
        r"\bpl\b",
        r"\bpolish\b",
        r"\bpolski\b",
        r"\[pl\]",
    ],
    "sv": [
        r"\bsv\b",
        r"\bswedish\b",
        r"\bsvenska\b",
        r"\[sv\]",
    ],
    "da": [
        r"\bda\b",
        r"\bdanish\b",
        r"\bdansk\b",
        r"\[da\]",
    ],
    "no": [
        r"\bno\b",
        r"\bnorwegian\b",
        r"\bnorsk\b",
        r"\[no\]",
    ],
    "fi": [
        r"\bfi\b",
        r"\bfinnish\b",
        r"\bsuomi\b",
        r"\[fi\]",
    ],
}


def extract_format(title: str, filename: Optional[str] = None) -> Optional[str]:
    """
    Extract format from title or filename.

    Prioritizes audiobook formats over ebook formats.

    Args:
        title: Release title
        filename: Optional filename (may be more accurate)

    Returns:
        Format string (e.g., "epub", "m4b") or None

    Examples:
        >>> extract_format("Book Title [EPUB]")
        'epub'
        >>> extract_format("Audiobook.m4b")
        'm4b'
        >>> extract_format("Book Title.pdf")
        'pdf'
    """
    text = filename if filename else title
    if not text:
        return None

    text_lower = text.lower()

    # Check audiobook formats first (more specific)
    for fmt in AUDIOBOOK_FORMATS:
        pattern = FORMAT_PATTERNS.get(fmt)
        if pattern and re.search(pattern, text, re.IGNORECASE):
            return fmt

    # Then check ebook formats
    for fmt in EBOOK_FORMATS:
        pattern = FORMAT_PATTERNS.get(fmt)
        if pattern and re.search(pattern, text, re.IGNORECASE):
            return fmt

    return None


def extract_language(title: str) -> Optional[str]:
    """
    Extract language code from title.

    Args:
        title: Release title

    Returns:
        ISO 639-1 language code (e.g., "en", "es") or None

    Examples:
        >>> extract_language("Book Title [en]")
        'en'
        >>> extract_language("Libro en español")
        'es'
        >>> extract_language("Book in German")
        'de'
    """
    if not title:
        return None

    title_lower = title.lower()

    for lang_code, patterns in LANGUAGE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, title_lower, re.IGNORECASE):
                return lang_code

    return None


def is_audiobook(title: str, categories: Optional[List[int]] = None) -> bool:
    """
    Determine if release is an audiobook.

    Args:
        title: Release title
        categories: Prowlarr category IDs

    Returns:
        True if audiobook, False otherwise
    """
    # Check categories first (most reliable)
    if categories:
        # 3030 = Audiobooks category in Prowlarr
        if 3030 in categories:
            return True
        # 3000-3999 are audio categories
        if any(3000 <= cat < 4000 for cat in categories):
            return True

    # Check for audiobook formats in title
    fmt = extract_format(title)
    if fmt in AUDIOBOOK_FORMATS:
        return True

    # Check for audiobook keywords
    audiobook_keywords = [
        r"\baudiobook\b",
        r"\baudio\s*book\b",
        r"\bunabridged\b",
        r"\babridged\b",
        r"\bnarrated\b",
    ]

    title_lower = title.lower()
    for keyword in audiobook_keywords:
        if re.search(keyword, title_lower):
            return True

    return False


def normalize_title(title: str) -> str:
    """
    Normalize title for better matching.

    Removes common clutter like format tags, year, quality indicators, etc.

    Args:
        title: Original title

    Returns:
        Normalized title

    Examples:
        >>> normalize_title("Book Title [EPUB] (2024)")
        'Book Title'
        >>> normalize_title("Book.Title.v2.RETAIL-GROUP")
        'Book Title'
    """
    # Remove file extensions
    normalized = re.sub(r"\.(epub|mobi|azw|azw3|pdf|m4b|mp3)$", "", title, flags=re.IGNORECASE)

    # Remove format tags
    normalized = re.sub(r"\[(EPUB|MOBI|AZW|AZW3|PDF|M4B|MP3)\]", "", normalized, flags=re.IGNORECASE)

    # Remove year in parentheses
    normalized = re.sub(r"\((\d{4})\)", "", normalized)

    # Remove quality/source tags
    normalized = re.sub(r"\b(RETAIL|PROPER|REPACK|V\d+)\b", "", normalized, flags=re.IGNORECASE)

    # Remove group tags
    normalized = re.sub(r"-[A-Z0-9]+$", "", normalized)

    # Replace dots and underscores with spaces
    normalized = normalized.replace(".", " ").replace("_", " ")

    # Remove multiple spaces
    normalized = re.sub(r"\s+", " ", normalized)

    # Strip and return
    return normalized.strip()


def build_search_queries(
    title: str,
    author: Optional[str] = None,
    isbn: Optional[str] = None,
    include_variants: bool = True
) -> List[str]:
    """
    Build list of search query variants.

    Args:
        title: Book title
        author: Book author (optional)
        isbn: ISBN (optional)
        include_variants: Include title variants

    Returns:
        List of search queries to try

    Examples:
        >>> build_search_queries("The Great Book", "John Doe", "1234567890")
        ['1234567890', 'The Great Book John Doe', 'The Great Book', 'Great Book']
    """
    queries = []

    # ISBN is most specific - try first if available
    if isbn:
        queries.append(isbn)

    # Title + Author
    if title and author:
        queries.append(f"{title} {author}")

    # Just title
    if title:
        queries.append(title)

    # Title variants (if enabled)
    if include_variants and title:
        # Remove "The", "A", "An" from beginning
        title_no_article = re.sub(r"^(The|A|An)\s+", "", title, flags=re.IGNORECASE)
        if title_no_article != title:
            queries.append(title_no_article)

        # Remove subtitle (after colon or dash)
        title_no_subtitle = re.split(r"\s*[:\-–]\s*", title)[0]
        if title_no_subtitle != title:
            queries.append(title_no_subtitle)

    return queries


def calculate_quality_score(
    result: dict,
    preferred_format: Optional[str] = None,
    min_seeders: int = 1
) -> float:
    """
    Calculate quality score for a release (0-100).

    Higher score = better quality.

    Args:
        result: Parsed Prowlarr result
        preferred_format: Preferred format (e.g., "epub", "m4b")
        min_seeders: Minimum seeders threshold

    Returns:
        Quality score (0.0 to 100.0)
    """
    score = 50.0  # Base score

    # Format match (+20 points)
    if preferred_format:
        fmt = extract_format(result.get("title", ""))
        if fmt == preferred_format:
            score += 20

    # Seeder count (0 to +15 points)
    seeders = result.get("seeders", 0)
    if seeders:
        if seeders >= min_seeders:
            # Logarithmic scaling: 1 seeder = +5, 10 seeders = +10, 100+ seeders = +15
            import math
            seeder_score = min(15, 5 + (math.log10(seeders) * 5))
            score += seeder_score

    # Size check (penalize extremely large or small files)
    size_bytes = result.get("size_bytes", 0)
    if size_bytes:
        size_mb = size_bytes / (1024 * 1024)
        # Ebooks should be 0.5-50 MB, audiobooks 50-500 MB
        if is_audiobook(result.get("title", "")):
            if 50 <= size_mb <= 1000:
                score += 10
            elif size_mb < 10 or size_mb > 2000:
                score -= 10
        else:  # Ebook
            if 0.5 <= size_mb <= 100:
                score += 10
            elif size_mb < 0.1 or size_mb > 500:
                score -= 10

    # Recency bonus (newer releases +5 points)
    publish_date = result.get("publish_date")
    if publish_date:
        from datetime import datetime, timezone, timedelta
        age_days = (datetime.now(timezone.utc) - publish_date).days
        if age_days < 30:
            score += 5

    # Clamp to 0-100 range
    return max(0.0, min(100.0, score))


def extract_series_info(title: str) -> Optional[dict]:
    """
    Extract series name and position from title.

    Args:
        title: Release title

    Returns:
        Dict with "name" and "position" or None

    Examples:
        >>> extract_series_info("The Great Series Book 3")
        {'name': 'The Great Series', 'position': 3.0}
        >>> extract_series_info("Series Name, Book 1")
        {'name': 'Series Name', 'position': 1.0}
    """
    # Pattern: "Series Name Book N" or "Series Name, Book N"
    patterns = [
        r"^(.+?)\s+Book\s+(\d+(?:\.\d+)?)",
        r"^(.+?),\s*Book\s+(\d+(?:\.\d+)?)",
        r"^(.+?)\s+Vol(?:ume)?\.?\s+(\d+(?:\.\d+)?)",
        r"^(.+?)\s+#(\d+(?:\.\d+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            series_name = match.group(1).strip()
            position = float(match.group(2))
            return {
                "name": series_name,
                "position": position
            }

    return None
