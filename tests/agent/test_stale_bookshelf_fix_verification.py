"""Standalone verification for the stale-bookshelf memory bug fix.

Bug: WeRead tool results (shelf, progress, notebooks, bookmarks, stats — all
live external state) were flowing into session-summary consolidation and,
from there, into Dream's durable memory files. Once the agent answered a
bookshelf question once, the same stale answer kept resurfacing in later
turns/sessions.

The primary fix is structural: nanobot/agent/memory.py filters volatile tool
results out of both the LLM-summarization path (Consolidator.archive) and
the raw-dump fallback (MemoryStore.raw_archive) before either can write to
history.jsonl, using the deterministic, LLM-free classifier in
nanobot/agent/memory_classification.py. A short WeReadTool docstring note is
a soft backstop on top of that — it just discourages the model from reusing
its own prior in-conversation answer; it is not what actually prevents
persistence.

This file verifies three things end to end:
  1. A weread.shelf tool result classifies VOLATILE.
  2. That volatile content does not survive into the resulting
     consolidation summary or history.jsonl entry.
  3. A genuinely persistable tool result still reaches persistent memory —
     proving the filter is selective, not a blanket block on all tool
     output. (No tool in the current registry is classified PERSISTABLE —
     see KNOWN_SAFE_SOURCES's docstring — so this simulates one via
     monkeypatch rather than inventing a fictional production tool.)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.memory import Consolidator, MemoryStore
from nanobot.agent.memory_classification import MemoryScope, classify_tool_result
from nanobot.providers.base import GenerationSettings
from nanobot.utils.llm_runtime import LLMRuntime


@pytest.fixture
def store(tmp_path):
    return MemoryStore(tmp_path)


@pytest.fixture
def mock_provider():
    p = MagicMock()
    p.chat_with_retry = AsyncMock()
    p.generation = GenerationSettings(max_tokens=100)
    return p


@pytest.fixture
def runtime(mock_provider):
    return LLMRuntime.capture(mock_provider, "test-model", context_window_tokens=1000)


@pytest.fixture
def consolidator(store):
    sessions = MagicMock()
    sessions.save = MagicMock()
    return Consolidator(
        store=store,
        sessions=sessions,
        build_messages=MagicMock(return_value=[]),
        get_tool_definitions=MagicMock(return_value=[]),
    )


class TestStep1ClassificationIsVolatile:
    def test_weread_shelf_result_classifies_volatile(self):
        result = classify_tool_result(
            "weread",
            '{"books": [{"title": "STALE_SHELF_PAYLOAD", "count": 42}]}',
            action="shelf",
        )
        assert result.scope is MemoryScope.VOLATILE

    def test_classification_is_pure_and_deterministic(self):
        """No LLM call, no randomness, no hidden state: same input, same
        output, every time. (This asserts the *contract*, not just one
        sample — classify_tool_result must never accept a runtime/provider
        argument, which the signature itself enforces.)"""
        import inspect

        sig = inspect.signature(classify_tool_result)
        assert "runtime" not in sig.parameters
        assert "provider" not in sig.parameters
        assert "llm" not in sig.parameters

        results = {
            classify_tool_result("weread", "content", action="shelf")
            for _ in range(5)
        }
        assert len(results) == 1


class TestStep2VolatileContentExcludedFromSummary:
    """The volatile weread.shelf payload must not survive into either the
    prompt sent to the summarizer LLM or the resulting persisted
    history.jsonl entry — via the LLM-summarization path and the raw-dump
    fallback path."""

    async def test_excluded_from_summarizer_prompt_and_history(
        self, consolidator, mock_provider, store, runtime
    ):
        mock_provider.chat_with_retry.return_value = MagicMock(
            content="User asked about their shelf.", finish_reason="stop"
        )
        messages = [
            {"role": "user", "content": "what's on my shelf?"},
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "name": "weread",
                "content": '{"books": [{"title": "STALE_SHELF_PAYLOAD", "count": 42}]}',
            },
            {"role": "assistant", "content": "You have books on your shelf."},
        ]

        await consolidator.archive(messages, runtime=runtime)

        prompt = mock_provider.chat_with_retry.call_args.kwargs["messages"][1]["content"]
        assert "STALE_SHELF_PAYLOAD" not in prompt

        entries = store.read_unprocessed_history(since_cursor=0)
        assert len(entries) == 1
        assert "STALE_SHELF_PAYLOAD" not in entries[0]["content"]

    async def test_excluded_from_raw_dump_fallback(
        self, consolidator, mock_provider, store, runtime
    ):
        """Same guarantee when the summarization LLM call itself fails."""
        mock_provider.chat_with_retry.side_effect = Exception("API error")
        messages = [
            {"role": "user", "content": "what's on my shelf?"},
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "name": "weread",
                "content": '{"books": [{"title": "STALE_SHELF_PAYLOAD", "count": 42}]}',
            },
        ]

        await consolidator.archive(messages, runtime=runtime)

        entries = store.read_unprocessed_history(since_cursor=0)
        assert "[RAW]" in entries[0]["content"]
        assert "STALE_SHELF_PAYLOAD" not in entries[0]["content"]


class TestStep3PersistableEventStillReachesMemory:
    """Sanity check that the fix filters selectively, not a blanket
    blackout of every tool result."""

    async def test_persistable_tool_result_reaches_summary_and_history(
        self, consolidator, mock_provider, store, runtime, monkeypatch
    ):
        monkeypatch.setattr(
            "nanobot.agent.memory_classification.KNOWN_SAFE_SOURCES",
            frozenset({"add_reading_item"}),
        )
        mock_provider.chat_with_retry.return_value = MagicMock(
            content="User added 'Project Hail Mary' to their reading list.",
            finish_reason="stop",
        )
        messages = [
            {"role": "user", "content": "add Project Hail Mary to my list"},
            {
                "role": "tool",
                "tool_call_id": "call-2",
                "name": "add_reading_item",
                "content": '{"status": "confirmed", "title": "Project Hail Mary"}',
            },
        ]

        await consolidator.archive(messages, runtime=runtime)

        # The persistable tool result reached the summarizer prompt...
        prompt = mock_provider.chat_with_retry.call_args.kwargs["messages"][1]["content"]
        assert "confirmed" in prompt
        assert "Project Hail Mary" in prompt

        # ...and the resulting summary was actually persisted to history.jsonl.
        entries = store.read_unprocessed_history(since_cursor=0)
        assert len(entries) == 1
        assert "Project Hail Mary" in entries[0]["content"]

    def test_unpatched_registry_has_no_persistable_tools_yet(self):
        """Documents the current state so this test file breaks loudly (not
        silently) the day a real tool is added to KNOWN_SAFE_SOURCES —
        that's the signal to add a real (non-monkeypatched) version of the
        test above for it."""
        from nanobot.agent.memory_classification import KNOWN_SAFE_SOURCES

        assert KNOWN_SAFE_SOURCES == frozenset()
