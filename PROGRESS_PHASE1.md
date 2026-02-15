# Phase 1 Complete: Core Infrastructure ✅

**Date**: 2026-01-18
**Status**: Foundation Ready

---

## What Was Built

### 1. Plugin System Foundation ✅

**File**: `backend/app/downloads/__init__.py` (300+ lines)

**Core Components**:
- `DownloadState` enum - Track download states (queued, downloading, complete, etc.)
- `Release` dataclass - Unified release structure across all sources
- `DownloadStatus` dataclass - Current download progress and state
- `DownloadTask` dataclass - Internal task representation
- `ReleaseSource` ABC - Interface for search sources (Prowlarr, manual, etc.)
- `DownloadHandler` ABC - Interface for download execution
- Plugin registry with decorators (`@register_source`, `@register_handler`)
- Helper functions (`get_source`, `get_handler`, `list_sources`)

**Key Design Decisions**:
1. **Decorator-based registration** - Clean plugin discovery
2. **Protocol-agnostic** - Works with torrents and usenet equally
3. **Callback-driven** - Progress/status updates via callbacks (WebSocket-ready)
4. **Separation of concerns** - Sources search, handlers download

---

### 2. Database Models ✅

**File**: `backend/app/models.py`

**New Models**:

#### `DownloadClient`
Stores download client configuration (qBittorrent, NZBGet, etc.):
- Connection info (host, port, auth)
- Protocol type (torrent/usenet)
- Priority for client selection
- Path mappings (Docker support)

#### `DownloadTask`
Tracks individual download tasks:
- Book and format references
- Release metadata (source, URL, size, indexer)
- Download state and progress
- Client tracking (type, ID)
- Paths (download, original for hardlinking, final organized)
- Timestamps (created, started, completed)

**Updated Models**:
- Added `Book.download_tasks` relationship

---

### 3. Database Migration ✅

**File**: `backend/alembic/versions/022_add_download_system.py`

**Tables Created**:
- `download_clients` - Client configurations
- `download_tasks` - Task tracking

**Indexes Created**:
- `ix_download_clients_name` (unique)
- `ix_download_tasks_book_id`
- `ix_download_tasks_state`

**To Apply Migration**:
```bash
cd backend
alembic upgrade head
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│              Plugin System (Extensible)                  │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ReleaseSource (ABC)          DownloadHandler (ABC)     │
│  ├── ProwlarrSource           ├── ProwlarrHandler       │
│  ├── ManualSource             ├── DirectDownloadHandler │
│  └── [Future Sources]         └── [Future Handlers]     │
│                                                           │
│  Registry:                    Registry:                  │
│  _SOURCES = {...}             _HANDLERS = {...}          │
│  @register_source()           @register_handler()        │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

---

## Data Flow

```
1. User requests book
   ↓
2. ReleaseSource.search() → List[Release]
   ↓
3. User selects Release
   ↓
4. Create DownloadTask (DB)
   ↓
5. DownloadHandler.download(task, callbacks) → path
   ↓
6. Post-process (extract, organize) → final path
   ↓
7. Update Book availability
```

---

## Key Features

### Extensibility
- **Add new sources**: Implement `ReleaseSource`, decorate with `@register_source("name")`
- **Add new handlers**: Implement `DownloadHandler`, decorate with `@register_handler("source")`
- **No core changes needed**: Plugins register themselves on import

### Flexibility
- **Protocol-agnostic**: Torrents and usenet treated equally
- **Client-agnostic**: Handler chooses appropriate client based on protocol
- **Multiple clients**: Priority-based selection, failover support

### Production-Ready
- **Progress tracking**: Callbacks for real-time updates
- **Cancellation support**: `cancel_flag` parameter
- **Error handling**: Structured state management
- **Docker support**: Path mappings for container environments

---

## Next Steps (Phase 2: Prowlarr Integration)

### 1. Prowlarr API Client
**File**: `backend/app/downloads/prowlarr/api.py`

Features needed:
- Connection testing
- Search with categories (7000=ebook, 3030=audiobook)
- Indexer management
- Error handling with retries

### 2. Prowlarr Source Plugin
**File**: `backend/app/downloads/prowlarr/source.py`

Implement:
- `search()` method using ProwlarrClient
- Query building (title + author + ISBN variants)
- Format detection (extract from title/filename)
- Language detection
- Quality scoring

### 3. Format/Language Utilities
**File**: `backend/app/downloads/prowlarr/utils.py`

Extract from Shelfmark:
- Format patterns (`.epub`, `[MOBI]`, etc.)
- Language detection regex
- Title normalization

---

## Testing Checklist

Before moving to Phase 2:

- [ ] Import `app.downloads` module successfully
- [ ] Register a dummy source and handler
- [ ] Retrieve source/handler from registry
- [ ] Create DownloadClient in database
- [ ] Create DownloadTask in database
- [ ] Verify relationships (Book ↔ DownloadTask)

---

## Code Statistics

**Lines Added**:
- Plugin system: ~300 lines
- Models: ~80 lines
- Migration: ~90 lines
- **Total**: ~470 lines

**Files Created**: 3
**Files Modified**: 1

---

## Design Patterns Used

1. **Abstract Base Class (ABC)** - Enforce interface contracts
2. **Dataclass** - Clean, immutable data structures
3. **Registry Pattern** - Dynamic plugin discovery
4. **Decorator Pattern** - Clean registration syntax
5. **Callback Pattern** - Loose coupling for progress updates

---

## Benefits Over Readarr

✅ **No external service** - One less Docker container
✅ **Direct control** - Full access to download client APIs
✅ **Extensible** - Easy to add new sources/clients
✅ **Type-safe** - Proper Python types throughout
✅ **Testable** - Clean interfaces, dependency injection ready
✅ **Debuggable** - All code in one place

---

## Migration Strategy

Current plan supports **gradual migration**:

1. **Parallel operation**: New system runs alongside Readarr
2. **Opt-in**: Configure Prowlarr + clients to enable
3. **Fallback**: Keep Readarr for existing requests
4. **Full transition**: Disable Readarr when confident

No data loss, no downtime!

---

## Next Session Goals

1. Implement Prowlarr API client
2. Implement Prowlarr source plugin
3. Add format/language detection utilities
4. Test full search flow
5. Begin download client implementations (qBittorrent first)

---

## Questions for Next Session

1. Which download client to prioritize? (qBittorrent recommended)
2. Prowlarr instance details? (URL, API key for testing)
3. Preferred hardlinking strategy? (Keep seeding vs. move files)
4. Path mapping requirements? (Docker setup details)

