from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    # Permission fields
    can_request_ebook = Column(Boolean, default=True)
    can_request_audiobook = Column(Boolean, default=True)
    can_download = Column(Boolean, default=True)
    auto_approve_ebooks = Column(Boolean, default=True)
    auto_approve_audiobooks = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    requests = relationship("BookRequest", back_populates="user")

class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    author = Column(String, nullable=False)
    author_id = Column(Integer, nullable=True, index=True)  # Hardcover author ID from contributions
    isbn = Column(String, unique=True, index=True, nullable=True)
    description = Column(Text, nullable=True)
    cover_url = Column(String, nullable=True)
    genre = Column(String, nullable=True)
    published_date = Column(String, nullable=True)
    rating = Column(Float, nullable=True)
    page_count = Column(Integer, nullable=True)
    hardcover_id = Column(Integer, nullable=True, index=True, unique=True)
    hardcover_slug = Column(String, nullable=True, index=True)
    booklore_id = Column(Integer, nullable=True, index=True, unique=True)
    booklore_added_on = Column(DateTime(timezone=True), nullable=True)
    default_edition_id = Column(Integer, nullable=True)
    default_physical_edition_id = Column(Integer, nullable=True)
    default_ebook_edition_id = Column(Integer, nullable=True)
    default_audio_edition_id = Column(Integer, nullable=True)
    series = Column(String, nullable=True)
    series_id = Column(Integer, nullable=True, index=True)  # Store the actual series ID from Hardcover API
    series_position = Column(Float, nullable=True)
    genres = Column(String, nullable=True)  # JSON string or comma-separated
    # Additional Hardcover metadata for seed data
    ratings_count = Column(Integer, nullable=True)
    users_count = Column(Integer, nullable=True)
    activities_count = Column(Integer, nullable=True)
    release_year = Column(Integer, nullable=True)
    is_seed_data = Column(Boolean, default=False)  # Mark seed data for refresh
    # Per-format availability tracking
    ebook_available = Column(Boolean, default=False)  # Ebook is available in library
    audiobook_available = Column(Boolean, default=False)  # Audiobook is available in library
    last_refreshed = Column(DateTime(timezone=True), nullable=True)
    # Track downloaded release hashes (JSON array of hashes) for duplicate detection
    downloaded_release_hashes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    requests = relationship("BookRequest", back_populates="book")
    download_tasks = relationship("DownloadTask", back_populates="book", cascade="all, delete-orphan")

    @property
    def is_available(self):
        """Book is available if either ebook or audiobook is available."""
        return self.ebook_available or self.audiobook_available

class Series(Base):
    __tablename__ = "series"

    id = Column(Integer, primary_key=True, index=True)
    hardcover_id = Column(Integer, unique=True, index=True, nullable=False)  # Series ID from Hardcover API
    name = Column(String, nullable=False, index=True)
    books_count = Column(Integer, nullable=True)  # Total books in series (from API)
    is_seed_data = Column(Boolean, default=False)  # Mark seed data for refresh
    last_refreshed = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class BookRequest(Base):
    __tablename__ = "book_requests"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    format = Column(String, nullable=False)  # 'ebook', 'audiobook'
    status = Column(String, default='pending')  # 'pending', 'approved', 'denied', 'processing', 'available'
    source = Column(String, default='user_request')  # 'user_request' or 'booklore_import'
    notes = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)
    # Deprecated: Readarr fields kept for backward compatibility / migration
    readarr_book_id = Column(Integer, nullable=True, index=True)
    edition_id = Column(Integer, nullable=True)  # Hardcover edition id selected for request
    readarr_received = Column(Boolean, default=False, nullable=False)  # Deprecated
    readarr_search_triggered = Column(Boolean, nullable=True)  # Deprecated
    readarr_search_status_code = Column(Integer, nullable=True)  # Deprecated
    readarr_message = Column(Text, nullable=True)  # Deprecated
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    book = relationship("Book", back_populates="requests")
    user = relationship("User", back_populates="requests")

