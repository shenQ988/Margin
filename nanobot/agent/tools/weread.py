"""Native WeRead (微信读书) API tool.

Calls the WeRead Agent API Gateway directly over HTTP instead of relying on the
LLM to author raw ``curl`` shell commands (see ``nanobot/skills/weread-skills/``
for the field-semantics reference docs this tool's callers should read first).
"""

# pyright: reportIncompatibleMethodOverride=false

from __future__ import annotations

import asyncio
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import httpx

from nanobot.agent.skills import parse_skill_metadata
from nanobot.agent.tools.base import Tool, ToolResult, tool_parameters
from nanobot.agent.tools.schema import (
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from nanobot.config_base import Base
from nanobot.security.network import PinnedDNSAsyncTransport

if TYPE_CHECKING:
    from nanobot.agent.tools.context import ToolContext

_GATEWAY_URL = "https://i.weread.qq.com/api/agent/gateway"
_SKILL_MD_PATH = Path(__file__).parent.parent.parent / "skills" / "weread-skills" / "SKILL.md"
_FALLBACK_SKILL_VERSION = "1.0.4"

_ACTION_TO_API_NAME: dict[str, str] = {
    "search": "/store/search",
    "shelf": "/shelf/sync",
    "notebooks": "/user/notebooks",
    "bookmarklist": "/book/bookmarklist",
    "reviews_mine": "/review/list/mine",
    "readdata": "/readdata/detail",
    "reviews": "/review/list",
    "recommend": "/book/recommend",
    "recommend_author": "",
    "advisor": "",
}

_REQUIRED_FIELDS_BY_ACTION: dict[str, str] = {
    "search": "keyword",
    "recommend_author": "keyword",
    "advisor": "keyword",
    "bookmarklist": "book_id",
    "reviews_mine": "book_id",
    "reviews": "book_id",
}


class WeReadError(Exception):
    """A safe error that can be surfaced to callers (tool or webui route)."""

    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class WeReadToolConfig(Base):
    """WeRead tool configuration."""

    enabled: bool = True
    api_key: str = ""


def _skill_version() -> str:
    try:
        content = _SKILL_MD_PATH.read_text(encoding="utf-8")
    except OSError:
        return _FALLBACK_SKILL_VERSION
    meta = parse_skill_metadata(content) or {}
    version = meta.get("version")
    return str(version) if version else _FALLBACK_SKILL_VERSION


def _weread_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=PinnedDNSAsyncTransport(), timeout=10.0, follow_redirects=False)


def _normalise_title(value: object) -> str:
    """Make edition variants of a title compare as one recommendation."""
    title = re.sub(r"[（(][^（）()]*[）)]", "", str(value or ""))
    return re.sub(r"[^\w]+", "", title.casefold())


def _same_work(candidate_title: object, owned_title: object) -> bool:
    """Reject an edition when it contains an owned work's stable title segment.

    This intentionally catches bilingual catalog labels such as
    ``傲慢与偏见（英文原版）Pride and Prejudice`` without needing a translation table.
    Very short titles are left to the LLM's ranking stage to avoid false positives.
    """
    candidate = _normalise_title(candidate_title)
    owned = _normalise_title(owned_title)
    return len(owned) >= 8 and (owned in candidate or candidate in owned)


