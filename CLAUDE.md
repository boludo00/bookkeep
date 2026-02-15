# Bookkeep

## Writing Style Rule

NEVER UNDER ANY CIRCUMSTANCES USE THE "\u2014" (em dash) CHARACTER IN YOUR RESPONSES. Always favor commas, colons, semicolons, or other standard punctuation instead.

## Overview

Bookkeep is a self-hosted library companion application for discovering books, exploring series, and managing book requests. It integrates with Hardcover.app for book metadata, Prowlarr for release searching, Booklore for library availability tracking, and download clients (qBittorrent, NZBGet, SABnzbd) for automated acquisition. The application serves media enthusiasts who want to catalog and manage their ebook/audiobook collections.

## Tech Stack

| Layer | Technology | Version | Purpose |
|-------|------------|---------|---------|
| Frontend Runtime | Node.js | 20.x | Build tooling and development |
| Frontend Framework | React | 18.x | UI components with lazy loading |
| Build Tool | Vite | 5.x | Fast HMR, SWC for transpilation |
| Language | TypeScript | 5.x | Type safety (relaxed strict mode) |
| Styling | Tailwind CSS | 3.x | Utility-first CSS with custom theme |
| UI Components | shadcn/ui + Radix | - | Accessible component primitives |
| Data Fetching | TanStack Query | 5.x | Server state management with caching |
| Backend Runtime | Python | 3.11+ | API server runtime |
| Backend Framework | FastAPI | 0.115.x | Async REST API with OpenAPI docs |
| ORM | SQLAlchemy | 2.x | Database models and queries |
| Database | PostgreSQL | 16.x | Primary data store |
| Migrations | Alembic | 1.x | Schema migrations |
| Cache | Redis | 7.x | API response caching (optional) |
| Scheduler | APScheduler | 3.x | Background job execution |

## Quick Start

```bash
# Prerequisites
# - Docker + Docker Compose
# - Hardcover API token from https://hardcover.app

# Using Docker Compose (recommended)
export HARDCOVER_API_TOKEN=your_token_here
docker-compose up --build

# Access points:
# - App: http://localhost:8000
# - API docs: http://localhost:8000/docs

# Local frontend development
npm install
npm run dev          # Starts on port 8080

# Local backend development
cd backend
curl -LsSf https://astral.sh/uv/install.sh | sh
uv pip install -r requirements.txt
export DATABASE_URL=postgresql://bookkeep:bookkeep_password@localhost:5432/bookkeep_db
uvicorn main:app --reload
```

## Project Structure

