"""
Download client implementations for Book Hound.

Provides interfaces for torrent and usenet download clients.
"""
from .qbittorrent import QBittorrentClient
from .nzbget import NZBGetClient
from .sabnzbd import SabnzbdClient

__all__ = ["QBittorrentClient", "NZBGetClient", "SabnzbdClient"]
