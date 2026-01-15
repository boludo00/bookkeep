#!/usr/bin/env python3
"""
Seed script to populate database with popular books and series from Hardcover API.
This creates a seed database that can be shipped with the Docker image.
"""
import os
import sys
import asyncio
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal, engine, Base
from app.models import Book, Series
from app.routers.hardcover import execute_graphql
from app.routers.settings import get_hardcover_token
import structlog
from pathlib import Path

logger = structlog.get_logger()

# Ensure data directory exists
project_root = Path(__file__).parent.parent.parent
data_dir = project_root / "data"
data_dir.mkdir(exist_ok=True)

# Run Alembic migrations
try:
    from alembic.config import Config
    from alembic import command
    # alembic.ini is in the backend directory (parent of scripts)
    backend_dir = Path(__file__).parent.parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")
    logger.info("alembic_migrations_applied")
except Exception as e:
    logger.warning("alembic_migration_failed", error=str(e), message="Continuing anyway...")
    # Fallback: create tables if migrations fail
    Base.metadata.create_all(bind=engine)

async def fetch_books_batch(query: str, variables: dict, db: Session):
    """Fetch a batch of books using a GraphQL query"""
    try:
        result = await execute_graphql(query, variables, db=db)
        books = result.get("books", [])
        logger.info(f"Fetched {len(books)} books", query_vars=variables)
        return books
    except Exception as e:
        logger.error("Failed to fetch books batch", error=str(e), variables=variables)
        return []

async def fetch_popular_books(total_limit: int = 5000):
    """Fetch popular books from Hardcover API using multiple queries to bypass 1000 limit"""
    db = SessionLocal()
    try:
        token, _ = get_hardcover_token(db)
        if not token:
            logger.warning("No Hardcover token available, skipping seed data fetch")
            return []
    finally:
        pass  # Keep db open for queries
    
    all_books = []
    seen_ids = set()
    
    # Strategy: Fetch books with different criteria and ordering to get variety
    # Each query gets up to 1000 books, we'll deduplicate
    # We'll use different queries for different order_by strategies
    
    queries = [
        # Highest rated with many ratings (prioritize rating)
        {
            "query": """
            query PopularBooks($limit: Int!, $minRatings: Int!) {
              books(
                order_by: [{rating: desc_nulls_last}, {ratings_count: desc_nulls_last}],
                limit: $limit,
                where: {ratings_count: {_gte: $minRatings}}
              ) {
                id title slug release_year release_date pages description cached_image cached_contributors
                rating ratings_count users_count activities_count
                book_series { series { id name } position }
                contributions { author { id name slug } }
                taggings(limit: 10) { tag { tag } }
              }
            }
            """,
            "variables": {"minRatings": 1000, "limit": 1000},
            "name": "highly_rated_popular"
        },
        # Very popular books (prioritize ratings_count)
        {
            "query": """
            query PopularBooks($limit: Int!, $minRatings: Int!) {
              books(
                order_by: [{ratings_count: desc_nulls_last}, {rating: desc_nulls_last}],
                limit: $limit,
                where: {ratings_count: {_gte: $minRatings}}
              ) {
                id title slug release_year release_date pages description cached_image cached_contributors
                rating ratings_count users_count activities_count
                book_series { series { id name } position }
                contributions { author { id name slug } }
                taggings(limit: 10) { tag { tag } }
              }
            }
            """,
            "variables": {"minRatings": 500, "limit": 1000},
            "name": "very_popular"
        },
        # Popular books by user count
        {
            "query": """
            query PopularBooks($limit: Int!, $minRatings: Int!) {
              books(
                order_by: [{users_count: desc_nulls_last}, {rating: desc_nulls_last}],
                limit: $limit,
                where: {ratings_count: {_gte: $minRatings}}
              ) {
                id title slug release_year release_date pages description cached_image cached_contributors
                rating ratings_count users_count activities_count
                book_series { series { id name } position }
                contributions { author { id name slug } }
                taggings(limit: 10) { tag { tag } }
              }
            }
            """,
            "variables": {"minRatings": 200, "limit": 1000},
            "name": "popular_by_users"
        },
        # Well-rated books
        {
            "query": """
            query PopularBooks($limit: Int!, $minRatings: Int!) {
              books(
                order_by: [{rating: desc_nulls_last}, {ratings_count: desc_nulls_last}],
                limit: $limit,
                where: {ratings_count: {_gte: $minRatings}}
              ) {
                id title slug release_year release_date pages description cached_image cached_contributors
                rating ratings_count users_count activities_count
                book_series { series { id name } position }
                contributions { author { id name slug } }
                taggings(limit: 10) { tag { tag } }
              }
            }
            """,
            "variables": {"minRatings": 100, "limit": 1000},
            "name": "well_rated"
        },
        # Books with decent activity
        {
            "query": """
            query PopularBooks($limit: Int!, $minRatings: Int!) {
              books(
                order_by: [{ratings_count: desc_nulls_last}, {users_count: desc_nulls_last}],
                limit: $limit,
                where: {ratings_count: {_gte: $minRatings}}
              ) {
                id title slug release_year release_date pages description cached_image cached_contributors
                rating ratings_count users_count activities_count
                book_series { series { id name } position }
                contributions { author { id name slug } }
                taggings(limit: 10) { tag { tag } }
              }
            }
            """,
            "variables": {"minRatings": 50, "limit": 1000},
            "name": "decent_activity"
        },
    ]
    
    for query_config in queries:
        if len(all_books) >= total_limit:
            break
            
        logger.info(f"Fetching batch: {query_config['name']}")
        # Adjust limit based on how many we still need
        variables = query_config["variables"].copy()
        variables["limit"] = min(1000, total_limit - len(all_books))
        
        batch = await fetch_books_batch(
            query_config["query"],
            variables,
            db=db
        )
        
        # Deduplicate by hardcover_id
        for book in batch:
            book_id = book.get("id")
            if book_id and book_id not in seen_ids:
                seen_ids.add(book_id)
                all_books.append(book)
        
        logger.info(f"Total unique books so far: {len(all_books)}")
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)
    
    db.close()
    logger.info(f"Fetched {len(all_books)} unique books total")
    return all_books