```
bookkeep/
├── src/                          # Frontend source (React/TypeScript)
│   ├── App.tsx                   # Root component with routing and providers
│   ├── main.tsx                  # Entry point
│   ├── components/
│   │   ├── ui/                   # shadcn/ui primitives (kebab-case: button.tsx, dialog.tsx)
│   │   ├── books/                # Book components (BookCard, BookRow, RequestDialog)
│   │   ├── layout/               # AppLayout, Header, Sidebar
│   │   ├── series/               # SeriesCard, SeriesRow
│   │   ├── search/               # SearchResults components
│   │   └── settings/             # Settings section components
│   ├── pages/                    # Route pages (19 total, lazy-loaded)
│   │   ├── Discover.tsx          # Home page with trending/popular
│   │   ├── BookDetails.tsx       # Book info with request UI
│   │   ├── Downloads.tsx         # Download task management
│   │   ├── Settings.tsx          # App configuration (largest page, ~51KB)
│   │   └── ...
│   ├── hooks/
│   │   ├── useAvailabilityPolling.ts  # Exponential backoff polling
│   │   ├── useHardcoverBooks.ts       # Trending/popular queries
│   │   └── usePageVisibility.ts       # Visibility API hook
│   ├── contexts/
│   │   ├── UserContext.tsx       # Auth state and user data
│   │   └── ThemeContext.tsx      # Dark mode theme
│   ├── lib/
│   │   ├── api.ts                # Centralized API client (~950 lines)
│   │   ├── hardcover.ts          # Hardcover data transformations
│   │   └── utils.ts              # Helper functions
│   └── types/
│       └── book.ts               # TypeScript interfaces
├── backend/
│   ├── main.py                   # FastAPI app with static file serving
│   ├── app/
│   │   ├── models.py             # SQLAlchemy models (14 tables)
│   │   ├── schemas.py            # Pydantic schemas (~400 lines)
│   │   ├── database.py           # DB engine, session management
│   │   ├── cache.py              # Redis/memory cache abstraction
│   │   ├── jwt.py                # JWT token creation/verification
│   │   ├── tasks.py              # Background job implementations (~55KB)
│   │   ├── scheduler.py          # APScheduler configuration
│   │   ├── routers/              # API route handlers (11 files)
│   │   │   ├── auth.py           # Login, token refresh
│   │   │   ├── users.py          # User CRUD, admin check
│   │   │   ├── books.py          # Book CRUD, availability
│   │   │   ├── requests.py       # Request management (~35KB)
│   │   │   ├── hardcover.py      # Hardcover API proxy (~118KB)
│   │   │   ├── downloads.py      # Download orchestration
│   │   │   ├── download_settings.py  # Prowlarr/client config
│   │   │   ├── booklore.py       # Booklore integration
│   │   │   ├── readarr.py        # Readarr integration
│   │   │   ├── settings.py       # User settings, cache mgmt
│   │   │   └── jobs.py           # Job scheduling
│   │   ├── downloads/            # Download system
│   │   │   ├── orchestrator.py   # Download coordination
│   │   │   ├── prowlarr/         # Prowlarr API integration
│   │   │   │   ├── api.py
│   │   │   │   └── source.py
│   │   │   ├── clients/          # Download client implementations
│   │   │   │   ├── qbittorrent.py
│   │   │   │   ├── nzbget.py
│   │   │   │   └── sabnzbd.py
│   │   │   └── handlers/         # Protocol handlers
│   │   │       ├── torrent.py
│   │   │       └── usenet.py
│   │   └── services/
│   │       ├── readarr_service.py
│   │       └── local_availability.py
│   ├── alembic/
│   │   └── versions/             # 16 migration files
│   ├── tests/                    # pytest test suite
│   ├── pyproject.toml            # Python 3.11+, uv managed
│   └── requirements.txt          # Pinned dependencies
├── public/                       # Static assets (favicon, icons)
├── docker-compose.yml            # Production stack (app, postgres, redis)
├── Dockerfile                    # Multi-stage build
└── .github/workflows/
    └── docker-build-publish.yml  # CI/CD for Docker Hub
```

## Architecture Overview

Bookkeep uses a **monolithic deployment** pattern where the FastAPI backend serves both the API and the built React frontend. The frontend is a single-page application with React Router handling client-side navigation; the backend catches all non-API routes and serves `index.html`.

**Data Flow:**
1. Frontend fetches book metadata from Hardcover API (GraphQL) via backend proxy
2. Book requests are stored in PostgreSQL with user associations
3. Prowlarr searches indexers for releases matching requested books
4. Download clients (qBittorrent/NZBGet/SABnzbd) handle file acquisition
5. Background jobs sync availability from Booklore and check download progress

```
┌─────────────────┐      ┌──────────────────┐      ┌────────────────┐
│   React SPA     │ ──▶  │   FastAPI API    │ ──▶  │   PostgreSQL   │
│   (Vite build)  │      │   /api/*         │      │   (data)       │
└─────────────────┘      └──────────────────┘      └────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
      ┌───────────┐     ┌───────────┐     ┌──────────────┐
      │ Hardcover │     │  Prowlarr │     │   Booklore   │
      │ (metadata)│     │ (indexers)│     │  (library)   │
      └───────────┘     └─────┬─────┘     └──────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
      ┌───────────┐   ┌───────────┐   ┌───────────┐
      │qBittorrent│   │   NZBGet  │   │  SABnzbd  │
      │ (torrent) │   │  (usenet) │   │  (usenet) │
      └───────────┘   └───────────┘   └───────────┘
```

### Key Modules

| Module | Location | Purpose |
|--------|----------|---------|
| API Client | `src/lib/api.ts` | JWT auth, token refresh, all backend API calls |
| Hardcover Client | `src/lib/hardcover.ts` | Data transformations for Hardcover responses |
| Request Dialog | `src/components/books/RequestDialog.tsx` | Book request UI with format selection |
| User Context | `src/contexts/UserContext.tsx` | Global auth state and user data |
| Books Router | `backend/app/routers/books.py` | Book CRUD and availability checks |
| Requests Router | `backend/app/routers/requests.py` | Request management and status updates |
| Hardcover Router | `backend/app/routers/hardcover.py` | Hardcover GraphQL API proxy (largest router) |
| Downloads Router | `backend/app/routers/downloads.py` | Release search and download orchestration |
| Scheduler | `backend/app/scheduler.py` | APScheduler job registration |
| Tasks | `backend/app/tasks.py` | Background job implementations |
| Orchestrator | `backend/app/downloads/orchestrator.py` | Download client coordination |