class AppSettings(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    value = Column(Text, nullable=True)
    source = Column(String, nullable=False, default='ui')  # 'env' or 'ui'
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class ReadarrServer(Base):
    __tablename__ = "readarr_servers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    hostname = Column(String, nullable=False)
    port = Column(Integer, nullable=False, default=8787)
    use_ssl = Column(Boolean, default=False)
    api_key = Column(String, nullable=False)
    url_base = Column(String, nullable=True)  # Optional URL base path
    is_default = Column(Boolean, default=False)  # Default server for ebook format
    is_audiobook = Column(Boolean, default=False)  # True for audiobook server, False for ebook
    # Ebook settings
    ebook_quality_profile_id = Column(Integer, nullable=True)
    ebook_root_folder = Column(String, nullable=True)
    ebook_tags = Column(String, nullable=True)  # Comma-separated tag IDs
    # Audiobook settings (if this is an audiobook server)
    audiobook_quality_profile_id = Column(Integer, nullable=True)
    audiobook_root_folder = Column(String, nullable=True)
    audiobook_tags = Column(String, nullable=True)  # Comma-separated tag IDs
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class BookloreServer(Base):
    __tablename__ = "booklore_servers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)  # Full URL like https://booklore.example.com
    username = Column(String, nullable=False)
    password = Column(String, nullable=False)  # Stored encrypted/hashed
    is_default = Column(Boolean, default=False)
    # Cached JWT tokens
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class JobSchedule(Base):
    __tablename__ = "job_schedules"

    id = Column(Integer, primary_key=True, index=True)
    job_name = Column(String, unique=True, index=True, nullable=False)
    interval_seconds = Column(Integer, nullable=False)  # How often the job runs
    last_execution = Column(DateTime(timezone=True), nullable=True)
    next_execution = Column(DateTime(timezone=True), nullable=True)  # When the job will run next
    is_enabled = Column(Boolean, default=True)
    state_json = Column(Text, nullable=True)  # JSON for job-specific state (e.g., offset)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DownloadClient(Base):
    """Download client configuration (qBittorrent, NZBGet, SABnzbd, etc.)"""
    __tablename__ = "download_clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    type = Column(String, nullable=False)  # "qbittorrent", "nzbget", "sabnzbd", "transmission"
    protocol = Column(String, nullable=False)  # "torrent" or "usenet"

    # Connection settings
    host = Column(String, nullable=False)
    port = Column(Integer, nullable=False)
    use_ssl = Column(Boolean, default=False)
    username = Column(String, nullable=True)
    password = Column(String, nullable=True)  # TODO: Encrypt this

    # Configuration
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # Higher = preferred
    category = Column(String, nullable=True)  # Legacy: default category
    ebook_category = Column(String, nullable=True)  # Category for ebooks
    audiobook_category = Column(String, nullable=True)  # Category for audiobooks

    # Path mappings (JSON array of {remote, local} objects for Docker)
    path_mappings_json = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ProwlarrServer(Base):
    """Prowlarr server configuration for searching releases"""
    __tablename__ = "prowlarr_servers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)

    # Connection settings
    host = Column(String, nullable=False)
    port = Column(Integer, nullable=False, default=9696)
    use_ssl = Column(Boolean, default=False)
    api_key = Column(String, nullable=False)
    url_base = Column(String, nullable=True)

    # Configuration
    enabled = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)

    # Indexer filtering - JSON list of allowed indexer IDs (empty/null = all indexers)
    indexer_ids_json = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DownloadTask(Base):
    """Download task tracking - replaces Readarr dependency"""
    __tablename__ = "download_tasks"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False, index=True)
    format = Column(String, nullable=False)  # "ebook" or "audiobook"

    # Release information
    source = Column(String, nullable=False)  # "prowlarr", "manual"
    release_title = Column(String, nullable=True)
    download_url = Column(String, nullable=True)
    protocol = Column(String, nullable=True)  # "torrent" or "usenet"
    indexer = Column(String, nullable=True)
    indexer_id = Column(Integer, nullable=True)
    size_bytes = Column(BigInteger, nullable=True)

    # Download state
    state = Column(String, default="queued", nullable=False, index=True)
    progress = Column(Float, default=0.0)  # 0.0 to 100.0
    download_speed = Column(Float, nullable=True)  # bytes/sec
    upload_speed = Column(Float, nullable=True)  # bytes/sec (torrents)
    eta_seconds = Column(Integer, nullable=True)
    downloaded_bytes = Column(BigInteger, nullable=True)
    total_bytes = Column(BigInteger, nullable=True)
    message = Column(String, nullable=True)

    # Paths
    download_path = Column(String, nullable=True)  # Where file was downloaded
    original_download_path = Column(String, nullable=True)  # For hardlinking (torrents)
    final_path = Column(String, nullable=True)  # Final organized location

    # Client tracking
    client_type = Column(String, nullable=True)  # "qbittorrent", "nzbget", etc.
    client_download_id = Column(String, nullable=True)  # ID in download client
    client_state = Column(String(50), nullable=True)  # Raw state from client (e.g., "stalledDL", "uploading")

    # Full release data (JSON blob)
    release_data_json = Column(Text, nullable=True)

    # Hash for tracking unique downloads (torrent info_hash, NZB hash, or download URL hash)
    info_hash = Column(String(64), nullable=True, index=True)

    # Import tracking
    import_status = Column(String(20), server_default='pending', nullable=True)  # pending, importing, imported, failed, skipped
    import_message = Column(String(500), nullable=True)  # Error message or status details
    imported_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    book = relationship("Book", back_populates="download_tasks")