def transform_to_db_book(hc_book: dict) -> dict:
    """Transform Hardcover book to database Book model"""
    authors = []
    author_id = None
    if hc_book.get("contributions"):
        authors = [c["author"]["name"] for c in hc_book["contributions"] if c.get("author", {}).get("name")]
        # Extract first author's ID from contributions
        if hc_book["contributions"] and hc_book["contributions"][0].get("author", {}).get("id"):
            author_id = hc_book["contributions"][0]["author"]["id"]
    elif hc_book.get("cached_contributors"):
        authors = [c.get("author", {}).get("name") or c.get("name", "") for c in hc_book["cached_contributors"]]
    
    author = ", ".join(authors) if authors else "Unknown Author"
    
    # Extract cover URL
    cover_url = None
    if isinstance(hc_book.get("cached_image"), dict):
        cover_url = hc_book["cached_image"].get("url")
    
    # Extract series info
    series = None
    series_id = None
    series_position = None
    if hc_book.get("book_series") and len(hc_book["book_series"]) > 0:
        series_info = hc_book["book_series"][0].get("series", {})
        series = series_info.get("name")
        series_id = series_info.get("id")
        series_position = hc_book["book_series"][0].get("position")
    
    # Extract genres
    genres = []
    if hc_book.get("taggings"):
        genres = [t["tag"]["tag"] for t in hc_book["taggings"] if t.get("tag", {}).get("tag")]
    
    return {
        "title": hc_book.get("title", "Unknown"),
        "author": author,
        "author_id": author_id,  # Store author ID
        "description": hc_book.get("description"),
        "cover_url": cover_url,
        "published_date": hc_book.get("release_date") or str(hc_book.get("release_year", "")),
        "rating": hc_book.get("rating"),
        "page_count": hc_book.get("pages"),
        "hardcover_id": hc_book.get("id"),
        "hardcover_slug": hc_book.get("slug"),
        "series": series,
        "series_id": series_id,
        "series_position": series_position,
        "genres": ", ".join(genres) if genres else None,
        "ratings_count": hc_book.get("ratings_count"),
        "users_count": hc_book.get("users_count"),
        "activities_count": hc_book.get("activities_count"),
        "release_year": hc_book.get("release_year"),
        "is_seed_data": True,
        "last_refreshed": datetime.now(),
    }

