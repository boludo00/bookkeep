#!/usr/bin/env python3
"""
Backfill readarr_book_id for existing book requests that don't have it set.

This script finds all book requests with status='processing' but no readarr_book_id,
then looks them up in Readarr's library and updates the database.

Usage:
    python backend/scripts/backfill_readarr_book_ids.py
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy.orm import Session
from app import models
from app.database import SessionLocal
from app.services.readarr_service import find_book_in_library, get_readarr_client_for_format
from app.routers.readarr import get_readarr_server_for_format
import structlog

logger = structlog.get_logger()


async def backfill_readarr_book_ids():
    """Find and update all processing requests without readarr_book_id."""
    db = SessionLocal()

    try:
        # Find all requests with status='processing' but no readarr_book_id
        requests_to_fix = db.query(models.BookRequest).filter(
            models.BookRequest.status == 'processing',
            models.BookRequest.readarr_book_id.is_(None)
        ).all()

        logger.info("found_requests_to_backfill", count=len(requests_to_fix))

        if not requests_to_fix:
            logger.info("no_requests_need_backfilling")
            return

        updated_count = 0
        not_found_count = 0

        for request in requests_to_fix:
            book = db.query(models.Book).filter(models.Book.id == request.book_id).first()

            if not book:
                logger.warning("book_not_found_for_request", request_id=request.id)
                continue

            # Get the appropriate Readarr server for this format
            readarr_server = get_readarr_server_for_format(request.format, db)

            if not readarr_server:
                logger.warning("no_readarr_server_for_format",
                              format=request.format,
                              request_id=request.id)
                continue

            # Try to find the book in Readarr
            try:
                client = get_readarr_client_for_format(request.format, db)
                if not client:
                    continue

                readarr_book = await find_book_in_library(
                    client,
                    book.hardcover_id,
                    book.isbn
                )

                if readarr_book and readarr_book.get('id'):
                    # Found it! Update the request
                    request.readarr_book_id = readarr_book['id']
                    request.readarr_received = True

                    # Check if it's already available
                    book_file_count = readarr_book.get('statistics', {}).get('bookFileCount', 0)
                    if book_file_count > 0:
                        request.status = 'available'
                        logger.info("backfilled_and_marked_available",
                                   request_id=request.id,
                                   book_title=book.title,
                                   readarr_book_id=readarr_book['id'])
                    else:
                        logger.info("backfilled_readarr_book_id",
                                   request_id=request.id,
                                   book_title=book.title,
                                   readarr_book_id=readarr_book['id'])

                    updated_count += 1
                else:
                    logger.info("book_not_found_in_readarr",
                               request_id=request.id,
                               book_title=book.title,
                               hardcover_id=book.hardcover_id)
                    not_found_count += 1

            except Exception as e:
                logger.error("error_finding_book",
                            request_id=request.id,
                            book_title=book.title,
                            error=str(e))
                not_found_count += 1

        # Commit all changes
        db.commit()

        logger.info("backfill_complete",
                   updated_count=updated_count,
                   not_found_count=not_found_count,
                   total_requests=len(requests_to_fix))

        print(f"\n✅ Backfill complete!")
        print(f"   Updated: {updated_count} requests")
        print(f"   Not found in Readarr: {not_found_count} requests")
        print(f"   Total processed: {len(requests_to_fix)} requests\n")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(backfill_readarr_book_ids())
