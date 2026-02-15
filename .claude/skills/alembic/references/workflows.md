# Alembic Workflows Reference

## Contents
- Creating New Migrations
- Deploying Migrations
- Troubleshooting
- Migration Checklist

## Creating New Migrations

### Workflow: Add New Model Field

1. Update the model in `backend/app/models.py`:

```python
# In backend/app/models.py
class User(Base):
    __tablename__ = "users"
    # ... existing fields ...
    new_permission = Column(Boolean, default=True)  # Add new field
```

2. Generate migration:

```bash
cd backend
alembic revision --autogenerate -m "add_new_permission_to_users"
```

3. Edit the generated migration to add idempotency checks:

```python
def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns

def upgrade():
    if not column_exists('users', 'new_permission'):
        op.add_column('users', sa.Column('new_permission', sa.Boolean(), 
                      nullable=True, server_default='true'))

def downgrade():
    if column_exists('users', 'new_permission'):
        op.drop_column('users', 'new_permission')
```

4. Run the migration:

```bash
alembic upgrade head
```

5. Validate: `alembic current` should show the new revision

### Workflow: Add New Table

1. Create model in `backend/app/models.py`
2. Import model in `backend/alembic/env.py`:

```python
from app.models import User, Book, BookRequest, AppSettings, NewModel  # Add import
```

3. Generate and edit migration (add table_exists/index_exists checks)
4. Apply with `alembic upgrade head`

## Deploying Migrations

### Docker Deployment

Migrations run automatically on container start via `main.py`:

```python
# backend/main.py startup
from alembic.config import Config
from alembic import command

alembic_cfg = Config("alembic.ini")
command.upgrade(alembic_cfg, "head")
```

### Manual Deployment

```bash
# SSH into server
cd /path/to/bookkeep/backend
export DATABASE_URL=postgresql://user:pass@host:5432/db
alembic upgrade head
```

### Rollback Procedure

```bash
# Check current state
alembic current

# Roll back one migration
alembic downgrade -1

# Roll back to specific revision
alembic downgrade 021
```

## Troubleshooting

### Migration Already Applied Error

```
alembic.util.exc.CommandError: Target database is not up to date
```

**Solution:** The database has migrations that autogenerate doesn't recognize.

```bash
alembic stamp head  # Mark current state as up to date
alembic upgrade head  # Apply any new migrations
```

### Column Already Exists Error

```
sqlalchemy.exc.OperationalError: column "new_field" of relation "users" already exists
```

**Solution:** Add existence check to migration (see patterns.md).

### Foreign Key Constraint Error

```
sqlalchemy.exc.IntegrityError: insert or update on table ... violates foreign key constraint
```

**Solution:** Ensure referenced table exists first. Check migration ordering.

### SQLite Batch Alter Error

```
NotImplementedError: No support for ALTER of constraints in SQLite
```

**Solution:** Use `batch_alter_table` context manager for all ALTER operations on SQLite.

## Migration Checklist

Copy this checklist when creating migrations:

```markdown
- [ ] Model updated in `backend/app/models.py`
- [ ] Model imported in `backend/alembic/env.py` if new table
- [ ] Migration generated with `alembic revision --autogenerate`
- [ ] File renamed with correct numeric prefix (check last migration number)
- [ ] Added idempotency helpers (table_exists, column_exists, index_exists)
- [ ] Wrapped operations in existence checks
- [ ] Used batch_alter_table for SQLite compatibility
- [ ] Implemented symmetric downgrade
- [ ] Tested locally: `alembic upgrade head`
- [ ] Tested rollback: `alembic downgrade -1` then `alembic upgrade head`
```

### Naming Convention

Migrations use numeric prefixes for ordering:

```
001_add_seed_data_columns.py
002_add_series_id_to_books.py
...
030_add_api_key_to_download_clients.py
```

When creating a new migration, check the last number and increment:

```bash
ls backend/alembic/versions/*.py | tail -1
# 030_add_api_key_to_download_clients.py
# Next migration should be 031_...
```

### Validation Feedback Loop

1. Run migration: `alembic upgrade head`
2. Check status: `alembic current`
3. If errors, fix migration file
4. Rollback if needed: `alembic downgrade -1`
5. Repeat until `alembic upgrade head` succeeds
6. Test rollback: `alembic downgrade -1`
7. Only commit when both upgrade and downgrade work