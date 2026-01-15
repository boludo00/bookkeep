# Seed Data Setup

This application includes a hybrid approach to book data: it can work with seed data (pre-populated popular books) and also fetch fresh data from the Hardcover API.

## How It Works

1. **Seed Database**: The app ships with a SQLite database containing ~500 popular books
2. **API First**: When a Hardcover API token is configured, the app fetches fresh data from the API
3. **Fallback**: If the API is unavailable or no token is set, the app falls back to seed data
4. **Background Refresh**: The app automatically refreshes seed data every 24 hours (if API token is available)

## Initial Seed Data

To populate the seed database initially:

```bash
# Set your Hardcover API token
export HARDCOVER_API_TOKEN=your_token_here

# Run the seed script
python -m backend.scripts.seed_database
```

Or from within Docker:

```bash
docker exec -it book-hound python -m backend.scripts.seed_database
```

## Shipping Seed Data

The seed database (`data/bookhound.db`) can be included in the Docker image or mounted as a volume:

### Option 1: Include in Docker Image (Recommended for Distribution)

1. Run the seed script locally to create `data/bookhound.db`
2. Copy the database into the Docker image:

```dockerfile
COPY data/bookhound.db /app/data/bookhound.db
```

### Option 2: Volume Mount (Recommended for Development)

Mount the data directory as a volume in `docker-compose.yml`:

```yaml
volumes:
  - ./data:/app/data
```

Then run the seed script to populate it.

## Benefits

- **Fast Initial Load**: Seed data loads instantly without API calls
- **Works Offline**: App functions without API token initially
- **Better Demo**: Users see content immediately
- **Reduced API Load**: Fewer calls to Hardcover API
- **Resilient**: Falls back gracefully if API is down

## Database Schema

Seed books are marked with `is_seed_data=True` and include:
- Basic metadata (title, author, description, cover)
- Ratings and activity counts
- Series information
- Genres/tags
- Hardcover IDs for API lookups

## Background Refresh

The app automatically refreshes seed data every 24 hours if:
- A Hardcover API token is configured
- Seed data is older than 7 days

This ensures the seed data stays relatively current while minimizing API calls.

