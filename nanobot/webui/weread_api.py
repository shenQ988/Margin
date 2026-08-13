"""Proxy for the WeRead (微信读书) shelf and notes, used by the webui."""

from __future__ import annotations

import asyncio
import os
from typing import Any, cast

from nanobot.agent.tools.weread import WeReadError, call_weread_api

__all__ = [
    "WeReadError",
    "fetch_notebooks",
    "fetch_shelf_enriched",
    "normalize_notebooks",
    "normalize_shelf",
    "weread_configured",
]

_PROGRESS_CANDIDATE_LIMIT = 5
# Enrichment (notes + progress) is best-effort: bound it well under the
# frontend's fetch timeout (see fetchWeReadShelf in webui/src/lib/api.ts) so a
# slow WeRead gateway degrades to "shelf without enrichment" instead of the
# browser abandoning the connection while the backend is still writing to it
# (that race trips a `websockets` library assertion — see git history).
_NOTEBOOKS_TIMEOUT_S = 6.0
_PROGRESS_TIMEOUT_S = 5.0


def weread_configured() -> bool:
    return bool(os.environ.get("WEREAD_API_KEY"))


def _flag(value: Any) -> bool:
    return value == 1 or value is True


async def _fetch_notebooks_raw(api_key: str) -> dict[str, Any]:
    return await call_weread_api(api_key, "/user/notebooks", count=200)


async def _note_book_ids(api_key: str) -> set[str]:
    try:
        payload = await asyncio.wait_for(_fetch_notebooks_raw(api_key), timeout=_NOTEBOOKS_TIMEOUT_S)
    except (WeReadError, TimeoutError):
        return set()
    ids: set[str] = set()
    for book in cast(list[dict[str, Any]], payload.get("books") or []):
        total = (book.get("reviewCount") or 0) + (book.get("noteCount") or 0) + (book.get("bookmarkCount") or 0)
        book_id = book.get("bookId")
        if total > 0 and book_id is not None:
            ids.add(str(book_id))
    return ids


async def _book_progress(api_key: str, book_id: str) -> tuple[str, int | None]:
    try:
        payload = await call_weread_api(api_key, "/book/getprogress", bookId=book_id)
    except WeReadError:
        return book_id, None
    book = cast(dict[str, Any], payload.get("book") or {})
    progress = book.get("progress")
    return book_id, progress if isinstance(progress, int) else None


async def fetch_shelf_enriched() -> dict[str, Any]:
    """Fetch the shelf, plus note/progress enrichment, and return normalized items.

    ``/shelf/sync`` and ``/user/notebooks`` are independent, so they're fetched
    concurrently rather than chained — chaining all three calls (shelf, notebooks,
    then per-book progress) sequentially can sum to 30+ seconds under a slow
    network, which is slow enough to trip unrelated timeouts elsewhere.
    """
    api_key = os.environ.get("WEREAD_API_KEY") or ""
    shelf_payload, note_book_ids = await asyncio.gather(
        call_weread_api(api_key, "/shelf/sync"),
        _note_book_ids(api_key),
    )

    books = cast(list[dict[str, Any]], shelf_payload.get("books") or [])
    candidates = [
        book for book in books if not _flag(book.get("finishReading")) and book.get("readUpdateTime")
    ]
    candidates.sort(key=lambda book: cast(int, book.get("readUpdateTime") or 0), reverse=True)
    top_candidates = candidates[:_PROGRESS_CANDIDATE_LIMIT]

    try:
        progress_results = await asyncio.wait_for(
            asyncio.gather(*[_book_progress(api_key, str(book.get("bookId"))) for book in top_candidates]),
            timeout=_PROGRESS_TIMEOUT_S,
        )
    except TimeoutError:
        progress_results = []
    progress_by_book_id = {book_id: progress for book_id, progress in progress_results if progress is not None}

    return normalize_shelf(shelf_payload, note_book_ids=note_book_ids, progress_by_book_id=progress_by_book_id)


def normalize_shelf(
    payload: dict[str, Any],
    *,
    note_book_ids: set[str] | None = None,
    progress_by_book_id: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Flatten WeRead's books/albums/mp shelf shape into one item list."""
    note_book_ids = note_book_ids or set()
    progress_by_book_id = progress_by_book_id or {}
    items: list[dict[str, Any]] = []

    for book in cast(list[dict[str, Any]], payload.get("books") or []):
        finished = _flag(book.get("finishReading"))
        book_id = book.get("bookId")
        book_id_str = str(book_id) if book_id is not None else None
        status = "finished" if finished else ("reading" if book.get("readUpdateTime") else "toread")
        items.append(
            {
                "kind": "book",
                "id": book_id,
                "title": book.get("title"),
                "author": book.get("author"),
                "cover": book.get("cover"),
                "category": book.get("category"),
                "finished": finished,
                "top": _flag(book.get("isTop")),
                "deepLink": book.get("deepLink"),
                "updateTime": book.get("readUpdateTime") or book.get("updateTime"),
                "status": status,
                "progress": progress_by_book_id.get(book_id_str) if book_id_str else None,
                "hasNote": book_id_str in note_book_ids if book_id_str else False,
            }
        )

    for album in cast(list[dict[str, Any]], payload.get("albums") or []):
        info = cast(dict[str, Any], album.get("albumInfo") or {})
        extra = cast(dict[str, Any], album.get("albumInfoExtra") or {})
        finished = _flag(info.get("finish"))
        status = "finished" if finished else ("reading" if extra.get("lectureReadUpdateTime") else "toread")
        items.append(
            {
                "kind": "album",
                "id": info.get("albumId"),
                "title": info.get("name"),
                "author": info.get("authorName"),
                "cover": info.get("cover"),
                "category": None,
                "finished": finished,
                "top": _flag(extra.get("isTop")),
                "deepLink": None,
                "updateTime": info.get("updateTime"),
                "status": status,
                "progress": None,
                "hasNote": False,
            }
        )

    mp = payload.get("mp")
    if mp:
        items.append(
            {
                "kind": "mp",
                "id": "mp",
                "title": "文章收藏",
                "author": None,
                "cover": None,
                "category": None,
                "finished": False,
                "top": False,
                "deepLink": None,
                "updateTime": None,
                "status": "toread",
                "progress": None,
                "hasNote": False,
            }
        )

    return {"configured": True, "items": items, "count": len(items)}


async def fetch_notebooks() -> dict[str, Any]:
    """Fetch the raw ``/user/notebooks`` payload from the WeRead gateway."""
    api_key = os.environ.get("WEREAD_API_KEY") or ""
    return await _fetch_notebooks_raw(api_key)


def normalize_notebooks(payload: dict[str, Any]) -> dict[str, Any]:
    """Shape WeRead's notebooks overview into a flat list for the Notes tab."""
    items: list[dict[str, Any]] = []
    for entry in cast(list[dict[str, Any]], payload.get("books") or []):
        book = cast(dict[str, Any], entry.get("book") or {})
        review_count = entry.get("reviewCount") or 0
        note_count = entry.get("noteCount") or 0
        bookmark_count = entry.get("bookmarkCount") or 0
        items.append(
            {
                "bookId": entry.get("bookId"),
                "title": book.get("title"),
                "author": book.get("author"),
                "cover": book.get("cover"),
                "reviewCount": review_count,
                "noteCount": note_count,
                "bookmarkCount": bookmark_count,
                "totalNotes": review_count + note_count + bookmark_count,
                "readingProgress": entry.get("readingProgress"),
                "markedStatus": entry.get("markedStatus"),
            }
        )
    return {"configured": True, "items": items, "count": len(items)}