async def seed_database():
    """Main seed function"""
    db: Session = SessionLocal()
    try:
        logger.info("Starting database seed...")
        
        # Fetch popular books (using multiple queries to bypass 1000 limit)
        logger.info("Fetching popular books from Hardcover API...")
        books_data = await fetch_popular_books(total_limit=5000)
        
        if not books_data:
            logger.warning("No books fetched, cannot seed database")
            return
        
        logger.info(f"Fetched {len(books_data)} books, inserting into database...")
        
        inserted = 0
        updated = 0
        skipped = 0
        
        for hc_book in books_data:
            hardcover_id = hc_book.get("id")
            if not hardcover_id:
                skipped += 1
                continue
            
            # Check if book already exists
            existing = db.query(Book).filter(Book.hardcover_id == hardcover_id).first()
            
            book_data = transform_to_db_book(hc_book)
            
            if existing:
                # Update existing book
                for key, value in book_data.items():
                    setattr(existing, key, value)
                existing.is_seed_data = True
                existing.last_refreshed = datetime.now()
                updated += 1
            else:
                # Create new book
                db_book = Book(**book_data)
                db.add(db_book)
                inserted += 1
        
        db.commit()
        logger.info(
            "Books seed complete",
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            total=len(books_data)
        )
        
        # Now fetch and store series data
        logger.info("Fetching series data...")
        await seed_series_data(db, books_data)
        
        logger.info("Database seed complete")
        
    except Exception as e:
        logger.error("Error seeding database", error=str(e))
        db.rollback()
        raise
    finally:
        db.close()

async def seed_series_data(db: Session, books_data: list):
    """Fetch and store series information for books that have series"""
    # Collect unique series IDs from books
    series_ids = set()
    for hc_book in books_data:
        if hc_book.get("book_series") and len(hc_book["book_series"]) > 0:
            series_id = hc_book["book_series"][0].get("series", {}).get("id")
            if series_id:
                series_ids.add(series_id)
    
    if not series_ids:
        logger.info("No series found in books data")
        return
    
    logger.info(f"Found {len(series_ids)} unique series, fetching details...")
    
    # Fetch series details from API in batches
    all_series = []
    series_ids_list = list(series_ids)
    batch_size = 50  # Fetch 50 series at a time
    
    for i in range(0, len(series_ids_list), batch_size):
        batch_ids = series_ids_list[i:i + batch_size]
        
        query = """
        query GetSeries($ids: [Int!]!) {
          series(where: {id: {_in: $ids}}) {
            id
            name
            books_count
          }
        }
        """
        
        try:
            result = await execute_graphql(query, {"ids": batch_ids}, db=db)
            series_batch = result.get("series", [])
            all_series.extend(series_batch)
            logger.info(f"Fetched {len(series_batch)} series (batch {i//batch_size + 1})")
            await asyncio.sleep(0.5)  # Rate limiting
        except Exception as e:
            logger.error(f"Failed to fetch series batch", error=str(e), batch_ids=batch_ids)
    
    # Store series in database
    inserted = 0
    updated = 0
    
    for series_data in all_series:
        series_id = series_data.get("id")
        if not series_id:
            continue
        
        # Check if series already exists
        existing = db.query(Series).filter(Series.hardcover_id == series_id).first()
        
        series_dict = {
            "hardcover_id": series_id,
            "name": series_data.get("name", "Unknown Series"),
            "books_count": series_data.get("books_count"),
            "is_seed_data": True,
            "last_refreshed": datetime.now(),
        }
        
        if existing:
            # Update existing series
            for key, value in series_dict.items():
                setattr(existing, key, value)
            updated += 1
        else:
            # Create new series
            db_series = Series(**series_dict)
            db.add(db_series)
            inserted += 1
    
    db.commit()
    logger.info(
        "Series seed complete",
        inserted=inserted,
        updated=updated,
        total=len(all_series)
    )

def main():
    """Entry point for script execution"""
    asyncio.run(seed_database())

if __name__ == "__main__":
    main()

