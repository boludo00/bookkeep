# Changelog

All notable changes to Book Hound will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-01-21

### 🎉 Major Features

#### Complete Download System
- **Direct Download Management**: Download books directly through Book Hound without Readarr
- **Multi-Client Support**:
  - qBittorrent for torrents
  - NZBGet for usenet
  - SABnzbd for usenet
- **Prowlarr Integration**: Search for book releases across multiple indexers
- **Download Orchestration**: Intelligent download orchestration with retry logic and error handling
- **Real-time Progress Tracking**: Monitor downloads with live progress updates
- **Import Status Tracking**: Track when downloads are imported by Booklore or other media managers

#### JWT Authentication System
- **Secure Token-Based Auth**: Replace basic auth with JWT tokens
- **Access & Refresh Tokens**: 30-minute access tokens, 7-day refresh tokens
- **Persistent Sessions**: Tokens survive server restarts with configured secret key
- **User Permissions**: Granular permissions (can_request_ebook, can_request_audiobook, can_download)

#### Book Availability Management
- **Clear Availability**: Manually reset book availability flags to allow re-downloads
- **Per-Format Control**: Clear ebook or audiobook availability independently
- **Request Status Sync**: Clearing availability also resets request status
- **Interactive UI**: Hover over availability badges to reveal clear buttons

### ✨ New Features

#### Prowlarr Integration
- Configure multiple Prowlarr servers
- Search across all configured indexers
- Filter by release type (ebook/audiobook), quality, format
- View release details (size, seeders, indexer, protocol)
- Direct download to configured clients

#### Download Management UI
- New Downloads page showing active and completed downloads
- Real-time progress bars with percentage and status
- Import status indicators (waiting/imported/failed)
- Cancel active downloads
- Clear completed downloads
- Filter and search downloads

#### Enhanced Settings
- Download client configuration (qBittorrent, NZBGet, SABnzbd)
- Prowlarr server management
- Download paths configuration
- Category management for organizing downloads
- Connection testing for all services

#### Booklore Integration
- Track when books are sent to Booklore
- Store Booklore book IDs for reference
- Check availability in Booklore library
- Handle Booklore token refresh automatically

### 🔧 Improvements

#### User Interface
- Added Downloads navigation item in header
- Improved search results with availability status
- Enhanced book detail page with clear availability buttons
- Better request status visualization
- Real-time updates for download progress

#### API Enhancements
- New `/api/downloads` endpoints for download management
- New `/api/prowlarr` endpoints for search
- New `/api/books/{id}/availability/{format}` endpoint to clear availability
- Enhanced `/api/books/{id}/refresh` with Booklore checks
- Batch availability checks for better performance

#### Database
- New `download_tasks` table for tracking downloads
- New `download_clients` table for client configuration
- New `prowlarr_servers` table for Prowlarr configuration
- New `download_paths` table for path management
- Added `booklore_book_id` and `last_sent_to_booklore` to books
- Added `can_download` permission to users
- Added import status tracking fields

#### Authentication
- JWT secret key configuration via environment variable
- Token expiration configurable via environment variables
- Secure password hashing with bcrypt
- Token refresh endpoint for seamless re-authentication

### 🐛 Bug Fixes

- Fixed timezone handling for token expiration (use UTC everywhere)
- Fixed Booklore token refresh logic
- Fixed request status not updating when availability cleared
- Fixed missing "pending" status in RequestCard component
- Fixed database connection with correct credentials in docker-compose
- Added fallback for unknown request statuses to prevent crashes

### 🔒 Security

- JWT tokens replace basic authentication
- Configurable secret key (BOOKKEEP_SECRET_KEY)
- Password hashing for stored credentials
- Token expiration and refresh mechanism
- Secure API key storage for external services

### 📝 Configuration

#### New Environment Variables
```env
BOOKKEEP_SECRET_KEY=<your-secret-key>  # Required for JWT persistence
BOOKKEEP_ACCESS_TOKEN_EXPIRE_MINUTES=30  # Default: 30
BOOKKEEP_REFRESH_TOKEN_EXPIRE_DAYS=7     # Default: 7
```

#### Docker Compose Updates
- Added BOOKKEEP_SECRET_KEY to environment
- Documented importance of secret key for token persistence

### 📚 Documentation

- Added DOWNLOAD_SYSTEM_README.md for download system architecture
- Added QUICK_START.md for getting started guide
- Added example_download_usage.py for API usage examples
- Added audit and progress tracking documents

### ⚠️ Breaking Changes

- **Authentication**: Users must re-login after upgrade (old sessions invalid)
- **Environment**: BOOKKEEP_SECRET_KEY must be set for persistent sessions
- **Database**: Run migrations to add new tables and columns

### 🔄 Migration Guide

1. **Update Environment**:
   ```bash
   # Add to .env file
   BOOKKEEP_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
   ```

2. **Run Database Migrations**:
   ```bash
   docker-compose exec app alembic upgrade head
   ```

3. **Restart Services**:
   ```bash
   docker-compose restart
   ```

4. **Configure Download Clients**:
   - Go to Settings → Download Clients
   - Add your qBittorrent, NZBGet, or SABnzbd client
   - Test connection to verify configuration

5. **Configure Prowlarr** (Optional):
   - Go to Settings → Prowlarr
   - Add your Prowlarr server
   - Test connection to enable search functionality

### 📊 Database Migrations

- `022_add_download_system.py` - Core download system tables
- `023_add_prowlarr_servers.py` - Prowlarr integration
- `024_add_download_paths_and_categories.py` - Path management
- `025_add_download_hash_tracking.py` - Hash-based deduplication
- `026_add_client_state_tracking.py` - Client state persistence
- `027_add_import_status_tracking.py` - Import status tracking
- `028_add_can_download_permission.py` - Download permission

### 🔍 Technical Details

#### Download System Architecture
- **Handler Pattern**: Separate handlers for torrent and usenet
- **Client Abstraction**: Unified interface for different download clients
- **State Machine**: Track download lifecycle (queued → downloading → completed)
- **Error Recovery**: Automatic retry with exponential backoff
- **Deduplication**: Hash-based tracking to prevent duplicate downloads

#### API Changes
- All endpoints now require JWT authentication via `Authorization: Bearer <token>` header
- `/api/auth/login` - Get access and refresh tokens
- `/api/auth/refresh` - Refresh expired access token
- `/api/downloads/*` - Complete download management API
- `/api/prowlarr/*` - Search and indexer management

### 🎯 What's Next (v0.3.0)

- Background job system for scheduled availability checks
- Webhook support for Booklore import notifications
- Enhanced search with filters and sorting
- Series management improvements
- Reading list and collection features

---

## [0.1.0] - 2025-01-14

### Initial Release
- Book discovery from Hardcover API
- Book request system
- Readarr integration
- Basic user authentication
- Series browsing
- Popular and trending books
