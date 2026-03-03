#!/bin/bash

# Set DATABASE_URL explicitly to ensure it points to the correct location
export DATABASE_URL="${DATABASE_URL:-sqlite:////app/data/bookkeep.db}"

if [[ "$DATABASE_URL" == sqlite:* ]]; then
    # Ensure data directory exists (where SQLite DB will be created)
    mkdir -p /app/data
    chmod 755 /app/data
fi

# Set PYTHONPATH - Alembic needs to import app.* modules
export PYTHONPATH="/app/backend:$PYTHONPATH"

echo "Running database migrations..."
echo "DATABASE_URL: $DATABASE_URL"

cd /app/backend

# Check current Alembic tracking state
echo "Checking Alembic version..."
ALEMBIC_CURRENT=$(python -m alembic -c alembic.ini current 2>&1)
echo "Alembic current: $ALEMBIC_CURRENT"

# If there is no alembic_version table the command prints nothing or errors.
# This happens when the DB was bootstrapped via SQLAlchemy create_all without
# Alembic ever having run (legacy deployments).  We detect this and stamp the
# database at the correct revision so Alembic only runs the truly new migrations.
if ! echo "$ALEMBIC_CURRENT" | grep -q "(head)\|Rev:"; then
    echo "No Alembic version found. Checking whether the database already has tables..."

    TABLES_EXIST=$(python -c "
import sys, os
sys.path.insert(0, '/app/backend')
from sqlalchemy import inspect, create_engine
engine = create_engine(os.environ['DATABASE_URL'])
try:
    print('yes' if inspect(engine).has_table('users') else 'no')
except Exception:
    print('no')
" 2>/dev/null || echo "no")

    echo "Existing tables found: $TABLES_EXIST"

    if [ "$TABLES_EXIST" = "yes" ]; then
        # The database has data but was never tracked by Alembic.
        # Check whether oidc_subject already exists to decide which revision to
        # stamp so we don't re-run migrations that were applied via create_all.
        OIDC_COL=$(python -c "
import sys, os
sys.path.insert(0, '/app/backend')
from sqlalchemy import inspect, create_engine
engine = create_engine(os.environ['DATABASE_URL'])
try:
    cols = [c['name'] for c in inspect(engine).get_columns('users')]
    print('yes' if 'oidc_subject' in cols else 'no')
except Exception:
    print('no')
" 2>/dev/null || echo "no")

        if [ "$OIDC_COL" = "yes" ]; then
            # Schema is fully up to date; stamp as head so no migrations run.
            echo "Schema is current. Stamping database as head..."
            python -m alembic -c alembic.ini stamp heads
        else
            # Schema is behind (oidc_subject missing). Stamp at 034 so Alembic
            # runs 035 and 036 to bring the schema up to date.
            echo "Legacy database missing recent columns. Stamping at revision 034..."
            python -m alembic -c alembic.ini stamp 034
        fi
    fi
fi

# Run all pending migrations.  Fail loudly if something goes wrong so the
# problem is visible in container logs rather than silently masked.
echo "Applying pending Alembic migrations..."
if python -m alembic -c alembic.ini upgrade heads; then
    echo "Migrations completed successfully."
    python -m alembic -c alembic.ini current
else
    echo "ERROR: Alembic migrations failed. Check the logs above for details."
    exit 1
fi

# Start the application from /app (where uvicorn expects to find backend module)
cd /app
echo "Starting application..."
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
