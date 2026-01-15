#!/bin/bash

# Set DATABASE_URL explicitly to ensure it points to the correct location
export DATABASE_URL="${DATABASE_URL:-sqlite:////app/data/bookhound.db}"

if [[ "$DATABASE_URL" == sqlite:* ]]; then
    # Ensure data directory exists (where SQLite DB will be created)
    mkdir -p /app/data
    chmod 755 /app/data
fi

# Set PYTHONPATH - Alembic needs to import app.* modules
export PYTHONPATH="/app/backend:$PYTHONPATH"

# Run Alembic migrations before starting the app
# Run from /app/backend where alembic.ini is located
echo "Running Alembic migrations..."
echo "Working directory: $(pwd)"
echo "PYTHONPATH: $PYTHONPATH"
echo "DATABASE_URL: $DATABASE_URL"
if [[ "$DATABASE_URL" == sqlite:* ]]; then
    echo "Database file will be at: /app/data/bookhound.db"
    # Check if database file exists
    if [ -f "/app/data/bookhound.db" ]; then
        echo "Database file exists"
    else
        echo "Database file does not exist yet (will be created by migration)"
    fi
fi

# Create tables first (SQLAlchemy will create all tables with current schema)
# Then migrations will add any missing columns (idempotent)
cd /app
echo "Creating database tables if they don't exist..."
python -c "from app.database import engine, Base; Base.metadata.create_all(bind=engine); print('✓ Tables created/verified')"

# Now run migrations to add any missing columns
cd /app/backend
echo "Running Alembic migrations..."
echo "Current directory: $(pwd)"
echo "Checking Alembic version..."
python -m alembic -c alembic.ini current || echo "No current version (database may be new)"
echo "Running migrations..."
if python -m alembic -c alembic.ini upgrade head 2>&1; then
    echo "✓ Alembic migrations completed successfully"
    python -m alembic -c alembic.ini current
else
    echo "✗ WARNING: Alembic migrations had issues (this is okay if columns already exist)"
fi

# Start the application from /app (where uvicorn expects to find backend module)
cd /app
echo "Starting application..."
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