def build_author_recommendations(
    author: str,
    shelf_payload: dict[str, Any],
    notebooks_payload: dict[str, Any],
    search_payload: dict[str, Any],
) -> dict[str, Any]:
    """Create a compact, evidence-only recommendation brief for the LLM.

    The function deliberately does deterministic filtering (shelf exclusion
    and edition de-duplication) before the LLM sees candidates. The LLM can
    then tailor wording from the live profile without inventing titles.
    """
    shelf_books = cast(list[dict[str, Any]], shelf_payload.get("books") or [])
    notes_by_id = {
        str(entry.get("bookId")): sum(
            int(entry.get(field) or 0) for field in ("reviewCount", "noteCount", "bookmarkCount")
        )
        for entry in cast(list[dict[str, Any]], notebooks_payload.get("books") or [])
        if entry.get("bookId") is not None
    }
    owned_ids = {str(book.get("bookId")) for book in shelf_books if book.get("bookId") is not None}
    owned_titles = {_normalise_title(book.get("title")) for book in shelf_books}
    category_weights: Counter[str] = Counter()
    deep_reads: list[dict[str, Any]] = []
    active_books: list[str] = []
    for book in shelf_books:
        book_id = str(book.get("bookId") or "")
        notes = notes_by_id.get(book_id, 0)
        category = str(book.get("category") or "").strip()
        if notes >= 5:
            if category:
                category_weights[category] += 1
            deep_reads.append({"title": book.get("title") or "Untitled", "notes": notes, "category": category or None})
        if not bool(book.get("finishReading")) and book.get("readUpdateTime"):
            active_books.append(str(book.get("title") or "Untitled"))

    candidates: list[dict[str, Any]] = []
    rejected_candidates: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for group in cast(list[dict[str, Any]], search_payload.get("results") or []):
        for result in cast(list[dict[str, Any]], group.get("books") or []):
            info = cast(dict[str, Any], result.get("bookInfo") or result)
            title = str(info.get("title") or "").strip()
            canonical_title = _normalise_title(title)
            book_id = str(info.get("bookId") or "")
            if not title or canonical_title in seen_titles:
                continue
            if book_id in owned_ids or canonical_title in owned_titles:
                rejected_candidates.append({"title": title, "reason": "already_owned"})
                continue
            matching_owned = next(
                (book.get("title") for book in shelf_books if _same_work(title, book.get("title"))), None
            )
            if matching_owned:
                rejected_candidates.append(
                    {"title": title, "reason": "same_work_as_owned", "ownedTitle": matching_owned}
                )
                continue
            seen_titles.add(canonical_title)
            candidates.append(
                {
                    "bookId": book_id or None,
                    "title": title,
                    "author": info.get("author") or None,
                    "category": info.get("category") or None,
                    "deepLink": info.get("deepLink") or None,
                    "rating": result.get("newRating") if result.get("newRating") is not None else info.get("newRating"),
                }
            )

    return {
        "author": author,
        "ownedBooks": [
            {"title": book.get("title") or "Untitled", "author": book.get("author") or None}
            for book in shelf_books
        ],
        "profile": {
            "deepReadTopics": [name for name, _ in category_weights.most_common(3)],
            "deepReads": sorted(deep_reads, key=lambda item: item["notes"], reverse=True)[:3],
            "activeBooks": active_books[:3],
        },
        "candidates": candidates[:8],
        "validation": {
            "eligibleCandidates": "Only candidates are eligible for recommendation.",
            "rejectedCandidates": rejected_candidates,
        },
        "rules": {
            "source": "Live WeRead shelf, notebook, and ebook catalog data.",
            "excluded": "Exact title matches, matching book IDs, and duplicate title editions were removed.",
            "response": "This is the validation stage of the advisor workflow. Recommend only listed candidates; rejectedCandidates are forbidden. If deepReadTopics, deepReads, or activeBooks are non-empty, explicitly mention one of those signals in one brief personalized rationale. Do not invent book facts or preferences.",
        },
    }


def build_topic_advisor(
    topic: str,
    shelf_payload: dict[str, Any],
    notebooks_payload: dict[str, Any],
    search_payload: dict[str, Any],
) -> dict[str, Any]:
    """Build the advisor's evidence packet for a topic-specific next-step recommendation."""
    packet = build_author_recommendations(topic, shelf_payload, notebooks_payload, search_payload)
    shelf_books = cast(list[dict[str, Any]], shelf_payload.get("books") or [])
    notebook_books = cast(list[dict[str, Any]], notebooks_payload.get("books") or [])
    notebook_ids = {
        str(entry.get("bookId")) for entry in notebook_books if entry.get("bookId") is not None
    }
    note_totals = {
        str(entry.get("bookId")): sum(int(entry.get(key) or 0) for key in ("reviewCount", "noteCount", "bookmarkCount"))
        for entry in notebook_books
        if entry.get("bookId") is not None
    }
    notebook_titles = {
        str(entry.get("bookId")): str(
            cast(dict[str, Any], entry.get("book") or {}).get("title") or entry.get("title") or "Untitled"
        )
        for entry in notebook_books
        if entry.get("bookId") is not None
    }
    shelf_ids = {str(book.get("bookId")) for book in shelf_books if book.get("bookId") is not None}
    topic_words = [word for word in re.split(r"\s+", topic.casefold()) if word]

    def is_relevant(book: dict[str, Any]) -> bool:
        searchable = f"{book.get('title', '')} {book.get('category', '')}".casefold()
        return not topic_words or any(word in searchable for word in topic_words)

    true_reads = []
    dormant = []
    shallow = []
    for book in shelf_books:
        if not is_relevant(book):
            continue
        notes = note_totals.get(str(book.get("bookId")), 0)
        record = {"title": book.get("title") or "Untitled", "notes": notes, "category": book.get("category") or None}
        if notes >= 5:
            true_reads.append(record)
        elif str(book.get("bookId")) not in notebook_ids:
            dormant.append(record)
        elif 1 <= notes <= 3:
            shallow.append(record)
    hidden_deep_reads = [
        {"bookId": book_id, "title": notebook_titles[book_id], "notes": notes}
        for book_id, notes in note_totals.items()
        if book_id not in shelf_ids and notes >= 10
    ]
    packet.update(
        {
            "topic": topic,
            "analysis": {
                "trueReads": sorted(true_reads, key=lambda item: item["notes"], reverse=True),
                "dormant": dormant,
                "shallow": shallow,
                "hiddenDeepReads": hidden_deep_reads,
            },
            "workflow": {
                "route": "advisor" if len(true_reads) >= 3 else "path",
                "checkpoint": "Before recommending, ask for count (3 or 5), WeRead-only versus broader sources, and any language or length limit unless the user already specified them.",
                "output": "If route is advisor and constraints are known, recommend only candidates. Lead with an evidence-based observation, group 3-5 books by priority, explain why each fills a gap, and end with one best next book plus one stretch pair. If route is path, explain that there are fewer than three deeply-noted topic books and offer a beginner path instead.",
            },
        }
    )
    return packet


