"""Proxy for the WeRead (微信读书) shelf and notes, used by the webui."""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any, cast

from nanobot.agent.tools.weread import WeReadError, call_weread_api

__all__ = [
    "WeReadError",
    "fetch_book_notes",
    "fetch_advisor",
    "fetch_notebooks",
    "fetch_shelf_enriched",
    "normalize_book_notes",
    "build_reading_profile",
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
_DEEP_READ_NOTE_COUNT = 5
_ACTIVE_READING_DAYS = 30
_MAP_LEVELS = ("Beginner", "Intermediate", "Advanced")
_MAP_REASONS = (
    "Start here to establish the core vocabulary and questions for this topic.",
    "Read this next to build on the foundation with a second perspective.",
    "Use this after the earlier steps to deepen or challenge the ideas you have met.",
)


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


async def fetch_advisor(topic: str | None = None) -> dict[str, Any]:
    """Build a fresh, non-persistent reading profile for the advisor UI."""
    api_key = os.environ.get("WEREAD_API_KEY") or ""
    requested_topic = topic.strip() if topic else ""
    requests = [
        call_weread_api(api_key, "/shelf/sync"),
        _fetch_notebooks_raw(api_key),
    ]
    if requested_topic:
        # These calls are independent. Keeping catalog search parallel with
        # shelf/profile retrieval prevents a slow WeRead response from making
        # the browser abandon the HTTP-over-WebSocket request.
        requests.append(call_weread_api(api_key, "/store/search", keyword=requested_topic, scope=10))
    results = await asyncio.gather(*requests)
    shelf_payload = cast(dict[str, Any], results[0])
    notebooks_payload = cast(dict[str, Any], results[1])
    profile = build_reading_profile(shelf_payload, notebooks_payload)
    if not requested_topic:
        return profile
    words = [word for word in requested_topic.casefold().split() if word]

    def matches(book: dict[str, Any]) -> bool:
        searchable = f"{book.get('title', '')} {book.get('category', '')}".casefold()
        return any(word in searchable for word in words)
    for key in ("deepReads", "dormantBooks", "activeBooks"):
        profile[key] = [book for book in profile[key] if matches(cast(dict[str, Any], book))]
    profile["topics"] = [item for item in profile["topics"] if matches(cast(dict[str, Any], item))]
    profile["recommendation"] = next(iter(profile["dormantBooks"]), None)
    profile["topic"] = requested_topic
    catalog = cast(dict[str, Any], results[2])
    profile["suggestedBooks"] = _build_topic_suggestions(catalog, shelf_payload, requested_topic)
    return profile


def _normalise_map_title(value: object) -> str:
    title = re.sub(r"[（(][^（）()]*[）)]", "", str(value or ""))
    return re.sub(r"[^\w]+", "", title.casefold())


def _build_topic_suggestions(
    catalog: dict[str, Any], shelf_payload: dict[str, Any], topic: str
) -> list[dict[str, Any]]:
    """Return a short, de-duplicated three-step path from live catalog results."""
    shelf_books = cast(list[dict[str, Any]], shelf_payload.get("books") or [])
    owned_ids = {str(book.get("bookId")) for book in shelf_books if book.get("bookId") is not None}
    owned_titles = [_normalise_map_title(book.get("title")) for book in shelf_books]
    candidates: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    for group in cast(list[dict[str, Any]], catalog.get("results") or []):
        for result in cast(list[dict[str, Any]], group.get("books") or []):
            info = cast(dict[str, Any], result.get("bookInfo") or result)
            title = str(info.get("title") or "").strip()
            canonical_title = _normalise_map_title(title)
            book_id = str(info.get("bookId") or "")
            is_owned_edition = any(
                len(owned_title) >= 8
                and (owned_title in canonical_title or canonical_title in owned_title)
                for owned_title in owned_titles
            )
            if not title or canonical_title in seen_titles or book_id in owned_ids or is_owned_edition:
                continue
            seen_titles.add(canonical_title)
            candidates.append(
                {
                    "bookId": book_id,
                    "title": title,
                    "author": info.get("author") or None,
                    "category": info.get("category") or None,
                    "deepLink": info.get("deepLink") or None,
                }
            )

    return [
        {
            **book,
            "step": index,
            "level": _MAP_LEVELS[index - 1],
            "reason": _MAP_REASONS[index - 1],
            "topic": topic,
        }
        for index, book in enumerate(candidates[: len(_MAP_LEVELS)], start=1)
    ]


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _category(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def build_reading_profile(
    shelf_payload: dict[str, Any],
    notebooks_payload: dict[str, Any],
    *,
    now_timestamp: int | None = None,
) -> dict[str, Any]:
    """Derive explainable advisor signals from live shelf and notebook snapshots.

    This function intentionally has no LLM or persistence dependency: its output
    is a request-local view of external state, never a durable user memory.
    """
    note_totals: dict[str, int] = {}
    for entry in cast(list[dict[str, Any]], notebooks_payload.get("books") or []):
        book_id = entry.get("bookId")
        if book_id is None:
            continue
        note_totals[str(book_id)] = sum(
            _count(entry.get(key)) for key in ("reviewCount", "noteCount", "bookmarkCount")
        )

    now = now_timestamp if now_timestamp is not None else int(time.time())
    active_cutoff = now - _ACTIVE_READING_DAYS * 24 * 60 * 60
    deep_reads: list[dict[str, Any]] = []
    dormant_books: list[dict[str, Any]] = []
    active_books: list[dict[str, Any]] = []
    topic_counts: dict[str, int] = {}

    for book in cast(list[dict[str, Any]], shelf_payload.get("books") or []):
        book_id = book.get("bookId")
        if book_id is None:
            continue
        title = book.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        notes = note_totals.get(str(book_id), 0)
        category = _category(book.get("category"))
        item = {"bookId": str(book_id), "title": title, "author": book.get("author"), "category": category, "notes": notes}
        if notes >= _DEEP_READ_NOTE_COUNT:
            deep_reads.append(item)
            if category is not None:
                topic_counts[category] = topic_counts.get(category, 0) + 1
        update_time = _count(book.get("readUpdateTime"))
        if not _flag(book.get("finishReading")) and update_time >= active_cutoff:
            active_books.append({**item, "updateTime": update_time})
        if not _flag(book.get("finishReading")) and not update_time and notes == 0:
            dormant_books.append(item)

    active_books.sort(key=lambda book: _count(book.get("updateTime")), reverse=True)
    topics = [
        {"name": name, "deepReadCount": count}
        for name, count in sorted(topic_counts.items(), key=lambda pair: (-pair[1], pair[0].lower()))
    ]
    strongest_topic = topics[0]["name"] if topics else None
    candidates = sorted(
        dormant_books,
        key=lambda book: (
            -topic_counts.get(cast(str | None, book.get("category")) or "", 0),
            str(book["title"]).lower(),
        ),
    )
    recommendation = None
    if candidates:
        candidate = candidates[0]
        reason = (
            f"It matches your strongest reading topic: {strongest_topic}."
            if strongest_topic and candidate.get("category") == strongest_topic
            else "It is already on your shelf and has not yet become an active read."
        )
        recommendation = {**candidate, "reason": reason}

    return {
        "configured": True,
        "deepReads": deep_reads,
        "dormantBooks": dormant_books,
        "activeBooks": active_books,
        "topics": topics,
        "recommendation": recommendation,
        "confidence": "high" if deep_reads else "low",
    }


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


async def fetch_book_notes(book_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch a single book's highlights (`/book/bookmarklist`) and personal
    thoughts/reviews (`/review/list/mine`) concurrently."""
    api_key = os.environ.get("WEREAD_API_KEY") or ""
    bookmarks_payload, reviews_payload = await asyncio.gather(
        call_weread_api(api_key, "/book/bookmarklist", bookId=book_id),
        call_weread_api(api_key, "/review/list/mine", bookid=book_id, count=200),
    )
    return bookmarks_payload, reviews_payload


def normalize_book_notes(
    bookmarks_payload: dict[str, Any],
    reviews_payload: dict[str, Any],
) -> dict[str, Any]:
    """Merge highlight and thought/review content into one chronological list."""
    chapter_titles = {
        chapter.get("chapterUid"): chapter.get("title")
        for chapter in cast(list[dict[str, Any]], bookmarks_payload.get("chapters") or [])
    }
    book = cast(dict[str, Any], bookmarks_payload.get("book") or {})

    items: list[dict[str, Any]] = []
    for bookmark in cast(list[dict[str, Any]], bookmarks_payload.get("updated") or []):
        chapter_uid = bookmark.get("chapterUid")
        items.append(
            {
                "id": f"bm:{bookmark.get('bookmarkId')}",
                "type": "highlight",
                "text": bookmark.get("markText"),
                "quote": None,
                "chapterUid": chapter_uid,
                "chapterTitle": chapter_titles.get(chapter_uid),
                "createTime": bookmark.get("createTime"),
            }
        )

    for entry in cast(list[dict[str, Any]], reviews_payload.get("reviews") or []):
        review = cast(dict[str, Any], entry.get("review") or {})
        chapter_uid = review.get("chapterUid")
        items.append(
            {
                "id": f"rv:{review.get('reviewId')}",
                "type": "thought",
                "text": review.get("content"),
                "quote": review.get("abstract"),
                "chapterUid": chapter_uid,
                "chapterTitle": review.get("chapterName") or chapter_titles.get(chapter_uid),
                "createTime": review.get("createTime"),
            }
        )

    items.sort(key=lambda item: cast(int, item.get("createTime") or 0), reverse=True)

    return {
        "configured": True,
        "book": {
            "bookId": book.get("bookId"),
            "title": book.get("title"),
            "author": book.get("author"),
            "cover": book.get("cover"),
        },
        "items": items,
        "count": len(items),
    }


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
