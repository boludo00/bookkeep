"""
Prowlarr API client.

Handles communication with Prowlarr for searching releases and managing indexers.
"""
import requests
from typing import List, Dict, Optional
from datetime import datetime, timezone
import structlog
import time

logger = structlog.get_logger()


class ProwlarrClient:
    """
    Prowlarr API client for searching releases.

    Category IDs:
    - 7000-7999: Books (ebooks)
    - 3030: Audiobooks
    """

    # Category constants
    CATEGORY_EBOOK = 7000
    CATEGORY_AUDIOBOOK = 3030

    # Protocol constants
    PROTOCOL_TORRENT = "torrent"
    PROTOCOL_USENET = "usenet"

    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        """
        Initialize Prowlarr client.

        Args:
            base_url: Prowlarr base URL (e.g., "http://prowlarr:9696")
            api_key: Prowlarr API key
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({
            "X-Api-Key": api_key,
            "Accept": "application/json",
        })

    def test_connection(self) -> bool:
        """
        Test connection to Prowlarr.

        Returns:
            True if connection succeeds, False otherwise
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/system/status",
                timeout=self.timeout
            )
            if response.status_code == 200:
                data = response.json()
                logger.info(
                    "prowlarr_connection_success",
                    version=data.get("version"),
                    app_name=data.get("appName")
                )
                return True
            else:
                logger.warning(
                    "prowlarr_connection_failed",
                    status_code=response.status_code
                )
                return False
        except Exception as e:
            logger.warning("prowlarr_connection_error", error=str(e))
            return False

    def search(
        self,
        query: str,
        categories: Optional[List[int]] = None,
        indexer_ids: Optional[List[int]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """
        Search Prowlarr for releases.

        Args:
            query: Search query (book title, ISBN, etc.)
            categories: Category IDs to filter by (e.g., [7000] for ebooks)
            indexer_ids: Specific indexers to search
            limit: Maximum number of results
            offset: Result offset for pagination

        Returns:
            List of release dictionaries from Prowlarr

        Example response item:
        {
            "guid": "https://indexer.com/details/12345",
            "title": "Book Title [EPUB]",
            "indexerId": 1,
            "indexer": "IndexerName",
            "size": 2048000,
            "publishDate": "2024-01-15T10:30:00Z",
            "downloadUrl": "http://prowlarr/1/api?...",
            "infoUrl": "https://indexer.com/details/12345",
            "seeders": 10,
            "leechers": 2,
            "protocol": "torrent",
            "categories": [{"id": 7000, "name": "Books/Ebook"}]
        }
        """
        params = {
            "query": query,
            "limit": limit,
            "offset": offset,
            "type": "search"  # "search" for general, "book" for book-specific
        }

        if categories:
            # Prowlarr expects comma-separated category IDs
            params["categories"] = ",".join(str(c) for c in categories)

        if indexer_ids:
            # Prowlarr expects indexerIds as separate params (e.g., indexerIds=1&indexerIds=2)
            params["indexerIds"] = indexer_ids

        try:
            start_time = time.time()
            response = self.session.get(
                f"{self.base_url}/api/v1/search",
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            results = response.json()

            elapsed = time.time() - start_time
            logger.info(
                "prowlarr_search_complete",
                query=query,
                categories=categories,
                results=len(results),
                elapsed_seconds=round(elapsed, 2)
            )

            return results

        except requests.exceptions.Timeout:
            logger.error(
                "prowlarr_search_timeout",
                query=query,
                timeout=self.timeout
            )
            return []
        except requests.exceptions.HTTPError as e:
            logger.error(
                "prowlarr_search_http_error",
                query=query,
                status_code=e.response.status_code,
                error=str(e)
            )
            return []
        except Exception as e:
            logger.error(
                "prowlarr_search_error",
                query=query,
                error=str(e)
            )
            return []

    def search_with_retry(
        self,
        query: str,
        categories: Optional[List[int]] = None,
        indexer_ids: Optional[List[int]] = None,
        limit: int = 100,
        max_retries: int = 2
    ) -> List[Dict]:
        """
        Search with automatic retry on failure.

        First attempts with categories, then retries without if no results.

        Args:
            query: Search query
            categories: Category IDs to filter by
            indexer_ids: Specific indexers to search
            limit: Maximum number of results
            max_retries: Number of retry attempts

        Returns:
            List of release dictionaries
        """
        # Try with categories first
        results = self.search(
            query=query,
            categories=categories,
            indexer_ids=indexer_ids,
            limit=limit
        )

        # If no results and categories were specified, retry without categories
        if not results and categories:
            logger.info(
                "prowlarr_retry_without_categories",
                query=query,
                original_categories=categories
            )
            results = self.search(
                query=query,
                categories=None,  # Remove category filter
                indexer_ids=indexer_ids,
                limit=limit
            )

        return results

    def get_indexers(self) -> List[Dict]:
        """
        Get list of configured indexers.

        Returns:
            List of indexer dictionaries

        Example response item:
        {
            "id": 1,
            "name": "IndexerName",
            "protocol": "torrent",
            "privacy": "public",
            "enable": true,
            "categories": [{"id": 7000, "name": "Books/Ebook"}]
        }
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/indexer",
                timeout=self.timeout
            )
            response.raise_for_status()
            indexers = response.json()

            logger.info("prowlarr_get_indexers", count=len(indexers))
            return indexers

        except Exception as e:
            logger.error("prowlarr_get_indexers_error", error=str(e))
            return []

    def get_indexer(self, indexer_id: int) -> Optional[Dict]:
        """
        Get details of a specific indexer.

        Args:
            indexer_id: Prowlarr indexer ID

        Returns:
            Indexer dictionary or None if not found
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/indexer/{indexer_id}",
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(
                "prowlarr_get_indexer_error",
                indexer_id=indexer_id,
                error=str(e)
            )
            return None

    def get_indexer_stats(self) -> List[Dict]:
        """
        Get indexer statistics (query counts, failures, etc.).

        Returns:
            List of indexer stats dictionaries
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/indexerstats",
                timeout=self.timeout
            )
            response.raise_for_status()
            stats = response.json()

            logger.info("prowlarr_get_stats", indexers=len(stats.get("indexers", [])))
            return stats.get("indexers", [])

        except Exception as e:
            logger.error("prowlarr_get_stats_error", error=str(e))
            return []

    @staticmethod
    def parse_prowlarr_result(result: Dict) -> Dict:
        """
        Parse a Prowlarr search result into a standardized format.

        Args:
            result: Raw Prowlarr result dictionary

        Returns:
            Parsed result with standardized fields
        """
        # Extract protocol
        protocol = result.get("protocol", "unknown").lower()

        # Parse publish date
        publish_date_str = result.get("publishDate")
        publish_date = None
        if publish_date_str:
            try:
                publish_date = datetime.fromisoformat(
                    publish_date_str.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        # Extract category IDs
        categories = result.get("categories", [])
        category_ids = [c.get("id") for c in categories if isinstance(c, dict)]

        return {
            "guid": result.get("guid"),
            "title": result.get("title", ""),
            "indexer_id": result.get("indexerId"),
            "indexer": result.get("indexer", ""),
            "size_bytes": result.get("size", 0),
            "download_url": result.get("downloadUrl", ""),
            "info_url": result.get("infoUrl"),
            "seeders": result.get("seeders"),
            "leechers": result.get("leechers"),
            "protocol": protocol,
            "category_ids": category_ids,
            "publish_date": publish_date,
            "raw": result,  # Keep original for reference
        }