### Database Models

| Model | Purpose |
|-------|---------|
| `User` | Credentials, permissions (can_request_*, can_download, is_admin) |
| `Book` | Metadata, hardcover_id, format availability (ebook_available, audiobook_available) |
| `Series` | Hardcover series data |
| `BookRequest` | User request with status (pending/approved/denied/processing/available) |
| `DownloadTask` | Download progress tracking (state, progress, protocol) |
| `JobSchedule` | Background job configuration (interval, next_execution) |
| `ProwlarrServer` | Prowlarr indexer configuration |
| `DownloadClient` | Client config (qBittorrent/NZBGet/SABnzbd with category mapping) |
| `BookloreServer` | Booklore library integration |
| `ReadarrServer` | Readarr integration (legacy) |

## Development Guidelines

### Code Style

**Frontend (TypeScript/React):**
- File names: PascalCase for components (`BookCard.tsx`), camelCase for hooks/utils (`useToast.ts`)
- Component names: PascalCase matching file name (`export const BookCard = ...`)
- Functions/variables: camelCase (`const handleClick`, `const userData`)
- Types/interfaces: PascalCase (`interface BookCardProps`)
- Hooks: `use` prefix (`useHardcoverBooks`, `useUser`)
- Constants: camelCase or SCREAMING_SNAKE for true constants

**Backend (Python):**
- File names: snake_case (`readarr_service.py`, `local_availability.py`)
- Functions/variables: snake_case (`check_book_availability`, `ebook_available`)
- Classes: PascalCase (`ReadarrClient`, `BookRequest`)
- Constants: SCREAMING_SNAKE_CASE (`JOB_DEFINITIONS`, `ACCESS_TOKEN_KEY`)
- Router instances: `router = APIRouter()`

### Import Order

**Frontend:**
1. React/external packages (`import { useState } from 'react'`)
2. Internal absolute imports (`import { Button } from '@/components/ui/button'`)
3. Relative imports (`import { BookCard } from './BookCard'`)
4. Types (`import type { Book } from '@/types/book'`)

**Backend:**
1. Standard library (`import asyncio`, `from datetime import datetime`)
2. Third-party (`from fastapi import APIRouter`, `import structlog`)
3. Internal modules (`from app import models, schemas, cache`)

### Path Aliases

- Frontend uses `@/` alias for `./src/` (configured in `tsconfig.json` and `vite.config.ts`)

### Component Patterns

- Use `memo()` for expensive components receiving stable props
- Use TanStack Query for all server state (avoid `useState` for fetched data)
- Lazy load pages with `React.lazy()` for code splitting
- Use shadcn/ui components from `@/components/ui/` as primitives
- Default React Query config: `staleTime: 30_000`, `refetchOnWindowFocus: false`

### API Patterns

- All API calls go through `src/lib/api.ts` which handles auth tokens
- JWT tokens stored in localStorage with automatic refresh
- Backend routes prefixed with `/api/` (e.g., `/api/books`, `/api/requests`)
- API client organized into modules: `hardcoverApi`, `booksApi`, `requestsApi`, `downloadsApi`, etc.

### Polling Patterns

- `useAvailabilityPolling` hook uses exponential backoff (30s → 3min → 5min)
- `usePageVisibility` pauses polling when browser tab is hidden
- Download tasks polled separately via `sync_download_states` job

## Available Commands

### Frontend
| Command | Description |
|---------|-------------|
| `npm run dev` | Start Vite dev server on port 8080 |
| `npm run build` | Production build to `dist/` |
| `npm run lint` | Run ESLint |
| `npm run preview` | Preview production build |

### Backend
| Command | Description |
|---------|-------------|
| `uvicorn main:app --reload` | Start FastAPI dev server |
| `uv run pytest tests/ -v` | Run pytest test suite |
| `alembic upgrade head` | Apply database migrations |
| `alembic revision --autogenerate -m "msg"` | Generate migration |

