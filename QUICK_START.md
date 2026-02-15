# Quick Start Guide - Download System

Get up and running with Book Hound's standalone download system in 5 minutes.

## Prerequisites

1. **Download clients running:**
   - qBittorrent (for torrents) - http://localhost:8080
   - NZBGet (for usenet) - http://localhost:6789
   - Prowlarr (for search) - http://localhost:9696

2. **Python dependencies installed:**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

## Step 1: Configure Environment

Create/update `.env` file:

```env
# Prowlarr
PROWLARR_URL=http://localhost:9696
PROWLARR_API_KEY=your_prowlarr_api_key_here

# qBittorrent
QBITTORRENT_HOST=localhost
QBITTORRENT_PORT=8080
QBITTORRENT_USERNAME=admin
QBITTORRENT_PASSWORD=adminadmin

# NZBGet
NZBGET_HOST=localhost
NZBGET_PORT=6789
NZBGET_USERNAME=nzbget
NZBGET_PASSWORD=tegbzn6789
```

**Get Prowlarr API Key:**
1. Open Prowlarr UI (http://localhost:9696)
2. Go to Settings → General
3. Copy the API Key

## Step 2: Test Connection

```python
from app.downloads.prowlarr import ProwlarrClient

# Test Prowlarr
client = ProwlarrClient("http://localhost:9696", "your_api_key")
if client.test_connection():
    print("✓ Prowlarr connected")
    indexers = client.get_indexers()
    print(f"✓ Found {len(indexers)} indexers")
else:
    print("✗ Prowlarr connection failed")
```

```python
from app.downloads.clients import QBittorrentClient

# Test qBittorrent
client = QBittorrentClient("localhost", 8080, "admin", "adminadmin")
if client.test_connection():
    print("✓ qBittorrent connected")
else:
    print("✗ qBittorrent connection failed")
```

## Step 3: Download a Book

### Option A: One-Liner (Easiest)

```python
from app.downloads import DownloadOrchestrator
from app.models import Book
from app.database import SessionLocal

db = SessionLocal()
orchestrator = DownloadOrchestrator(db_session=db)

# Get a book
book = db.query(Book).filter(Book.title.ilike("%hail mary%")).first()

# Search and download
task = orchestrator.search_and_download(book, "ebook")

if task:
    print(f"✓ Download started: Task #{task.id}")

    # Monitor
    import time
    while orchestrator.is_downloading(task.id):
        db.refresh(task)
        print(f"  [{task.state}] {task.progress:.1f}%")
        time.sleep(5)

    db.refresh(task)
    if task.state == "complete":
        print(f"✓ Complete: {task.download_path}")
else:
    print("✗ No releases found")

db.close()
```

### Option B: Step-by-Step (More Control)

```python
from app.downloads import DownloadOrchestrator
from app.database import SessionLocal

db = SessionLocal()
orchestrator = DownloadOrchestrator(db_session=db)

# Get book
book = db.query(Book).first()

# Step 1: Search
releases = orchestrator.search_releases(book, "ebook")
print(f"Found {len(releases)} releases")

if releases:
    # Step 2: Select best
    best = releases[0]
    print(f"Selected: {best.title} (quality: {best.quality_score})")

    # Step 3: Create task
    task = orchestrator.create_download_task(book, best, "ebook")
    print(f"Created task #{task.id}")

    # Step 4: Start download
    orchestrator.start_download(task.id)
    print(f"Download started")

    # Step 5: Monitor (optional)
    # ... monitoring code ...

db.close()
```

## Step 4: Check Status

```python
from app.models import DownloadTask
from app.database import SessionLocal

db = SessionLocal()

# Get all tasks
tasks = db.query(DownloadTask).all()

for task in tasks:
    print(f"Task #{task.id}: [{task.state}] {task.progress:.1f}%")
    print(f"  Book: {task.book.title}")
    print(f"  Release: {task.release_title}")
    if task.download_path:
        print(f"  Path: {task.download_path}")
    print()

db.close()
```

## Step 5: Manage Downloads

### Pause
```python
orchestrator.pause_download(task_id)
```

### Resume
```python
orchestrator.resume_download(task_id)
```

### Cancel
```python
orchestrator.cancel_download(task_id)
```

### Check Active
```python
active = orchestrator.get_active_downloads()
print(f"Active downloads: {len(active)}")
```

## Common Issues

### Issue: "No releases found"

**Solution 1:** Check Prowlarr has indexers configured
```python
from app.downloads.prowlarr import ProwlarrClient

client = ProwlarrClient("http://localhost:9696", "api_key")
indexers = client.get_indexers()

for idx in indexers:
    print(f"{idx['name']}: {idx['enable']}")
```

**Solution 2:** Try searching manually
```python
from app.downloads.prowlarr import ProwlarrSource

source = ProwlarrSource()
releases = source.search("Project Hail Mary", format_type="ebook")
print(f"Found {len(releases)} releases")
```

**Solution 3:** Check categories
- Prowlarr categories: 7000 for ebooks, 3030 for audiobooks
- Make sure your indexers support book categories

### Issue: "Connection refused"

**Check services are running:**
```bash
# Check qBittorrent
curl http://localhost:8080

# Check NZBGet
curl http://localhost:6789

# Check Prowlarr
curl http://localhost:9696
```

**Check credentials:**
- qBittorrent default: admin/adminadmin
- NZBGet default: nzbget/tegbzn6789
- Prowlarr: Get API key from Settings

### Issue: "Download stuck"

**Check client is working:**
1. Open qBittorrent Web UI: http://localhost:8080
2. Check if torrent appears in the list
3. Check if it's actually downloading

**Check logs:**
```python
import structlog
logger = structlog.get_logger()
# Logs will show what's happening
```

## Next Steps

1. **Read full documentation:**
   - [DOWNLOAD_SYSTEM_README.md](DOWNLOAD_SYSTEM_README.md)
   - [READARR_REPLACEMENT_STATUS.md](READARR_REPLACEMENT_STATUS.md)

2. **Run examples:**
   ```bash
   python backend/example_download_usage.py
   ```

3. **Run tests:**
   ```bash
   cd backend
   pytest tests/downloads/ -v
   ```

4. **Configure for production:**
   - Set up database-based client configuration
   - Configure path mappings for Docker
   - Set up proper logging

## Cheat Sheet

```python
# Import
from app.downloads import DownloadOrchestrator
from app.database import SessionLocal

# Setup
db = SessionLocal()
orch = DownloadOrchestrator(db_session=db)

# Search
releases = orch.search_releases(book, "ebook")

# Download
task = orch.search_and_download(book, "ebook")

# Monitor
while orch.is_downloading(task.id):
    db.refresh(task)
    print(f"{task.progress:.1f}%")
    time.sleep(5)

# Control
orch.pause_download(task.id)
orch.resume_download(task.id)
orch.cancel_download(task.id)

# Status
active = orch.get_active_downloads()
count = orch.get_download_count()
is_active = orch.is_downloading(task.id)

# Cleanup
db.close()
```

## Support

- **Documentation:** See markdown files in root directory
- **Examples:** See `backend/example_download_usage.py`
- **Tests:** See `backend/tests/downloads/`
- **Issues:** Open GitHub issue with logs

## Tips

1. **Always close database sessions:**
   ```python
   try:
       # Your code
   finally:
       db.close()
   ```

2. **Monitor in separate thread:**
   ```python
   import threading

   def monitor(task_id):
       # Monitoring code
       pass

   thread = threading.Thread(target=monitor, args=(task.id,))
   thread.start()
   ```

3. **Use context managers:**
   ```python
   from app.database import get_db

   with get_db() as db:
       orchestrator = DownloadOrchestrator(db_session=db)
       # Your code
   ```

4. **Check quality scores:**
   ```python
   for release in releases[:5]:
       print(f"{release.title}: {release.quality_score}")
   ```

5. **Filter by format:**
   ```python
   epub_releases = [r for r in releases if r.format == "epub"]
   ```

---

**That's it! You're ready to download books without Readarr.** 🎉
