"""Native WeRead (微信读书) API tool.

Calls the WeRead Agent API Gateway directly over HTTP instead of relying on the
LLM to author raw ``curl`` shell commands (see ``nanobot/skills/weread-skills/``
for the field-semantics reference docs this tool's callers should read first).
"""

# pyright: reportIncompatibleMethodOverride=false

from __future__ import annotations

import json
import os
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
}

_REQUIRED_FIELDS_BY_ACTION: dict[str, str] = {
    "search": "keyword",
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
        "Which WeRead capability to call.",
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
            "bookmarklist, reviews_mine, readdata, reviews, recommend. Read the weread-skills "
            "skill doc first for field semantics and output formatting rules; this tool returns "
            "raw API JSON, not formatted prose."
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
