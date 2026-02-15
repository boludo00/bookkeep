# Bookkeep

Bookkeep is a self-hosted library companion for discovering books, exploring series, and requesting formats through integrated services.

## Features

- Discover trending and popular titles
- Search books, authors, and series
- Author detail pages with bio, portrait, books, and series
- Book and series request flows
- Admin tooling for users, requests, and settings

## Screenshots

### Discover
![Discover](docs/imgs/discover.png)

### Book Details
![Book Details](docs/imgs/book.png)

### Series
![Series](docs/imgs/series.png)

### Search
![Search](docs/imgs/search.png)

### Requests
![Requests](docs/imgs/requests.png)

## Tech Stack

- React + Vite + TypeScript
- Tailwind CSS + shadcn/ui
- FastAPI backend
- PostgreSQL database
- Optional Redis cache

## Requirements

- Docker + Docker Compose
- Hardcover API token (from https://hardcover.app)

## Running with Docker Compose (from source)

The default `docker-compose.yml` builds from source and runs the app with Postgres + Redis.

```sh
export HARDCOVER_API_TOKEN=your_token_here
docker-compose up --build
```

Access:
- App (frontend + API): http://localhost:8000
- API docs: http://localhost:8000/docs

## Running with Docker Compose (Docker Hub image)

Create a separate compose file (e.g. `docker-compose.dockerhub.yml`) with a prebuilt image:

```yaml
version: '3.8'

services:
  app:
    image: akiraslingshot/bookkeep:latest
    container_name: bookkeep
    environment:
      DATABASE_URL: postgresql://bookkeep:bookkeep_password@db:5432/bookkeep_db
      HARDCOVER_API_TOKEN: ${HARDCOVER_API_TOKEN:-}
      REDIS_URL: redis://redis:6379/0
      BOOKKEEP_SECRET_KEY: ${BOOKKEEP_SECRET_KEY:-}
    # volumes:
    #   # Mount host download directories so Bookkeep can access completed downloads.
    #   # Adjust the left side (host path) to match your download client's output directory.
    #   - /path/to/downloads:/downloads
    #   # Example: separate mounts for different media types
    #   # - /data/media/ebooks:/downloads/ebooks
    #   # - /data/media/audiobooks:/downloads/audiobooks
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    container_name: bookkeep-db
    environment:
      POSTGRES_DB: bookkeep_db
      POSTGRES_USER: bookkeep
      POSTGRES_PASSWORD: bookkeep_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: bookkeep-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

  # Optional: FlareSolverr for direct downloads (solves DDoS-Guard challenges)
  # flaresolverr:
  #   image: ghcr.io/flaresolverr/flaresolverr:latest
  #   container_name: bookkeep-flaresolverr
  #   environment:
  #     LOG_LEVEL: info
  #   ports:
  #     - "8191:8191"
  #   restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

Run it:

```sh
docker-compose -f docker-compose.dockerhub.yml up
```

## Local Development with Docker

For local development, create a `dev.docker-compose.yml` (gitignored) based on the production compose file. This lets you add personal paths, volume mounts, and other dev-specific overrides without affecting the committed config.

```yaml
version: '3.8'

services:
  app:
    image: book-hound:latest
    build:
      context: .
      dockerfile: Dockerfile
    container_name: book-hound
    environment:
      DATABASE_URL: postgresql://bookhound:bookhound_password@db:5432/bookhound_db
      HARDCOVER_API_TOKEN: ${HARDCOVER_API_TOKEN:-}
      REDIS_URL: redis://redis:6379/0
      BOOKKEEP_SECRET_KEY: ${BOOKKEEP_SECRET_KEY:-}
    volumes:
      # Map your host download directory into the container
      - /path/to/downloads:/downloads
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    container_name: book-hound-db
    environment:
      POSTGRES_DB: bookhound_db
      POSTGRES_USER: bookhound
      POSTGRES_PASSWORD: bookhound_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: book-hound-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

Run it:

```sh
export HARDCOVER_API_TOKEN=your_token_here
docker-compose -f dev.docker-compose.yml up --build
```

## Configuration

Required environment variables:
- `HARDCOVER_API_TOKEN`
- `DATABASE_URL`

Optional:
- `REDIS_URL`
- `BOOKKEEP_SECRET_KEY` - JWT secret key for token signing (see Authentication below)
- `BOOKKEEP_ACCESS_TOKEN_EXPIRE_MINUTES` - Access token expiration (default: 30)
- `BOOKKEEP_REFRESH_TOKEN_EXPIRE_DAYS` - Refresh token expiration (default: 7)

## Download Client Volumes

If you use download clients (qBittorrent, NZBGet, SABnzbd) running in Docker alongside Bookkeep, you need shared volume mounts so the Bookkeep container can access completed downloads on the host filesystem.

Uncomment and adjust the `volumes` section in your compose file:

```yaml
    volumes:
      # Map your host download directory into the container
      - /path/to/downloads:/downloads
      # Or separate mounts for different media types
      - /data/media/ebooks:/downloads/ebooks
      - /data/media/audiobooks:/downloads/audiobooks
```

The **container path** (right side, e.g. `/downloads`) is what you configure in **Settings > Download Clients** as the download directory. The **host path** (left side) should match where your download client writes completed files.

> **Tip:** If your download client runs in its own container, mount the same host directory into both containers so the paths align. For example, if qBittorrent saves to `/data/downloads` on the host, mount `-v /data/downloads:/downloads` in both containers.

## Authentication

Bookkeep uses JWT (JSON Web Tokens) for authentication. Users log in with username/password and receive an access token and refresh token.

- **Access tokens** are short-lived (default 30 minutes) and used for API requests
- **Refresh tokens** are longer-lived (default 7 days) and used to obtain new access tokens

### Secret Key

Set `BOOKKEEP_SECRET_KEY` to a secure random string for production deployments. This key is used to sign JWT tokens.

```sh
# Generate a secure key
openssl rand -base64 32
```

If not set, a random key is generated at startup. This means **all users will be logged out when the server restarts**. For persistent sessions across restarts, always set this variable.

## Direct Downloads

Bookkeep can download books directly from Anna's Archive and Z-Library without requiring Prowlarr or external download clients. Enable this feature in **Settings > Direct Downloads**.

### How it works

When you search for a book, direct download results appear alongside Prowlarr results. The backend handles the full download lifecycle: finding sources, waiting through server countdowns, solving access challenges, and streaming the file to your configured download path.

### FlareSolverr (recommended)

Anna's Archive slow download servers are protected by DDoS-Guard. To access these sources, you need a running [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) instance to solve the challenges.

Add FlareSolverr to your `docker-compose.yml`:

```yaml
  flaresolverr:
    image: ghcr.io/flaresolverr/flaresolverr:latest
    container_name: bookkeep-flaresolverr
    environment:
      LOG_LEVEL: info
    ports:
      - "8191:8191"
    restart: unless-stopped
```

Then set the FlareSolverr URL in **Settings > Direct Downloads** to:

```
http://flaresolverr:8191
```

Without FlareSolverr, direct downloads will still work but only with sources that don't require challenge solving, which significantly reduces the number of available sources.

### Download paths

Configure your ebook and audiobook download paths in **Settings > Direct Downloads**. The paths must be accessible from within the Docker container. For example, add a volume mount:

```yaml
  app:
    volumes:
      - /path/on/host/ebooks:/downloads/ebooks
      - /path/on/host/audiobooks:/downloads/audiobooks
```

Then set the download paths in settings to `/downloads/ebooks` and `/downloads/audiobooks`.

## Jobs & Scheduling

Bookkeep runs background jobs via APScheduler. You can view and change schedules in Settings → Jobs, and manually trigger a job without changing its schedule.

Default jobs:
- `refresh_seed_data` (daily): pulls fresh books from Hardcover to keep the local catalog populated.
- `check_processing_requests` (every 5 minutes): checks for request status changes and updates requests that have completed.
- `sync_from_booklore` (daily): syncs availability from Booklore, importing items and marking matching requests as available.
- `sync_missing_metadata` (every 6 hours): fills missing metadata (cover, rating, IDs, series) using Hardcover.

Notes:
- Job state (e.g., seed refresh offset) is stored in the database.
- If Redis is unavailable, jobs still run; caching falls back to memory.

## Search Performance Notes

Autocomplete uses cached/local data only. Full searches call the Hardcover search API and cache results for faster subsequent queries.

## Releases & Docker Hub

Images are published to Docker Hub on pushes to `main` and `develop` with multi-arch support (amd64 + arm64).

Required GitHub secrets:
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

Version bump labels for `develop` → `main` PRs:
- `bump:major`
- `bump:minor`
- `bump:patch`

Main branch publishes:
- `vX.Y.Z`
- `X.Y.Z`
- `latest`

Develop branch publishes:
- `vX.Y.Z-develop-<shortsha>`

## Caching

Redis is used to cache Hardcover API responses. If Redis is unavailable, the app falls back to in-memory caching.

See `backend/README.md` for backend API details.

## A Note on AI Assistance

**In the interest of transparency**: the frontend components in this project were all built with help from AI tools. This includes the React components, UI/UX bits, and styling, especially the theme picker!

It's totally understandable if you are anti-AI or if that's just not your cup of tea, no hard feelings, there are plenty of great alternatives out there.

As a backend-focused Python developer with **many** failed attempts at front end development, I can't express it enough just how helpful it is to offload the cumbersome and mundane parts of this project. 

The backend, API design, database work, and overall system design will remain human.
