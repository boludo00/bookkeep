"""
Direct download providers.

Each provider implements the DirectProvider interface to search
a specific source for downloadable books.
"""
from .base import DirectProvider, DirectSearchResult
from .annas_archive import AnnasArchiveProvider
from .zlibrary import ZLibraryProvider

__all__ = [
    "DirectProvider",
    "DirectSearchResult",
    "AnnasArchiveProvider",
    "ZLibraryProvider",
]
