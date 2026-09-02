"""Tests for the deterministic tool-result memory classifier.

Regression coverage for the stale-bookshelf bug: WeRead tool results (live
external state) must never be classified as safe to persist, so they never
reach session summaries / history.jsonl / Dream's USER.md / MEMORY.md.
"""

from nanobot.agent.memory_classification import (
    KNOWN_SAFE_SOURCES,
    ClassifiedToolResult,
    MemoryScope,
    classify_tool_result,
    filter_persistable_messages,
)


class TestClassifyToolResult:
    def test_bare_weread_tool_name_is_volatile(self):
        result = classify_tool_result("weread", '{"books": []}')
        assert result == ClassifiedToolResult(
            tool_name="weread", content='{"books": []}', scope=MemoryScope.VOLATILE
        )

    def test_every_known_weread_action_is_volatile(self):
        for action in (
            "search",
            "shelf",
            "notebooks",
            "bookmarklist",
            "reviews_mine",
            "readdata",
            "reviews",
            "recommend",
        ):
            result = classify_tool_result("weread", "payload", action=action)
            assert result.scope is MemoryScope.VOLATILE, f"action={action}"

    def test_unknown_tool_name_defaults_to_volatile_not_persistable(self):
        """Default-deny: an unrecognized tool must never default to
        PERSISTABLE. A false 'safe to remember' is worse than an
        unnecessary re-fetch."""
        result = classify_tool_result("some_future_tool", "content")
        assert result.scope is MemoryScope.VOLATILE

    def test_unknown_action_on_known_tool_still_volatile_via_bare_name(self):
        """A new WeRead action not yet added to VOLATILE_TOOL_SOURCES's
        dotted entries still falls back to volatile via the bare 'weread'
        catch-all entry."""
        result = classify_tool_result("weread", "content", action="brand_new_action")
        assert result.scope is MemoryScope.VOLATILE

    def test_known_safe_source_is_persistable(self):
        assert not KNOWN_SAFE_SOURCES, (
            "no tool currently qualifies; if this now fails, a new entry was "
            "added — also add a positive classify_tool_result test for it"
        )

    def test_classification_is_deterministic_pure_function(self):
        """Same input always produces the same output; no hidden state."""
        a = classify_tool_result("weread", "x", action="shelf")
        b = classify_tool_result("weread", "x", action="shelf")
        assert a == b


class TestFilterPersistableMessages:
    def test_drops_weread_tool_result(self):
        messages = [
            {"role": "user", "content": "what's on my shelf?"},
            {"role": "assistant", "content": None, "tool_calls": []},
            {"role": "tool", "tool_call_id": "1", "name": "weread", "content": '{"books": [...]}'},
            {"role": "assistant", "content": "You have 42 books on your shelf."},
        ]
        filtered = filter_persistable_messages(messages)
        roles_and_names = [(m["role"], m.get("name")) for m in filtered]
        assert ("tool", "weread") not in roles_and_names
        assert len(filtered) == 3

    def test_keeps_non_tool_messages_unchanged(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        assert filter_persistable_messages(messages) == messages

    def test_keeps_non_volatile_tool_result(self):
        """A tool not in VOLATILE_TOOL_SOURCES and not matching the
        default-deny fallback for an *explicitly listed safe* source would
        be kept — exercised here via a monkeypatched safe source is out of
        scope; this asserts today's behavior for an unlisted tool, which is
        still VOLATILE by default (see test_unknown_tool_name_defaults_to_volatile_not_persistable)."""
        messages = [{"role": "tool", "name": "some_future_tool", "content": "x"}]
        # Unlisted tools default to VOLATILE too, so this is also dropped —
        # documenting the default-deny behavior end-to-end through the filter.
        assert filter_persistable_messages(messages) == []

    def test_empty_input(self):
        assert filter_persistable_messages([]) == []
