# Alembic Patterns Reference

## Contents
- Helper Functions for Idempotency
- Adding Columns
- Creating Tables
- Data Migrations
- WARNING: Common Anti-Patterns

## Helper Functions for Idempotency

Every migration in this project uses existence checks. Add these helpers at the top of each migration file:

```python
from sqlalchemy import inspect

def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()

def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns

def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = [idx["name"] for idx in inspector.get_indexes(table_name)]
    return index_name in indexes
```

## Adding Columns

### Simple Column Addition

From `backend/alembic/versions/028_add_can_download_permission.py`:

```python
def upgrade() -> None:
    if not column_exists('users', 'can_download'):
        op.add_column('users', sa.Column(
            'can_download', 
            sa.Boolean(), 
            nullable=True, 
            server_default='true'
        ))

def downgrade() -> None:
    if column_exists('users', 'can_download'):
        op.drop_column('users', 'can_download')
```

### Column with Data Migration

From `backend/alembic/versions/016_add_per_format_availability.py`:

```python
def upgrade():
    # Step 1: Add nullable column
    if not _column_exists("books", "ebook_available"):
        with op.batch_alter_table('books') as batch_op:
            batch_op.add_column(sa.Column('ebook_available', sa.Boolean(), nullable=True))

    # Step 2: Populate from existing data
    if _column_exists("books", "ebook_available"):
        op.execute("UPDATE books SET ebook_available = is_available WHERE is_available = TRUE")
        op.execute("UPDATE books SET ebook_available = FALSE WHERE ebook_available IS NULL")

    # Step 3: Make non-nullable with default
    with op.batch_alter_table('books') as batch_op:
        batch_op.alter_column(
            'ebook_available',
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        )
```

## Creating Tables

From `backend/alembic/versions/022_add_download_system.py`:

```python
def upgrade():
    if not table_exists('download_clients'):
        op.create_table('download_clients',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('type', sa.String(), nullable=False),
            sa.Column('host', sa.String(), nullable=False),
            sa.Column('port', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), 
                      server_default=sa.text('now()'), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
    
    if not index_exists('download_clients', 'ix_download_clients_name'):
        op.create_index('ix_download_clients_name', 'download_clients', 
                        ['name'], unique=True)
```

## Data Migrations

### Fix NULL Values

From `backend/alembic/versions/007_fix_user_permissions_null_values.py`:

```python
def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'users' not in inspector.get_table_names():
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('users')]
    
    if 'can_request_ebook' in existing_columns:
        op.execute("UPDATE users SET can_request_ebook = TRUE WHERE can_request_ebook IS NULL")

def downgrade():
    # No-op: values can remain as they are
    pass
```

## WARNING: Common Anti-Patterns

### WARNING: Missing Existence Checks

**The Problem:**

```python
# BAD - Fails if run twice or out of order
def upgrade():
    op.add_column('users', sa.Column('new_field', sa.String()))
```

**Why This Breaks:**
1. Migration fails if column already exists (deployed twice, restored from backup)
2. No rollback possible when partially applied
3. Docker restarts may rerun migrations

**The Fix:**

```python
# GOOD - Idempotent, safe to rerun
def upgrade():
    if not column_exists('users', 'new_field'):
        op.add_column('users', sa.Column('new_field', sa.String()))
```

### WARNING: Direct alter_column on SQLite

**The Problem:**

```python
# BAD - SQLite doesn't support most ALTER operations
def upgrade():
    op.alter_column('books', 'title', nullable=False)
```

**Why This Breaks:**
SQLite only supports ADD COLUMN. ALTER COLUMN, DROP COLUMN, and constraints require table recreation.

**The Fix:**

```python
# GOOD - Use batch_alter_table for SQLite compatibility
def upgrade():
    with op.batch_alter_table('books') as batch_op:
        batch_op.alter_column('title', nullable=False)
```

### WARNING: Missing downgrade Implementation

**The Problem:**

```python
# BAD - Cannot rollback
def downgrade():
    pass
```

**Why This Breaks:**
1. Cannot recover from failed deployments
2. No way to test migration rollback
3. Debugging becomes impossible

**The Fix:**

```python
# GOOD - Always implement symmetric downgrade
def downgrade():
    if column_exists('users', 'can_download'):
        op.drop_column('users', 'can_download')