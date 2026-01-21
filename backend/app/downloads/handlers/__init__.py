"""
Download handlers for Book Hound.

Handlers execute downloads using configured download clients.
"""
from .torrent import TorrentHandler
from .usenet import UsenetHandler

__all__ = ["TorrentHandler", "UsenetHandler"]
