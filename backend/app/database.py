from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from pathlib import Path

# Database URL from environment variable or default
# Use SQLite for single-container deployments, PostgreSQL for multi-container
default_db_path = os.getenv(
    "DATABASE_URL",
    None
)

if default_db_path is None:
    # Determine project root (go up from backend/app to project root)
    # This file is at backend/app/database.py, so project root is 2 levels up
    # In Docker: /app/backend/app/database.py -> /app
    # Locally: backend/app/database.py -> project root
    project_root = Path(__file__).parent.parent.parent
    data_dir = project_root / "data"
    data_dir.mkdir(exist_ok=True)  # Create data directory if it doesn't exist
    db_path = data_dir / "bookhound.db"
    # Use absolute path for SQLite to avoid path issues
    DATABASE_URL = f"sqlite:///{db_path.absolute()}"
else:
    DATABASE_URL = default_db_path

# SQLite needs special configuration
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={
            "check_same_thread": False,  # Needed for SQLite with multiple threads
            "timeout": 30,  # Wait up to 30 seconds for locks
        },
        echo=False
    )
    
    # Enable WAL mode for better concurrent access
    from sqlalchemy import event
    
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")  # 30 second timeout
        cursor.close()
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

