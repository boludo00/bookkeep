# PostgreSQL Workflows Reference

## Contents
- Migration Workflow
- Connection Pool Tuning
- Query Debugging
- Database Reset
- Production Checklist

---

## Migration Workflow

### Creating a New Migration

```bash
# 1. Make model changes in backend/app/models.py
# 2. Generate migration
cd backend
alembic revision --autogenerate -m "add user preferences table"

# 3. Review generated migration in alembic/versions/
# 4. Apply migration
alembic upgrade head
```

### Idempotent Migration Pattern

```python
# backend/alembic/versions/022_*.py
from sqlalchemy import inspect

def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()

def upgrade():
    if not table_exists('download_tasks'):
        op.create_table('download_tasks', ...)
```

### Data Migration with Raw SQL

```python
# For bulk data updates in migrations
def upgrade():
    # Set defaults for existing rows
    op.execute("UPDATE users SET can_request_ebook = TRUE WHERE can_request_ebook IS NULL")
    
    # Computed column backfill
    op.execute("""
        UPDATE books SET is_available = TRUE 
        WHERE ebook_available = TRUE OR audiobook_available = TRUE
    """)
```

### Migration Workflow Checklist

Copy this checklist and track progress:
- [ ] Make model changes in `backend/app/models.py`
- [ ] Run `alembic revision --autogenerate -m "description"`
- [ ] Review generated migration for correctness
- [ ] Add data migration if needed (UPDATE statements)
- [ ] Test locally: `alembic upgrade head`
- [ ] Test rollback: `alembic downgrade -1`
- [ ] Commit migration file

---

## Connection Pool Tuning

### Diagnose Pool Exhaustion

```python
# Add logging to see pool status
import logging
logging.getLogger('sqlalchemy.pool').setLevel(logging.DEBUG)

# Check for connection leaks
# Look for: "Pool limit exceeded, waiting..."
```

### Environment Configuration

```bash
# Production settings for moderate load
DB_POOL_SIZE=10           # Base connections
DB_MAX_OVERFLOW=20        # Burst to 30 total
DB_POOL_TIMEOUT=30        # Wait 30s for connection
DB_POOL_RECYCLE=1800      # Recycle every 30 min

# High-load settings
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=30
```

### Pre-ping for Connection Health

```python
# backend/app/database.py - Already enabled
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Validates connections with SELECT 1
)
```

This prevents "server closed the connection unexpectedly" errors from stale connections after PostgreSQL restarts or network interruptions.

---

## Query Debugging

### Enable SQL Logging

```python
# Temporary debugging - add to database.py
engine = create_engine(DATABASE_URL, echo=True)

# Or via logging
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

### Identify N+1 Queries

```python
# Count queries in a request
from sqlalchemy import event

query_count = 0

@event.listens_for(engine, "before_cursor_execute")
def count_queries(conn, cursor, statement, *args):
    global query_count
    query_count += 1

# After request: if query_count > 10, investigate
```

### EXPLAIN ANALYZE via ORM

```python
# Get query plan for slow queries
from sqlalchemy import text

result = db.execute(text("""
    EXPLAIN ANALYZE 
    SELECT * FROM books WHERE hardcover_id = :id
"""), {"id": 12345})
for row in result:
    print(row[0])
```

---

## Database Reset

### Development Reset

```bash
# Drop and recreate database
docker-compose down -v  # Removes volumes
docker-compose up -d postgres
cd backend
alembic upgrade head
```

### Reset with Data Preservation

```bash
# Backup first
docker exec bookkeep-postgres pg_dump -U bookkeep bookkeep_db > backup.sql

# Reset
docker-compose down -v
docker-compose up -d postgres

# Restore
docker exec -i bookkeep-postgres psql -U bookkeep bookkeep_db < backup.sql
```

---

## Production Checklist

### Before Deployment

Copy this checklist and track progress:
- [ ] All migrations tested locally
- [ ] Rollback tested: `alembic downgrade -1`
- [ ] No breaking schema changes without data migration
- [ ] Connection pool sized for expected load
- [ ] `pool_pre_ping=True` enabled
- [ ] Database backup scheduled

### Monitoring Queries

```sql
-- Find slow queries
SELECT query, calls, mean_time, total_time
FROM pg_stat_statements
ORDER BY total_time DESC
LIMIT 10;

-- Connection count
SELECT count(*) FROM pg_stat_activity 
WHERE datname = 'bookkeep_db';

-- Lock monitoring
SELECT * FROM pg_locks WHERE NOT granted;
```

### Index Verification

```sql
-- Unused indexes (candidates for removal)
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE idx_scan = 0;

-- Missing indexes (sequential scans on large tables)
SELECT relname, seq_scan, seq_tup_read, idx_scan, idx_tup_fetch
FROM pg_stat_user_tables
WHERE seq_scan > idx_scan AND n_live_tup > 10000;
```

---

## Troubleshooting

### "Connection refused" Error

1. Check PostgreSQL is running: `docker-compose ps`
2. Verify DATABASE_URL format: `postgresql://user:pass@host:5432/db`
3. Check network connectivity: `docker network ls`

### "Stale connection" Errors

Already mitigated by `pool_pre_ping=True` and `pool_recycle=1800`. If still occurring:

```python
# Reduce recycle time
pool_recycle=600  # 10 minutes
```

### Slow Queries After Migration

1. Run `ANALYZE` on affected tables: `ANALYZE books;`
2. Check for missing indexes on new columns
3. Verify query plans with `EXPLAIN ANALYZE`

Iterate-until-pass pattern:
1. Identify slow query from logs
2. Run `EXPLAIN ANALYZE` on the query
3. Add index or rewrite query
4. Verify improvement with `EXPLAIN ANALYZE`
5. Repeat until query time acceptable