async def call_weread_api(api_key: str, api_name: str, **params: Any) -> dict[str, Any]:
    """Call one WeRead Agent API Gateway endpoint and return the raw JSON payload."""
    if not api_key:
        raise WeReadError("WEREAD_API_KEY is not configured", status=501)
    body = {"api_name": api_name, "skill_version": _skill_version(), **params}
    try:
        async with _weread_client() as client:
            response = await client.post(
                _GATEWAY_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise WeReadError("WeRead is temporarily unavailable", status=502) from exc
    if not isinstance(payload, dict):
        raise WeReadError("WeRead returned an unexpected response", status=502)
    payload = cast(dict[str, Any], payload)
    if payload.get("errcode"):
        raise WeReadError(f"WeRead error: {payload.get('errmsg') or payload.get('errcode')}", status=502)
    return payload


_WEREAD_PARAMETERS = tool_parameters_schema(
    action=StringSchema(
        "Which WeRead capability to call. Use recommend_author for personalized "
        "recommendations of more books by a named author, or advisor for a topic-specific reading plan.",
        enum=list(_ACTION_TO_API_NAME),
    ),
    keyword=StringSchema("Search keyword. Required for action='search'."),
    scope=IntegerSchema(
        description="Search scope code (0=all, 10=ebooks, 16=web fiction, 14=audiobooks, "
        "6=authors, 12=full text, 13=booklists, 2=official accounts, 4=articles). "
        "Only used for action='search'; read the weread-skills skill doc for selection rules.",
    ),
    count=IntegerSchema(description="Page size. Used for search/notebooks/recommend."),
    max_idx=IntegerSchema(description="Pagination offset. Used for search/recommend."),
    book_id=StringSchema(
        "Book ID. Required for action='bookmarklist'/'reviews_mine'/'reviews'. "
        "Resolve from a title first via action='search'."
    ),
    last_sort=IntegerSchema(description="Pagination cursor for action='notebooks' (previous page's last 'sort' value)."),
    synckey=IntegerSchema(description="Pagination cursor for action='reviews_mine'."),
    review_list_type=IntegerSchema(
        description="Filter for action='reviews': 0=all, 1=recommended, 2=negative, 3=newest, 4=mixed.",
    ),
    mode=StringSchema(
        "Stats period for action='readdata': weekly, monthly, annually, or overall. Defaults to monthly.",
    ),
    base_time=IntegerSchema(description="Base unix timestamp for action='readdata' (0 = current period)."),
    required=["action"],
    description=(
        "Read the weread-skills skill doc before calling: it documents field semantics, "
        "counting rules (e.g. shelf totals must include albums[]), and output formatting. "
        "This tool returns raw WeRead API JSON; per-action required fields are enforced at "
        "runtime (see each field's description) rather than in this flat schema."
    ),
)


@tool_parameters(_WEREAD_PARAMETERS)
class WeReadTool(Tool):
    """Call the WeRead (微信读书) Agent API Gateway directly over HTTP."""

    config_key = "weread"
    _scopes = {"core", "subagent"}

    def __init__(self, config: WeReadToolConfig) -> None:
        self.config = config

    @classmethod
    def config_cls(cls) -> type[WeReadToolConfig]:
        return WeReadToolConfig

    @classmethod
    def enabled(cls, ctx: ToolContext) -> bool:
        return ctx.config.weread.enabled

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        return cls(config=ctx.config.weread)

    @property
    def name(self) -> str:
        return "weread"

    @property
    def description(self) -> str:
        return (
            "Call the WeRead (微信读书) reading app API. Actions: search, shelf, notebooks, "
            "bookmarklist, reviews_mine, readdata, reviews, recommend, recommend_author, advisor. Read the weread-skills "
            "skill doc first for field semantics and output formatting rules; this tool returns "
            "raw API JSON, not formatted prose. For requests to find, search, or recommend "
            "books, use the WeRead catalog before web search. For 'more books by [author]' or "
            "a tailored author recommendation, use action='recommend_author' with keyword=the author; "
            "it fetches the live profile, searches ebook scope=10, and removes owned/duplicate titles. "
            "When its profile contains a signal, explicitly connect one recommendation to that signal in the final answer. "
            "For 'what should I read next about [topic]' use action='advisor'. It returns live cross-analysis and verified ebook candidates; follow its checkpoint before making recommendations unless the user already supplied constraints. "
            "For ordinary book search use action='search' with scope=10. For an open-ended "
            "personalized recommendation, use action='recommend'. Every result is a live snapshot of external "
            "state (shelf contents, reading progress, notebooks, etc.) that can change outside "
            "this conversation at any time — call this tool again for current data rather than "
            "relying on an earlier answer in this session or on remembered facts; results are "
            "never persisted to long-term memory for this reason (see memory_classification.py)."
        )

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = super().validate_params(params)
        action = params.get("action")
        required_field = _REQUIRED_FIELDS_BY_ACTION.get(cast(str, action))
        if required_field and not str(params.get(required_field) or "").strip():
            errors.append(f"{required_field} is required when action='{action}'")
        return errors

    def _api_key(self) -> str:
        return self.config.api_key or os.environ.get("WEREAD_API_KEY", "")

    async def execute(
        self,
        action: str,
        keyword: str | None = None,
        scope: int | None = None,
        count: int | None = None,
        max_idx: int | None = None,
        book_id: str | None = None,
        last_sort: int | None = None,
        synckey: int | None = None,
        review_list_type: int | None = None,
        mode: str | None = None,
        base_time: int | None = None,
    ) -> str:
        api_name = _ACTION_TO_API_NAME.get(action)
        if api_name is None:
            return ToolResult.error(f"Unknown action: {action}")

        if action in {"recommend_author", "advisor"}:
            if not keyword or not keyword.strip():
                return ToolResult.error(f"keyword is required for action='{action}'")
            try:
                shelf_payload, notebooks_payload, search_payload = await asyncio.gather(
                    call_weread_api(self._api_key(), "/shelf/sync"),
                    call_weread_api(self._api_key(), "/user/notebooks", count=200),
                    call_weread_api(self._api_key(), "/store/search", keyword=keyword.strip(), scope=10),
                )
            except WeReadError as exc:
                return ToolResult.error(f"Error: {exc.message}")
            return json.dumps(
                (
                    build_author_recommendations(keyword.strip(), shelf_payload, notebooks_payload, search_payload)
                    if action == "recommend_author"
                    else build_topic_advisor(keyword.strip(), shelf_payload, notebooks_payload, search_payload)
                ),
                ensure_ascii=False,
                indent=2,
            )

        params: dict[str, Any] = {}
        if action == "search":
            if not keyword:
                return ToolResult.error("keyword is required for action='search'")
            params["keyword"] = keyword
            if scope is not None:
                params["scope"] = scope
            if count is not None:
                params["count"] = count
            if max_idx is not None:
                params["maxIdx"] = max_idx
        elif action == "notebooks":
            if count is not None:
                params["count"] = count
            if last_sort is not None:
                params["lastSort"] = last_sort
        elif action == "bookmarklist":
            if not book_id:
                return ToolResult.error("book_id is required for action='bookmarklist'")
            params["bookId"] = book_id
        elif action == "reviews_mine":
            if not book_id:
                return ToolResult.error("book_id is required for action='reviews_mine'")
            params["bookid"] = book_id
            if synckey is not None:
                params["synckey"] = synckey
            if count is not None:
                params["count"] = count
        elif action == "readdata":
            if mode is not None:
                params["mode"] = mode
            if base_time is not None:
                params["baseTime"] = base_time
        elif action == "reviews":
            if not book_id:
                return ToolResult.error("book_id is required for action='reviews'")
            params["bookId"] = book_id
            if review_list_type is not None:
                params["reviewListType"] = review_list_type
            if count is not None:
                params["count"] = count
            if max_idx is not None:
                params["maxIdx"] = max_idx
            if synckey is not None:
                params["synckey"] = synckey
        elif action == "recommend":
            if count is not None:
                params["count"] = count
            if max_idx is not None:
                params["maxIdx"] = max_idx
        # action == "shelf": no parameters

        try:
            payload = await call_weread_api(self._api_key(), api_name, **params)
        except WeReadError as exc:
            return ToolResult.error(f"Error: {exc.message}")
        return json.dumps(payload, ensure_ascii=False, indent=2)
