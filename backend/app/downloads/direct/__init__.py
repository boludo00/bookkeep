"""
Direct download source package.

Provides unified access to direct download providers (Anna's Archive, Z-Library, etc.)
through a single DirectDownloadSource that aggregates results.
"""
from .source import DirectDownloadSource

__all__ = ["DirectDownloadSource"]
