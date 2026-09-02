"""Deterministic tool-result memory classification.

Bug this fixes: WeRead tool results (bookshelf state, reading progress,
notebooks, bookmarks, stats) were flowing into session-summary
consolidation and, from there via ``history.jsonl``, into Dream's durable
memory files (``USER.md`` / ``memory/MEMORY.md``). Once the agent answered a
bookshelf question once, the *stale* answer kept resurfacing in later
turns/sessions, because it had been baked in as if it were a permanent
fact instead of a snapshot of external state that can change at any time
outside the conversation. This was an observed bug, not a hypothetical.

``classify_tool_result`` is a static, deterministic lookup — it must never
call an LLM and must never be influenced by the agent's own judgment. Only
tool-*result* messages (``role == "tool"``) are ever classified; ordinary
user/assistant prose is untouched by this module, and the consolidation
LLM is still free to summarize *that* the user asked about their shelf —
it just never sees the raw WeRead JSON payload to bake specific numbers
into a "fact".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class MemoryScope(Enum):
    VOLATILE = "volatile"       # live external state — never written to
                                 # persistent memory, always re-fetch
    PERSISTABLE = "persistable"  # safe to include in session summaries /
                                  # USER.md / any consolidation step


# Every WeRead tool action (nanobot/agent/tools/weread.py, WeReadTool) reads
# live state from WeChat Reading's servers — shelf contents, reading
# progress, notebooks, bookmarks, stats, search results. All of it can
# change at any moment independent of this conversation, so all of it is
# volatile by definition. Entries are "<tool name>.<action>" for every
# action in WeReadTool's _ACTION_TO_API_NAME, plus the bare tool name as a
# catch-all for callers that can't resolve which action was invoked (this
# is what call sites in this codebase currently use, since tool-result
# messages don't carry the originating action directly).
#
# Update this set whenever nanobot/agent/tools/weread.py gains a new action.
VOLATILE_TOOL_SOURCES: frozenset[str] = frozenset(
    {
        "weread",  # bare tool name catch-all
        "weread.search",
        "weread.shelf",
        "weread.notebooks",
        "weread.bookmarklist",
        "weread.reviews_mine",
        "weread.readdata",
        "weread.reviews",
        "weread.recommend",
    }
)

# Tools whose result content is an explicit, user-confirmed durable fact
# rather than a fetch of mutable external state. Nothing in the current
# tool registry (nanobot/agent/tools/) qualifies: the consolidation LLM
# already extracts durable facts from ordinary assistant/user prose, so
# this set exists only for a future tool that itself *asserts* a fact the
# user explicitly confirmed (e.g. a hypothetical add_reading_item /
# save_note tool). Do not add a tool here just because its data "seems
# stable" — if it round-trips to a live external system, it is VOLATILE.
KNOWN_SAFE_SOURCES: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ClassifiedToolResult:
    tool_name: str
    content: str
    scope: MemoryScope


def classify_tool_result(
    tool_name: str,
    content: str,
    *,
    action: str | None = None,
) -> ClassifiedToolResult:
    """Deterministic lookup — this function must NEVER call an LLM and must
    NEVER be influenced by the agent's own judgment. Any (tool_name, action)
    pair not explicitly listed in KNOWN_SAFE_SOURCES defaults to VOLATILE,
    never PERSISTABLE: a false "safe to remember" produces a confidently
    wrong answer later, while an unnecessary re-fetch just costs one extra
    tool call. When in doubt, don't persist.
    """
    keys = (f"{tool_name}.{action}", tool_name) if action else (tool_name,)

    if any(key in VOLATILE_TOOL_SOURCES for key in keys):
        scope = MemoryScope.VOLATILE
    elif any(key in KNOWN_SAFE_SOURCES for key in keys):
        scope = MemoryScope.PERSISTABLE
    else:
        scope = MemoryScope.VOLATILE

    return ClassifiedToolResult(tool_name=tool_name, content=content, scope=scope)


def filter_persistable_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop tool-result messages classified VOLATILE before they reach
    consolidation.

    This is the actual interception point that stops the stale-bookshelf
    bug: volatile tool results must never survive into a session summary,
    ``history.jsonl``, or (via Dream) ``USER.md``/``MEMORY.md``. They may
    still be used to answer the *current* turn — this only filters what
    gets archived, not what the model saw live.

    Non-tool messages (user/assistant prose) always pass through unchanged.
    """
    kept: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") == "tool":
            classified = classify_tool_result(
                tool_name=str(message.get("name") or ""),
                content=str(message.get("content") or ""),
            )
            if classified.scope is MemoryScope.VOLATILE:
                continue
        kept.append(message)
    return kept