### Docker
| Command | Description |
|---------|-------------|
| `docker-compose up --build` | Build and run full stack |
| `docker-compose up` | Run with existing images |
| `docker-compose logs -f app` | Tail application logs |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `HARDCOVER_API_TOKEN` | Yes | API token from hardcover.app |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | No | Redis URL for caching (falls back to memory) |
| `BOOKKEEP_SECRET_KEY` | No | JWT signing key (random if unset, sessions lost on restart) |
| `BOOKKEEP_ACCESS_TOKEN_EXPIRE_MINUTES` | No | Access token TTL (default: 30) |
| `BOOKKEEP_REFRESH_TOKEN_EXPIRE_DAYS` | No | Refresh token TTL (default: 7) |
| `VITE_API_URL` | No | Override API URL for frontend (dev only) |

## Testing

**Backend:**
- Tests in `backend/tests/` using pytest
- Run: `cd backend && pytest -v`
- pytest config in `pyproject.toml` with `pythonpath = ["."]`

**Frontend:**
- No test suite currently configured
- Vitest available via Vite but not set up

## Background Jobs

Jobs are managed via APScheduler and configurable in Settings > Jobs:

| Job | Default Interval | Purpose |
|-----|------------------|---------|
| `refresh_seed_data` | 24 hours | Fetch trending/popular books from Hardcover |
| `check_processing_requests` | 5 minutes | Check download tasks for completion |
| `sync_from_booklore` | 24 hours | Import availability from Booklore |
| `sync_missing_metadata` | 6 hours | Fill missing book metadata |
| `sync_download_states` | 2 minutes | Poll download clients for status |

## Deployment

- **Docker Hub:** `akiraslingshot/bookkeep:latest`
- Multi-arch builds (amd64 + arm64)
- CI triggers on push to `main` (tagged releases) and `develop` (develop tag)
- PRs get `pr-{number}` tags for testing

## Key API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/auth/login` | POST | User authentication |
| `/api/auth/refresh` | POST | Token refresh |
| `/api/users/check/admin-exists` | GET | Check if admin account exists |
| `/api/hardcover/search` | GET | Search books via Hardcover |
| `/api/hardcover/trending` | GET | Get trending books |
| `/api/books/{id}/availability` | GET | Check book availability |
| `/api/requests/` | GET/POST | List/create book requests |
| `/api/requests/by-hardcover/{id}` | GET | Get request by Hardcover ID |
| `/api/downloads/search` | POST | Search releases via Prowlarr |
| `/api/downloads/download` | POST | Start download |
| `/api/downloads/tasks` | GET | List download tasks |
| `/api/jobs/` | GET | List background jobs |
| `/api/settings/cache/{resource}` | DELETE | Clear cache by resource |

## Additional Resources

- [Hardcover API](https://hardcover.app) - Book metadata source
- [Prowlarr](https://prowlarr.com) - Indexer aggregator
- [FastAPI Docs](http://localhost:8000/docs) - Interactive API documentation (when running)
- [shadcn/ui](https://ui.shadcn.com) - Component library documentation


## Skill Usage Guide

When working on tasks involving these technologies, invoke the corresponding skill:

| Skill | Invoke When |
|-------|-------------|
| tailwind | Applies utility-first CSS styling with Tailwind and custom theme configuration |
| typescript | Enforces TypeScript type safety and interface patterns across frontend |
| react | Manages React components, hooks, and lazy loading patterns for the SPA |
| vite | Configures Vite build tool, HMR, and SWC transpilation for React development |
| frontend-design | Designs React components with Tailwind CSS, shadcn/ui, and Radix primitives |
| tanstack-query | Manages server state, caching, and data fetching with TanStack Query |
| shadcn-ui | Implements shadcn/ui accessible components and Radix UI primitives |
| python | Develops Python backend services with type hints and async patterns |
| sqlalchemy | Defines database models, relationships, and ORM queries in SQLAlchemy |
| fastapi | Builds async REST APIs, routes, and OpenAPI documentation with FastAPI |
| alembic | Generates and manages database migrations with Alembic |
| postgresql | Manages PostgreSQL database schema, migrations, and queries |
| apscheduler | Configures background job scheduling and task execution with APScheduler |
| redis | Implements caching layer with Redis or memory fallback |
| pytest | Writes and executes backend unit and integration tests with pytest |
