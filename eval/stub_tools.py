"""Self-contained stub tool registry for the tool-calling eval.

These are deliberately NOT the real production tools (e.g. not
``nanobot/agent/tools/weread.py``'s single action-multiplexed ``weread``
tool) — the eval is about measuring whether the *model* picks the right
tool given a name/description/schema, not about exercising real WeRead API
calls (which would be slow, rate-limited, non-deterministic, and require
live credentials just to run an eval). Each stub records its invocation
and returns a small canned string; nothing here touches the network or any
production module.
"""

from __future__ import annotations

from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.registry import ToolRegistry


class RecordingStubTool(Tool):
    """A minimal Tool that records every call it receives and returns a
    canned response. Never makes a network call or touches real data."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        canned_response: str = "ok",
    ) -> None:
        self._name = name
        self._description = description
        self._parameters = parameters
        self._canned_response = canned_response
        self.calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._canned_response


def _book_title_schema(*, required: bool) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "book_title": {
                "type": "string",
                "description": "Title of the book to look up.",
            },
        },
        "required": ["book_title"] if required else [],
    }


_STUB_TOOL_SPECS: list[tuple[str, str, dict[str, Any], str]] = [
    (
        "weread_shelf",
        "Fetch the user's current WeRead bookshelf (books currently reading, "
        "to-read, and finished). Always call this for shelf/bookshelf questions "
        "— shelf contents are live external state and change independently of "
        "this conversation, so never answer from a prior turn's shelf answer.",
        {"type": "object", "properties": {}, "required": []},
        '{"books": [{"title": "Sapiens", "status": "reading"}, '
        '{"title": "Pride and Prejudice", "status": "reading"}]}',
    ),
    (
        "weread_progress",
        "Fetch the user's current reading progress (percent complete) for a "
        "specific book. Progress is live external state — always call this "
        "rather than reusing a progress number stated earlier in the "
        "conversation.",
        _book_title_schema(required=True),
        '{"book_title": "Pride and Prejudice", "progress_percent": 42}',
    ),
    (
        "weread_notebooks",
        "List which of the user's books have personal notes/highlights on "
        "them, with counts. Always call this for 'which books have notes' "
        "style questions rather than answering from an earlier turn.",
        {"type": "object", "properties": {}, "required": []},
        '{"books_with_notes": [{"title": "Sapiens", "highlight_count": 12}]}',
    ),
    (
        "weread_bookmarklist",
        "Fetch the actual highlighted passage text for one specific book. "
        "Use this when the user wants to see/read their highlights "
        "themselves, not just a count.",
        _book_title_schema(required=True),
        '{"book_title": "Sapiens", "highlights": ["Fiction has enabled us '
        'to cooperate flexibly in large numbers."]}',
    ),
    (
        "weread_stats",
        "Fetch the user's reading time/activity statistics for a period "
        "(e.g. this week). Always call this for reading-time questions "
        "rather than guessing or reusing an earlier stated figure.",
        {"type": "object", "properties": {}, "required": []},
        '{"period": "week", "hours_read": 5.5}',
    ),
    (
        "ask_about_book",
        "Answer a question about the content/arguments of a specific book "
        "the user is reading, grounded in the book's actual text (not the "
        "model's general knowledge). Requires the book title.",
        _book_title_schema(required=True),
        '{"book_title": "Sapiens", "answer": "Harari argues shared myths '
        'let strangers cooperate at scale."}',
    ),
    (
        "generate_weekly_digest",
        "Generate a personalized summary of the user's reading activity "
        "and progress over the past week. Use this for open-ended "
        "'what's new with my reading' style questions about the user's own "
        "activity, not general chit-chat.",
        {"type": "object", "properties": {}, "required": []},
        '{"digest": "You read 5.5 hours this week across 2 books."}',
    ),
    (
        "get_reading_profile",
        "Fetch an aggregated profile of the user's reading habits and "
        "favorite topics/genres, computed from their actual reading "
        "history. Always call this rather than guessing from a stray "
        "preference mentioned earlier in conversation.",
        {"type": "object", "properties": {}, "required": []},
        '{"top_topics": ["science", "history"]}',
    ),
    (
        "add_reading_item",
        "Add a book to the user's WeRead reading list. Call this whenever "
        "the user asks to add/save/queue a book — do not just acknowledge "
        "the request in text without actually calling this tool.",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Title of the book to add."},
                "author": {"type": "string", "description": "Author, if known."},
            },
            "required": ["title"],
        },
        '{"status": "added", "title": "Project Hail Mary"}',
    ),
]


def build_stub_registry() -> ToolRegistry:
    """Build a fresh ToolRegistry containing exactly the 9 stub tools this
    eval's dataset (eval/tool_call_cases.py) references. A fresh instance
    per call so per-call ``.calls`` recordings never leak between eval runs."""
    registry = ToolRegistry()
    for name, description, parameters, canned_response in _STUB_TOOL_SPECS:
        registry.register(RecordingStubTool(name, description, parameters, canned_response))
    return registry


STUB_TOOL_NAMES: frozenset[str] = frozenset(spec[0] for spec in _STUB_TOOL_SPECS)
