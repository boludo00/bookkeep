from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any

import httpx
import structlog
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app import models
from app.cache import get_cached, set_cached, make_cache_key, CACHE_TTL

logger = structlog.get_logger(__name__)


def build_readarr_url(
    hostname: str,
    port: int,
    use_ssl: bool,
    url_base: Optional[str] = None,
) -> str:
    """Build Readarr API URL from components."""
    protocol = "https" if use_ssl else "http"
    base_url = f"{protocol}://{hostname}:{port}"
    if url_base:
        url_base = url_base.strip("/")
        if url_base:
            base_url = f"{base_url}/{url_base}"
    return base_url


class ReadarrClient:
    def __init__(
        self,
        hostname: str,
        port: int,
        use_ssl: bool,
        api_key: str,
        url_base: Optional[str] = None,
        timeout: float = 15.0,
    ) -> None:
        self.hostname = hostname
        self.port = port
        self.use_ssl = use_ssl
        self.api_key = api_key
        self.url_base = url_base
        self.timeout = timeout

    @classmethod
    def from_server(cls, server: models.ReadarrServer, timeout: float = 15.0) -> "ReadarrClient":
        return cls(
            hostname=server.hostname,
            port=server.port,
            use_ssl=server.use_ssl,
            api_key=server.api_key,
            url_base=server.url_base,
            timeout=timeout,
        )

    @property
    def api_url(self) -> str:
        base_url = build_readarr_url(self.hostname, self.port, self.use_ssl, self.url_base)
        return f"{base_url}/api/v1"

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

    @asynccontextmanager
    async def session(self, timeout: Optional[float] = None) -> httpx.AsyncClient:
        async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
            yield client

    async def _get(
        self,
        client: Optional[httpx.AsyncClient],
        path: str,
        params: Optional[dict] = None,
    ) -> httpx.Response:
        if client is None:
            async with self.session() as session_client:
                return await session_client.get(
                    f"{self.api_url}{path}", headers=self.headers, params=params
                )
        return await client.get(f"{self.api_url}{path}", headers=self.headers, params=params)

    async def _post(
        self,
        client: Optional[httpx.AsyncClient],
        path: str,
        payload: dict,
    ) -> httpx.Response:
        if client is None:
            async with self.session() as session_client:
                return await session_client.post(
                    f"{self.api_url}{path}", headers=self.headers, json=payload
                )
        return await client.post(f"{self.api_url}{path}", headers=self.headers, json=payload)

    async def get_library_books(self, client: Optional[httpx.AsyncClient] = None) -> List[Dict[str, Any]]:
        response = await self._get(client, "/book")
        if response.status_code == 200:
            return response.json()
        logger.warning("readarr_library_fetch_failed", status_code=response.status_code)
        return []

    async def get_book_by_isbn(
        self,
        client: Optional[httpx.AsyncClient],
        isbn: str,
    ) -> Optional[dict]:
        try:
            response = await self._get(client, "/book/lookup", params={"term": f"isbn:{isbn}"})
            if response.status_code == 200:
                results = response.json()
                if results:
                    return results[0]
        except Exception as exc:
            logger.debug("readarr_isbn_lookup_failed", isbn=isbn, error=str(exc))
        return None

    async def get_book_by_title_author(
        self,
        client: Optional[httpx.AsyncClient],
        title: str,
        author: str,
    ) -> Optional[dict]:
        try:
            search_term = f"{title} {author}"
            response = await self._get(client, "/book/lookup", params={"term": search_term})
            if response.status_code == 200:
                results = response.json()
                if results:
                    return results[0]
        except Exception as exc:
            logger.debug(
                "readarr_title_author_lookup_failed",
                title=title,
                author=author,
                error=str(exc),
            )
        return None

    async def get_book_by_hardcover_id(
        self,
        client: Optional[httpx.AsyncClient],
        hardcover_id: int,
    ) -> Optional[dict]:
        async def _lookup_by_term(
            term: str,
            exact_event: str,
            no_match_event: str,
        ) -> Optional[dict]:
            response = await self._get(client, "/book/lookup", params={"term": term})
            if response.status_code != 200:
                return None
            results = response.json()
            if not results:
                return None
            for result in results:
                result_foreign_id = result.get("foreignBookId")
                if result_foreign_id and str(result_foreign_id) == str(hardcover_id):
                    logger.info(exact_event, hardcover_id=hardcover_id, result_title=result.get("title"))
                    return result
            logger.warning(
                no_match_event,
                hardcover_id=hardcover_id,
                search_term=term,
                returned_ids=[
                    str(r.get("foreignBookId"))
                    for r in results
                    if r.get("foreignBookId")
                ],
                first_result_title=results[0].get("title") if results else None,
            )
            return None

        try:
            work_match = await _lookup_by_term(
                f"work:{hardcover_id}",
                "readarr_lookup_exact_match",
                "readarr_lookup_no_exact_match",
            )
            if work_match:
                return work_match

            book_match = await _lookup_by_term(
                f"book:{hardcover_id}",
                "readarr_lookup_exact_match_book_prefix",
                "readarr_lookup_no_exact_match_book_prefix",
            )
            if book_match:
                return book_match

            direct_match = await _lookup_by_term(
                str(hardcover_id),
                "readarr_lookup_exact_match_direct",
                "readarr_lookup_no_exact_match_direct",
            )
            if direct_match:
                return direct_match
            logger.debug("readarr_lookup_no_results", hardcover_id=hardcover_id)
        except Exception as exc:
            logger.debug(
                "readarr_hardcover_id_lookup_failed",
                hardcover_id=hardcover_id,
                error=str(exc),
            )
        return None

    async def get_most_popular_edition_id(
        self,
        client: Optional[httpx.AsyncClient],
        hardcover_id: int,
    ) -> Optional[str]:
        try:
            book_data = await self.get_book_by_hardcover_id(client, hardcover_id)
            if not book_data:
                return None

            book_data_foreign_id = book_data.get("foreignBookId")
            if not book_data_foreign_id or str(book_data_foreign_id) != str(hardcover_id):
                logger.warning(
                    "readarr_get_edition_id_mismatch",
                    expected_work_id=hardcover_id,
                    book_data_foreign_id=book_data_foreign_id,
                )
                return None

            editions = book_data.get("editions", [])
            if not editions:
                return None

            most_popular_edition = None
            max_popularity = 0.0
            for edition in editions:
                ratings = edition.get("ratings", {})
                votes = ratings.get("votes", 0) or 0
                value = ratings.get("value", 0.0) or 0.0
                popularity = float(value) * float(votes)
                if popularity > max_popularity:
                    max_popularity = popularity
                    most_popular_edition = edition

            if most_popular_edition:
                foreign_edition_id = most_popular_edition.get("foreignEditionId")
                logger.info(
                    "readarr_found_most_popular_edition",
                    work_id=hardcover_id,
                    edition_id=foreign_edition_id,
                    popularity=max_popularity,
                )
                return str(foreign_edition_id) if foreign_edition_id else None

            first_edition_id = editions[0].get("foreignEditionId")
            logger.info(
                "readarr_using_first_edition_fallback",
                work_id=hardcover_id,
                edition_id=first_edition_id,
            )
            return str(first_edition_id) if first_edition_id else None
        except Exception as exc:
            logger.warning(
                "readarr_get_most_popular_edition_failed",
                hardcover_id=hardcover_id,
                error=str(exc),
            )
        return None

    async def get_author_by_hardcover_id(
        self,
        client: Optional[httpx.AsyncClient],
        hardcover_author_id: int,
    ) -> Optional[dict]:
        try:
            response = await self._get(
                client,
                "/author/lookup",
                params={"term": f"author:{hardcover_author_id}"},
            )

            if response.status_code == 200:
                results = response.json()
                if isinstance(results, list) and results:
                    for result in results:
                        if isinstance(result, dict):
                            if result.get("id"):
                                if str(result.get("foreignAuthorId")) == str(hardcover_author_id):
                                    logger.info(
                                        "readarr_author_found_existing",
                                        hardcover_author_id=hardcover_author_id,
                                        readarr_author_id=result.get("id"),
                                    )
                                    return result
                            else:
                                if str(result.get("foreignAuthorId")) == str(hardcover_author_id):
                                    add_response = await self._post(client, "/author", result)
                                    if add_response.status_code in {200, 201}:
                                        added_author = add_response.json()
                                        logger.info(
                                            "readarr_author_added",
                                            hardcover_author_id=hardcover_author_id,
                                            readarr_author_id=added_author.get("id"),
                                        )
                                        return added_author
                                    logger.warning(
                                        "readarr_author_add_failed",
                                        status=add_response.status_code,
                                        response=add_response.text[:200],
                                    )
                    first_result = results[0] if isinstance(results[0], dict) else None
                    if first_result and first_result.get("id"):
                        logger.info(
                            "readarr_author_found_first_existing",
                            hardcover_author_id=hardcover_author_id,
                            readarr_author_id=first_result.get("id"),
                        )
                        return first_result
                    return first_result
                if isinstance(results, dict):
                    if results.get("id"):
                        logger.info(
                            "readarr_author_found_dict_existing",
                            hardcover_author_id=hardcover_author_id,
                            readarr_author_id=results.get("id"),
                        )
                        return results
                    add_response = await self._post(client, "/author", results)
                    if add_response.status_code in {200, 201}:
                        added_author = add_response.json()
                        logger.info(
                            "readarr_author_added_from_dict",
                            hardcover_author_id=hardcover_author_id,
                            readarr_author_id=added_author.get("id"),
                        )
                        return added_author
            else:
                logger.warning(
                    "readarr_author_lookup_failed",
                    status=response.status_code,
                    response_text=response.text[:500],
                    hardcover_author_id=hardcover_author_id,
                )
        except Exception as exc:
            logger.error(
                "readarr_hardcover_author_lookup_exception",
                hardcover_author_id=hardcover_author_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
        return None

    async def lookup_or_create_author(
        self,
        client: Optional[httpx.AsyncClient],
        author_name: str,
        hardcover_author_id: Optional[int] = None,
    ) -> Optional[int]:
        try:
            lookup_response = await self._get(
                client,
                "/author/lookup",
                params={"term": author_name},
            )
            if lookup_response.status_code == 200:
                authors = lookup_response.json()
                if authors:
                    author_id = authors[0].get("id")
                    if author_id:
                        logger.info("readarr_author_found", author_name=author_name, author_id=author_id)
                        return int(author_id)

            if hardcover_author_id:
                author_data = await self.get_author_by_hardcover_id(client, hardcover_author_id)
                if author_data and author_data.get("id"):
                    logger.info(
                        "readarr_author_found_by_hardcover_id",
                        hardcover_author_id=hardcover_author_id,
                        readarr_author_id=author_data["id"],
                    )
                    return int(author_data["id"])

            logger.warning(
                "readarr_author_not_found",
                author_name=author_name,
                hardcover_author_id=hardcover_author_id,
            )
            return None
        except Exception as exc:
            logger.warning("readarr_author_lookup_error", author_name=author_name, error=str(exc))
            return None

    async def get_author_by_id(
        self,
        client: Optional[httpx.AsyncClient],
        author_id: int,
    ) -> Optional[dict]:
        try:
            response = await self._get(client, f"/author/{author_id}")
            if response.status_code == 200:
                return response.json()
            logger.warning("readarr_author_fetch_failed", author_id=author_id, status=response.status_code)
        except Exception as exc:
            logger.warning("readarr_author_fetch_error", author_id=author_id, error=str(exc))
        return None

    async def run_book_search_command(
        self,
        client: Optional[httpx.AsyncClient],
        book_id: int,
    ) -> None:
        try:
            await self._post(client, "/command", {"name": "BookSearch", "bookIds": [book_id]})
            logger.info("readarr_search_command_triggered", book_id=book_id)
        except Exception as exc:
            logger.warning("readarr_search_command_failed", book_id=book_id, error=str(exc))

    async def find_book_in_library(
        self,
        client: Optional[httpx.AsyncClient],
        hardcover_id: int,
    ) -> Optional[Dict[str, Any]]:
        try:
            books = await self.get_library_books(client)
            for book in books:
                foreign_id = book.get("foreignBookId")
                if foreign_id and str(foreign_id) == str(hardcover_id):
                    logger.info(
                        "readarr_book_found_in_library",
                        hardcover_id=hardcover_id,
                        readarr_book_id=book.get("id"),
                        title=book.get("title"),
                    )
                    return book
            return None
        except Exception as exc:
            logger.error(
                "readarr_library_fetch_error",
                hardcover_id=hardcover_id,
                error=str(exc),
            )
            return None

    async def check_queue(
        self,
        client: Optional[httpx.AsyncClient],
        book_ids: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        try:
            url = "/queue/details"
            params = None
            if book_ids:
                params = {"bookIds": ",".join(str(bid) for bid in book_ids)}
            response = await self._get(client, url, params=params)
            if response.status_code == 200:
                queue_items = response.json()
                return queue_items if isinstance(queue_items, list) else []
            logger.warning("readarr_queue_check_failed", status_code=response.status_code)
        except Exception as exc:
            logger.warning("readarr_queue_check_error", error=str(exc))
        return []

    async def check_history(
        self,
        client: Optional[httpx.AsyncClient],
        book_ids: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        try:
            params = {"page": 1, "pageSize": 100}
            if book_ids:
                params["bookIds"] = ",".join(str(bid) for bid in book_ids)
            response = await self._get(client, "/history", params=params)
            if response.status_code == 200:
                history_data = response.json()
                if isinstance(history_data, dict) and "records" in history_data:
                    records = history_data["records"]
                    return [
                        record for record in records
                        if record.get("eventType") == "downloadFolderImported"
                        or record.get("data", {}).get("files", [])
                    ]
                return history_data if isinstance(history_data, list) else []
            logger.warning("readarr_history_check_failed", status_code=response.status_code)
        except Exception as exc:
            logger.warning("readarr_history_check_error", error=str(exc))
        return []

    async def check_book_download_status(
        self,
        client: Optional[httpx.AsyncClient],
        readarr_book_id: int,
    ) -> Dict[str, Any]:
        queue_items = await self.check_queue(client, [readarr_book_id])
        if queue_items:
            queue_item = queue_items[0]
            progress = None
            if queue_item.get("sizeleft") is not None and queue_item.get("size"):
                size = queue_item.get("size", 0)
                sizeleft = queue_item.get("sizeleft", 0)
                if size > 0:
                    progress = round((1 - sizeleft / size) * 100, 1)
            return {"status": "downloading", "progress": progress, "details": queue_item}

        try:
            response = await self._get(client, f"/book/{readarr_book_id}")
            if response.status_code == 200:
                book_data = response.json()
                statistics = book_data.get("statistics", {})
                book_file_count = statistics.get("bookFileCount", 0)
                size_on_disk = statistics.get("sizeOnDisk", 0)
                if book_file_count > 0 or size_on_disk > 0:
                    return {
                        "status": "downloaded",
                        "file_count": book_file_count,
                        "size_on_disk": size_on_disk,
                        "details": book_data,
                    }
            elif response.status_code == 404:
                logger.warning("readarr_book_not_found", readarr_book_id=readarr_book_id)
            else:
                logger.warning(
                    "readarr_book_request_failed",
                    readarr_book_id=readarr_book_id,
                    status_code=response.status_code,
                    response_text=response.text[:200],
                )
        except Exception as exc:
            logger.warning("check_book_direct_error", readarr_book_id=readarr_book_id, error=str(exc))

        history_items = await self.check_history(client, [readarr_book_id])
        for item in history_items:
            if item.get("eventType") == "downloadFolderImported":
                return {"status": "downloaded", "details": item}

        return {"status": "unknown", "details": None}


class ReadarrService:
    def __init__(self, readarr_client: ReadarrClient, db: Session):
        self.readarr_client = readarr_client
        self.db = db

    @staticmethod
    def _normalize_match_value(value: Optional[str]) -> str:
        if not value:
            return ""
        return "".join(ch for ch in value.lower() if ch.isalnum() or ch.isspace()).strip()

    @staticmethod
    def _extract_search_ids(
        result: Dict[str, Any]
    ) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[dict]]:
        book_data = result.get("book")
        if not isinstance(book_data, dict):
            return None, None, None, None, None
        foreign_book_id = book_data.get("foreignBookId") or book_data.get("foreignId")
        author_foreign_id = None
        author_data = book_data.get("author") or {}
        if isinstance(author_data, dict):
            author_foreign_id = author_data.get("foreignAuthorId")
        title = book_data.get("title")
        author_name = (
            book_data.get("authorName")
            or author_data.get("authorName")
            or author_data.get("name")
        )
        return (
            str(foreign_book_id) if foreign_book_id is not None else None,
            str(author_foreign_id) if author_foreign_id is not None else None,
            title,
            author_name,
            book_data,
        )

    @staticmethod
    def _is_audiobook_format(edition_format: Optional[str]) -> bool:
        if not edition_format:
            return False
        return "audio" in edition_format.lower()

    def get_readarr_settings(self, server: models.ReadarrServer) -> tuple[int, str]:
        if server.is_audiobook:
            quality_profile_id = server.audiobook_quality_profile_id
            root_folder = server.audiobook_root_folder
        else:
            quality_profile_id = server.ebook_quality_profile_id
            root_folder = server.ebook_root_folder
        if not quality_profile_id or not root_folder:
            raise ValueError(
                f"Quality profile and root folder must be configured for server '{server.name}'"
            )
        return int(quality_profile_id), root_folder

    async def get_hardcover_editions(
        self,
        hardcover_id: int,
    ) -> Optional[List[Dict[str, Any]]]:
        try:
            from app.routers.hardcover import execute_graphql

            query = """
            query GetBookEditions($id: Int!) {
              books_by_pk(id: $id) {
                id
                title
                editions(order_by: {score: desc}) {
                  id
                  title
                  score
                  state
                  source
                  language_id
                  isbn_13
                  isbn_10
                  edition_information
                  edition_format
                  rating
                  publisher_id
                  physical_information
                  pages
                  original_book_id
                }
              }
            }
            """

            result = await execute_graphql(query, {"id": hardcover_id}, db=self.db)
            book_data = result.get("books_by_pk")

            if not book_data:
                logger.warning("hardcover_book_not_found", hardcover_id=hardcover_id)
                return None

            editions = book_data.get("editions", [])
            if not editions:
                logger.warning(
                    "hardcover_no_editions",
                    hardcover_id=hardcover_id,
                    book_title=book_data.get("title"),
                )
                return None

            logger.info(
                "hardcover_editions_fetched",
                hardcover_id=hardcover_id,
                editions_count=len(editions),
                book_title=book_data.get("title"),
                top_edition_score=editions[0].get("score") if editions else None,
                top_edition_id=editions[0].get("id") if editions else None,
            )
            return editions
        except Exception as exc:
            logger.warning("hardcover_get_editions_failed", hardcover_id=hardcover_id, error=str(exc))
            return None

    async def determine_author_id(
        self,
        client: httpx.AsyncClient,
        book: models.Book,
    ) -> tuple[int, Optional[dict]]:
        author_id = None
        book_data = None

        if book.author_id:
            author_data = await self.readarr_client.get_author_by_hardcover_id(client, book.author_id)
            if author_data and author_data.get("id"):
                author_id = int(author_data["id"])
                logger.info(
                    "readarr_author_exists",
                    hardcover_author_id=book.author_id,
                    readarr_author_id=author_id,
                )
            else:
                logger.info(
                    "readarr_trying_hardcover_author_id_directly",
                    hardcover_author_id=book.author_id,
                )
                author_id = book.author_id

        if not author_id and book.hardcover_id:
            book_data = await self.readarr_client.get_book_by_hardcover_id(client, book.hardcover_id)
            if book_data:
                if book_data.get("authorId"):
                    author_id = int(book_data["authorId"])
                elif book_data.get("author", {}).get("id"):
                    author_id = int(book_data["author"]["id"])

        if not author_id:
            if book.isbn:
                book_data = await self.readarr_client.get_book_by_isbn(client, book.isbn)
            else:
                book_data = await self.readarr_client.get_book_by_title_author(client, book.title, book.author)
            if book_data:
                if book_data.get("authorId"):
                    author_id = int(book_data["authorId"])
                elif book_data.get("author", {}).get("id"):
                    author_id = int(book_data["author"]["id"])

        if not author_id and book.author_id:
            author_id = book.author_id
            logger.info("readarr_using_hardcover_author_id_directly", hardcover_author_id=book.author_id)

        if not author_id:
            logger.error(
                "readarr_no_author_id",
                book_id=book.id,
                book_title=book.title,
                hardcover_id=book.hardcover_id,
                author_id=book.author_id,
            )
            raise HTTPException(
                status_code=400,
                detail=f"Could not determine author ID for '{book.author}'",
            )

        return author_id, book_data

    async def ensure_book_data_for_edition(
        self,
        client: httpx.AsyncClient,
        book: models.Book,
        book_data: Optional[dict],
    ) -> Optional[dict]:
        if book_data or not book.hardcover_id:
            return book_data

        book_data = await self.readarr_client.get_book_by_hardcover_id(client, book.hardcover_id)
        logger.info(
            "readarr_fetched_book_data_for_edition",
            hardcover_id=book.hardcover_id,
            has_foreign_edition_id=bool(book_data.get("foreignEditionId") if book_data else False),
            has_editions=bool(book_data.get("editions") if book_data else False),
        )

        if not book_data and book.title:
            try:
                logger.info("readarr_trying_search_endpoint", book_title=book.title)
                search_response = await client.get(
                    f"{self.readarr_client.api_url}/search",
                    headers=self.readarr_client.headers,
                    params={"term": book.title},
                )
                if search_response.status_code == 200:
                    search_results = search_response.json()
                    for result in search_results or []:
                        result_foreign_id = result.get("foreignId") or (
                            result.get("book", {}).get("foreignBookId") if result.get("book") else None
                        )
                        if result_foreign_id and str(result_foreign_id) == str(book.hardcover_id):
                            logger.info(
                                "readarr_search_found_exact_match",
                                hardcover_id=book.hardcover_id,
                                search_term=book.title,
                            )
                            book_data = result.get("book") or result
                            break
            except Exception as exc:
                logger.debug("readarr_search_fallback_failed", title=book.title, error=str(exc))

        return book_data

    async def select_edition_id(
        self,
        client: httpx.AsyncClient,
        book: models.Book,
        server: models.ReadarrServer,
        format_type: str,
        book_data: Optional[dict],
        edition_id_override: Optional[int] = None,
    ) -> Optional[str]:
        edition_id = None
        wants_audiobook = server.is_audiobook or format_type == "audiobook"

        if edition_id_override:
            edition_id = str(edition_id_override)
            logger.info(
                "readarr_using_requested_edition_id",
                book_id=book.id,
                hardcover_id=book.hardcover_id,
                edition_id=edition_id,
            )
            return edition_id

        if wants_audiobook and book.default_audio_edition_id:
            edition_id = str(book.default_audio_edition_id)
            logger.info(
                "readarr_using_default_audio_edition_id",
                book_id=book.id,
                hardcover_id=book.hardcover_id,
                edition_id=edition_id,
            )
        elif not wants_audiobook and book.default_ebook_edition_id:
            edition_id = str(book.default_ebook_edition_id)
            logger.info(
                "readarr_using_default_ebook_edition_id",
                book_id=book.id,
                hardcover_id=book.hardcover_id,
                edition_id=edition_id,
            )
        elif book.default_physical_edition_id:
            edition_id = str(book.default_physical_edition_id)
            logger.info(
                "readarr_using_default_physical_edition_id",
                book_id=book.id,
                hardcover_id=book.hardcover_id,
                edition_id=edition_id,
            )
        elif book.default_edition_id:
            edition_id = str(book.default_edition_id)
            logger.info(
                "readarr_using_default_edition_id_fallback",
                book_id=book.id,
                hardcover_id=book.hardcover_id,
                edition_id=edition_id,
            )

        if not edition_id and book.hardcover_id:
            hardcover_editions = await self.get_hardcover_editions(book.hardcover_id)
            if hardcover_editions:
                filtered_editions = [
                    edition for edition in hardcover_editions
                    if self._is_audiobook_format(edition.get("edition_format")) == wants_audiobook
                ]
                candidates = filtered_editions or hardcover_editions
                top_edition = candidates[0]
                edition_id = str(top_edition.get("id"))
                logger.info(
                    "readarr_selected_top_scored_edition_from_hardcover",
                    work_id=book.hardcover_id,
                    edition_id=edition_id,
                    edition_title=top_edition.get("title"),
                    edition_score=top_edition.get("score"),
                    edition_format=top_edition.get("edition_format"),
                    has_isbn13=bool(top_edition.get("isbn_13")),
                    has_isbn10=bool(top_edition.get("isbn_10")),
                )

            if not edition_id:
                if book_data:
                    book_data_foreign_id = book_data.get("foreignBookId")
                    if book_data_foreign_id and str(book_data_foreign_id) == str(book.hardcover_id):
                        if book_data.get("editions"):
                            editions = book_data.get("editions", [])
                            most_popular_edition = None
                            max_popularity = 0.0

                            for edition in editions:
                                ratings = edition.get("ratings", {})
                                votes = ratings.get("votes", 0) or 0
                                value = ratings.get("value", 0.0) or 0.0
                                popularity = float(value) * float(votes)
                                if popularity > max_popularity:
                                    max_popularity = popularity
                                    most_popular_edition = edition

                            if most_popular_edition:
                                edition_id = str(most_popular_edition.get("foreignEditionId", ""))
                                logger.info(
                                    "readarr_found_most_popular_edition_from_readarr",
                                    work_id=book.hardcover_id,
                                    edition_id=edition_id,
                                    popularity=max_popularity,
                                )
                            elif editions:
                                edition_id = str(editions[0].get("foreignEditionId", ""))
                                logger.info(
                                    "readarr_using_first_edition_from_readarr",
                                    work_id=book.hardcover_id,
                                    edition_id=edition_id,
                                )
                        elif book_data.get("foreignEditionId"):
                            edition_id = str(book_data.get("foreignEditionId"))
                            logger.info(
                                "readarr_found_edition_from_book_data",
                                work_id=book.hardcover_id,
                                edition_id=edition_id,
                            )

                if not edition_id:
                    edition_id = await self.readarr_client.get_most_popular_edition_id(
                        client, book.hardcover_id
                    )

        if not edition_id and book.hardcover_id:
            logger.info(
                "readarr_trying_search_endpoint_for_edition",
                hardcover_id=book.hardcover_id,
                book_title=book.title,
            )
            try:
                search_response = await client.get(
                    f"{self.readarr_client.api_url}/search",
                    headers=self.readarr_client.headers,
                    params={"term": book.title},
                )
                if search_response.status_code == 200:
                    search_results = search_response.json()
                    for result in search_results or []:
                        result_foreign_id = result.get("foreignId") or (
                            result.get("book", {}).get("foreignBookId") if result.get("book") else None
                        )
                        if result_foreign_id and str(result_foreign_id) == str(book.hardcover_id):
                            search_book_data = result.get("book") or result
                            if search_book_data.get("foreignEditionId"):
                                edition_id = str(search_book_data.get("foreignEditionId"))
                                logger.info(
                                    "readarr_found_edition_from_search",
                                    hardcover_id=book.hardcover_id,
                                    edition_id=edition_id,
                                )
                                break
                            editions = search_book_data.get("editions", [])
                            if editions:
                                first_edition = editions[0]
                                if first_edition.get("foreignEditionId"):
                                    edition_id = str(first_edition.get("foreignEditionId"))
                                    logger.info(
                                        "readarr_found_edition_from_search_editions",
                                        hardcover_id=book.hardcover_id,
                                        edition_id=edition_id,
                                    )
                                    break
            except Exception as exc:
                logger.debug("readarr_search_endpoint_failed", title=book.title, error=str(exc))

        if not edition_id:
            logger.warning(
                "readarr_no_edition_id_found",
                hardcover_id=book.hardcover_id,
                book_title=book.title,
            )

        return edition_id

    @staticmethod
    def build_add_payload(
        book: models.Book,
        quality_profile_id: int,
        root_folder: str,
        edition_id: Optional[str],
    ) -> dict:
        add_payload = {
            "foreignBookId": str(book.hardcover_id),
            "monitored": True,
            "anyEditionOk": not edition_id,
            "author": {
                "foreignAuthorId": str(book.author_id),
                "qualityProfileId": quality_profile_id,
                "metadataProfileId": 1,
                "rootFolderPath": root_folder,
                "addOptions": {
                    "booksToMonitor": [str(book.hardcover_id)],
                    "monitored": True,
                    "searchForMissingBooks": False,
                },
            },
            "addOptions": {
                "addType": "automatic",
                "searchForNewBook": True,
            },
        }
        if edition_id:
            add_payload["editions"] = [{"foreignEditionId": str(edition_id), "monitored": True}]
        else:
            add_payload["editions"] = []
        return add_payload

    @staticmethod
    def validate_add_payload(add_payload: dict, book: models.Book) -> None:
        if not add_payload.get("anyEditionOk") and not add_payload.get("editions"):
            logger.error(
                "readarr_payload_validation_failed",
                hardcover_id=book.hardcover_id,
                editions_count=len(add_payload.get("editions", [])),
                any_edition_ok=add_payload.get("anyEditionOk"),
            )
            raise HTTPException(
                status_code=500,
                detail=(
                    "Internal error: Failed to build valid payload - "
                    "editions array is empty and anyEditionOk is false"
                ),
            )

    async def find_existing_book(
        self,
        client: httpx.AsyncClient,
        book: models.Book,
    ) -> Optional[dict]:
        if not book.hardcover_id:
            return None
        try:
            lookup_result = await self.readarr_client.get_book_by_hardcover_id(client, book.hardcover_id)
            if lookup_result and lookup_result.get("id"):
                lookup_book_id = lookup_result.get("id")
                lookup_foreign_id = lookup_result.get("foreignBookId")
                if lookup_foreign_id and str(lookup_foreign_id) == str(book.hardcover_id):
                    try:
                        book_by_id_response = await client.get(
                            f"{self.readarr_client.api_url}/book/{lookup_book_id}",
                            headers=self.readarr_client.headers,
                        )
                        if book_by_id_response.status_code == 200:
                            book_in_library = book_by_id_response.json()
                            library_foreign_id = book_in_library.get("foreignBookId")
                            if library_foreign_id and str(library_foreign_id) == str(book.hardcover_id):
                                logger.info(
                                    "readarr_book_already_exists",
                                    hardcover_id=book.hardcover_id,
                                    readarr_book_id=book_in_library.get("id"),
                                    book_title=book.title,
                                )
                                return book_in_library
                            logger.warning(
                                "readarr_book_id_mismatch_in_library",
                                hardcover_id=book.hardcover_id,
                                readarr_book_id=lookup_book_id,
                                library_foreign_id=library_foreign_id,
                                book_title=book.title,
                            )
                    except Exception as exc:
                        logger.debug("readarr_get_book_by_id_failed", book_id=lookup_book_id, error=str(exc))
        except Exception as exc:
            logger.debug("readarr_check_existing_failed", error=str(exc))
        return None

    async def ensure_existing_book_monitored_and_search(
        self,
        client: httpx.AsyncClient,
        existing_book: dict,
        book: models.Book,
        server: models.ReadarrServer,
    ) -> dict:
        readarr_book_id = existing_book.get("id")
        existing_foreign_id = existing_book.get("foreignBookId")
        if not (existing_foreign_id and str(existing_foreign_id) == str(book.hardcover_id)):
            logger.warning(
                "readarr_final_verification_failed",
                hardcover_id=book.hardcover_id,
                readarr_book_id=readarr_book_id,
                readarr_foreign_id=existing_foreign_id,
                book_title=book.title,
            )
            return {}

        logger.info(
            "readarr_book_already_in_readarr",
            book_id=book.id,
            readarr_book_id=readarr_book_id,
            server_id=server.id,
        )

        if not existing_book.get("monitored", False):
            try:
                existing_book["monitored"] = True
                monitor_response = await client.put(
                    f"{self.readarr_client.api_url}/book/{readarr_book_id}",
                    headers=self.readarr_client.headers,
                    json=existing_book,
                )
                if monitor_response.status_code in [200, 202]:
                    logger.info(
                        "readarr_book_now_monitored",
                        readarr_book_id=readarr_book_id,
                        book_title=book.title,
                    )
                else:
                    logger.warning(
                        "readarr_monitor_update_failed",
                        readarr_book_id=readarr_book_id,
                        status_code=monitor_response.status_code,
                    )
            except Exception as exc:
                logger.warning(
                    "readarr_monitor_update_error",
                    readarr_book_id=readarr_book_id,
                    error=str(exc),
                )

        search_triggered = False
        search_status_code = None
        try:
            search_command = {"name": "BookSearch", "bookIds": [readarr_book_id]}
            search_response = await client.post(
                f"{self.readarr_client.api_url}/command",
                headers=self.readarr_client.headers,
                json=search_command,
            )
            search_status_code = search_response.status_code
            if search_response.status_code in [200, 201]:
                search_triggered = True
                logger.info(
                    "readarr_search_triggered_for_existing",
                    readarr_book_id=readarr_book_id,
                    book_title=book.title,
                )
            else:
                logger.warning(
                    "readarr_search_trigger_failed",
                    readarr_book_id=readarr_book_id,
                    status_code=search_response.status_code,
                )
        except Exception as exc:
            logger.warning(
                "readarr_search_trigger_error",
                readarr_book_id=readarr_book_id,
                error=str(exc),
            )

        return {
            "success": True,
            "readarr_book_id": readarr_book_id,
            "readarr_received": True,
            "search_triggered": search_triggered,
            "search_status_code": search_status_code,
            "message": "Book already exists in Readarr - now monitored and searching",
        }

    async def post_add_book_with_retries(
        self,
        client: httpx.AsyncClient,
        add_payload: dict,
        book: models.Book,
    ) -> tuple[httpx.Response, bool, bool, dict]:
        response = await client.post(
            f"{self.readarr_client.api_url}/book",
            headers=self.readarr_client.headers,
            json=add_payload,
        )
        used_any_edition_retry = False
        used_search_retry = False

        if (
            response.status_code >= 400
            and "Sequence contains no matching element" in response.text
            and add_payload.get("editions")
        ):
            retry_payload = {**add_payload, "editions": [], "anyEditionOk": True}
            logger.warning(
                "readarr_add_retry_any_edition",
                book_id=book.id,
                hardcover_id=book.hardcover_id,
                error=response.text,
            )
            response = await client.post(
                f"{self.readarr_client.api_url}/book",
                headers=self.readarr_client.headers,
                json=retry_payload,
            )
            logger.info("readarr_adding_new_book_retry_any_edition")
            used_any_edition_retry = True
            if response.status_code in [200, 201]:
                add_payload = retry_payload

        if (
            response.status_code not in [200, 201]
            and response.status_code >= 400
            and "Sequence contains no matching element" in response.text
        ):
            try:
                search_response = await client.get(
                    f"{self.readarr_client.api_url}/search",
                    headers=self.readarr_client.headers,
                    params={"term": book.title},
                )
                if search_response.status_code == 200:
                    search_results = search_response.json()
                    target_title = self._normalize_match_value(book.title)
                    target_author = self._normalize_match_value(book.author.split(",")[0]) if book.author else ""
                    chosen = None
                    for result in search_results:
                        foreign_id, author_foreign_id, title, author_name, book_data = (
                            self._extract_search_ids(result)
                        )
                        if not foreign_id or not title:
                            continue
                        normalized_title = self._normalize_match_value(title)
                        normalized_author = self._normalize_match_value(author_name)
                        if normalized_title == target_title:
                            if not target_author or not normalized_author or target_author in normalized_author:
                                chosen = (foreign_id, author_foreign_id, title, author_name, book_data)
                                break
                    if not chosen and search_results:
                        foreign_id, author_foreign_id, title, author_name, book_data = (
                            self._extract_search_ids(search_results[0])
                        )
                        if foreign_id:
                            chosen = (foreign_id, author_foreign_id, title, author_name, book_data)
                    if chosen:
                        foreign_id, author_foreign_id, title, author_name, book_data = chosen
                        resolved_author_foreign_id = author_foreign_id
                        if not resolved_author_foreign_id and book.author:
                            lookup_id = await self.readarr_client.lookup_or_create_author(
                                client,
                                book.author.split(",")[0],
                                None,
                            )
                            if lookup_id:
                                author_info = await self.readarr_client.get_author_by_id(client, int(lookup_id))
                                if author_info:
                                    resolved_author_foreign_id = author_info.get("foreignAuthorId")

                        if not book_data:
                            book_data = {}
                        search_payload = {
                            **book_data,
                            "addOptions": add_payload.get("addOptions", {}),
                        }
                        author_payload = search_payload.get("author", {})
                        if not isinstance(author_payload, dict):
                            author_payload = {}
                        if resolved_author_foreign_id:
                            author_payload["foreignAuthorId"] = str(resolved_author_foreign_id)
                        author_payload["qualityProfileId"] = add_payload.get("author", {}).get("qualityProfileId")
                        author_payload["metadataProfileId"] = add_payload.get("author", {}).get("metadataProfileId")
                        author_payload["rootFolderPath"] = add_payload.get("author", {}).get("rootFolderPath")
                        author_payload["addOptions"] = {
                            **add_payload.get("author", {}).get("addOptions", {}),
                            "booksToMonitor": [str(foreign_id)],
                        }
                        search_payload["author"] = author_payload
                        logger.warning(
                            "readarr_add_retry_search_match",
                            book_id=book.id,
                            hardcover_id=book.hardcover_id,
                            foreign_book_id=foreign_id,
                            author_foreign_id=resolved_author_foreign_id,
                            matched_title=title,
                            matched_author=author_name,
                        )
                        response = await client.post(
                            f"{self.readarr_client.api_url}/book",
                            headers=self.readarr_client.headers,
                            json=search_payload,
                        )
                        logger.info("readarr_adding_new_book_retry_search_match")
                        used_search_retry = True
                        if response.status_code in [200, 201]:
                            add_payload = search_payload
            except Exception as exc:
                logger.warning("readarr_add_retry_search_failed", book_id=book.id, error=str(exc))

        return response, used_any_edition_retry, used_search_retry, add_payload

    async def resolve_conflict(
        self,
        client: httpx.AsyncClient,
        book: models.Book,
    ) -> Optional[dict]:
        if not book.hardcover_id:
            return None
        try:
            lookup_result = await self.readarr_client.get_book_by_hardcover_id(client, book.hardcover_id)
            if lookup_result and lookup_result.get("id"):
                lookup_book_id = lookup_result.get("id")
                lookup_foreign_id = lookup_result.get("foreignBookId")
                if lookup_foreign_id and str(lookup_foreign_id) == str(book.hardcover_id):
                    try:
                        book_by_id_response = await client.get(
                            f"{self.readarr_client.api_url}/book/{lookup_book_id}",
                            headers=self.readarr_client.headers,
                        )
                        if book_by_id_response.status_code == 200:
                            book_in_library = book_by_id_response.json()
                            library_foreign_id = book_in_library.get("foreignBookId")
                            if library_foreign_id and str(library_foreign_id) == str(book.hardcover_id):
                                readarr_book_id = book_in_library.get("id")
                                logger.info(
                                    "readarr_book_found_after_conflict",
                                    book_id=book.id,
                                    readarr_book_id=readarr_book_id,
                                    hardcover_id=book.hardcover_id,
                                )
                                return {
                                    "success": True,
                                    "readarr_book_id": readarr_book_id,
                                    "message": "Book already exists in Readarr (found after conflict)",
                                }
                            logger.warning(
                                "readarr_conflict_resolution_mismatch",
                                hardcover_id=book.hardcover_id,
                                library_foreign_id=library_foreign_id,
                                readarr_book_id=lookup_book_id,
                            )
                    except Exception as exc:
                        logger.debug(
                            "readarr_get_book_after_conflict_failed",
                            book_id=lookup_book_id,
                            error=str(exc),
                        )
        except Exception as exc:
            logger.debug("readarr_resolve_conflict_failed", error=str(exc))
        return None

    async def trigger_search_for_new(
        self,
        readarr_book_id: int,
        book: models.Book,
    ) -> tuple[bool, Optional[int]]:
        search_triggered = False
        search_status_code = None
        try:
            async with httpx.AsyncClient(timeout=10.0) as search_client:
                search_command = {"name": "BookSearch", "bookIds": [readarr_book_id]}
                search_response = await search_client.post(
                    f"{self.readarr_client.api_url}/command",
                    headers=self.readarr_client.headers,
                    json=search_command,
                )
            search_status_code = search_response.status_code
            if search_response.status_code in [200, 201]:
                search_triggered = True
                logger.info(
                    "readarr_search_triggered",
                    book_id=book.id,
                    readarr_book_id=readarr_book_id,
                )
            else:
                logger.warning(
                    "readarr_search_trigger_failed",
                    book_id=book.id,
                    readarr_book_id=readarr_book_id,
                    status_code=search_response.status_code,
                    error=search_response.text,
                )
        except Exception as exc:
            logger.warning(
                "readarr_search_trigger_error",
                book_id=book.id,
                readarr_book_id=readarr_book_id,
                error=str(exc),
            )
        return search_triggered, search_status_code


def get_readarr_server_for_format(
    format_type: str,
    db: Session,
) -> Optional[models.ReadarrServer]:
    """Get the appropriate Readarr server for a given format."""
    if format_type == "audiobook":
        server = db.query(models.ReadarrServer).filter(
            models.ReadarrServer.is_audiobook == True
        ).first()
        if server:
            return server

    server = db.query(models.ReadarrServer).filter(
        models.ReadarrServer.is_default == True,
        models.ReadarrServer.is_audiobook == False,
    ).first()
    if server:
        return server

    if format_type != "audiobook":
        server = db.query(models.ReadarrServer).filter(
            models.ReadarrServer.is_audiobook == False
        ).first()
        if server:
            return server
    return None


async def _get_cached_library(server: models.ReadarrServer) -> List[Dict[str, Any]]:
    cache_key = make_cache_key("readarr_library", server_id=server.id)
    cached = await get_cached(cache_key)
    if cached is not None:
        return cached

    readarr_client = ReadarrClient.from_server(server)
    async with readarr_client.session(timeout=15.0) as client:
        books = await readarr_client.get_library_books(client)
    await set_cached(cache_key, books, ttl=CACHE_TTL.get("readarr_library", 60))
    return books


def _normalize_isbn(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())


def _availability_from_books(
    books: List[Dict[str, Any]],
    isbn_lookup: Optional[Dict[str, int]] = None,
) -> Dict[int, bool]:
    availability: Dict[int, bool] = {}
    for book in books:
        foreign_id = book.get("foreignBookId")
        if foreign_id is None:
            hardcover_id = None
        else:
            try:
                hardcover_id = int(foreign_id)
            except (TypeError, ValueError):
                hardcover_id = None
        has_file = book.get("statistics", {}).get("bookFileCount", 0) > 0
        if not has_file:
            continue
        if hardcover_id is not None:
            availability[hardcover_id] = True
            continue
        if not isbn_lookup:
            continue
        isbn_values: List[str] = []
        for key in ["isbn", "isbn13", "isbn10"]:
            value = book.get(key)
            if not value:
                continue
            if isinstance(value, list):
                isbn_values.extend([str(item) for item in value if item])
            else:
                isbn_values.append(str(value))
        for raw_isbn in isbn_values:
            normalized = _normalize_isbn(raw_isbn)
            if not normalized:
                continue
            matched_id = isbn_lookup.get(normalized)
            if matched_id is not None:
                availability[matched_id] = True
                break
    return availability


async def get_readarr_availability_map(
    db: Session,
    hardcover_ids: List[int],
    isbn_map: Optional[Dict[int, List[str]]] = None,
) -> Dict[int, Dict[str, bool]]:
    unique_ids = {int(book_id) for book_id in hardcover_ids if book_id is not None}
    result = {hardcover_id: {"ebook": False, "audiobook": False} for hardcover_id in unique_ids}
    if not result:
        return {}

    isbn_lookup: Dict[str, int] = {}
    if isbn_map:
        for hardcover_id, values in isbn_map.items():
            if not values:
                continue
            for raw_isbn in values:
                normalized = _normalize_isbn(str(raw_isbn))
                if normalized:
                    isbn_lookup[normalized] = int(hardcover_id)

    ebook_server = db.query(models.ReadarrServer).filter(
        models.ReadarrServer.is_audiobook == False
    ).first()
    if ebook_server:
        books = await _get_cached_library(ebook_server)
        ebook_available = _availability_from_books(books, isbn_lookup)
        for hardcover_id in result:
            if ebook_available.get(hardcover_id):
                result[hardcover_id]["ebook"] = True

    audiobook_server = db.query(models.ReadarrServer).filter(
        models.ReadarrServer.is_audiobook == True
    ).first()
    if audiobook_server:
        books = await _get_cached_library(audiobook_server)
        audiobook_available = _availability_from_books(books, isbn_lookup)
        for hardcover_id in result:
            if audiobook_available.get(hardcover_id):
                result[hardcover_id]["audiobook"] = True

    return result


async def is_format_available_in_readarr(
    db: Session,
    hardcover_id: int,
    format: str,
    isbns: Optional[List[str]] = None,
) -> bool:
    isbn_map = {int(hardcover_id): isbns} if isbns else None
    availability = await get_readarr_availability_map(db, [hardcover_id], isbn_map=isbn_map)
    item = availability.get(int(hardcover_id))
    if not item:
        return False
    if format == "ebook":
        return bool(item.get("ebook"))
    if format == "audiobook":
        return bool(item.get("audiobook"))
    return False
