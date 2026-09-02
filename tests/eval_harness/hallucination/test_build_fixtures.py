"""Tests for eval/hallucination/build_fixtures.py's pure/mockable logic.

Never calls real WeRead or LLM APIs — nanobot.agent.tools.weread.call_weread_api
is patched at eval.hallucination.build_fixtures.call_weread_api (the name
as imported into that module), and the drafting LLM call is exercised via
a mocked provider.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from eval.hallucination.build_fixtures import (
    _claims_from_tool_args,
    _draft_claims_and_questions,
    _fetch_all_notebook_entries,
    _fetch_real_highlights,
    _filter_candidates,
    _print_candidates,
)
from nanobot.agent.tools.weread import WeReadError
from nanobot.providers.base import GenerationSettings, LLMResponse, ToolCallRequest
from nanobot.utils.llm_runtime import LLMRuntime


class TestClaimsFromToolArgs:
    def test_maps_near_highlight_index_to_position(self):
        real_highlights = ["h0", "h1", "h2", "h3", "h4"]  # 5 items, denom=4
        args = {
            "injected_claims": [
                {"text": "fake", "why_false": "because", "near_highlight_index": 2},
            ]
        }
        claims = _claims_from_tool_args(real_highlights, args)
        assert claims[0].position == 2 / 4
        assert claims[0].is_true is False
        assert claims[0].text == "fake"
        assert claims[0].why_false == "because"

    def test_clamps_out_of_range_index(self):
        real_highlights = ["h0", "h1"]
        args = {"injected_claims": [{"text": "x", "why_false": "y", "near_highlight_index": 99}]}
        claims = _claims_from_tool_args(real_highlights, args)
        assert claims[0].position == 1.0  # clamped to last valid index

    def test_negative_index_clamps_to_zero(self):
        real_highlights = ["h0", "h1", "h2"]
        args = {"injected_claims": [{"text": "x", "why_false": "y", "near_highlight_index": -5}]}
        claims = _claims_from_tool_args(real_highlights, args)
        assert claims[0].position == 0.0

    def test_non_integer_index_defaults_to_zero(self):
        real_highlights = ["h0", "h1", "h2"]
        args = {"injected_claims": [{"text": "x", "why_false": "y", "near_highlight_index": "not a number"}]}
        claims = _claims_from_tool_args(real_highlights, args)
        assert claims[0].position == 0.0

    def test_single_highlight_does_not_divide_by_zero(self):
        real_highlights = ["only one"]
        args = {"injected_claims": [{"text": "x", "why_false": "y", "near_highlight_index": 0}]}
        claims = _claims_from_tool_args(real_highlights, args)
        assert claims[0].position == 0.0

    def test_empty_injected_claims(self):
        assert _claims_from_tool_args(["h0"], {"injected_claims": []}) == []

    def test_missing_injected_claims_key(self):
        assert _claims_from_tool_args(["h0"], {}) == []


class TestFetchAllNotebookEntries:
    async def test_single_page_no_pagination_needed(self):
        payload = {"books": [{"bookId": "1", "noteCount": 5}], "hasMore": 0}
        mock = AsyncMock(return_value=payload)
        with patch("eval.hallucination.build_fixtures.call_weread_api", mock):
            entries = await _fetch_all_notebook_entries("fake-key")
        assert len(entries) == 1
        mock.assert_awaited_once()

    async def test_pages_until_has_more_is_false(self):
        page1 = {"books": [{"bookId": "1", "noteCount": 5, "sort": 100}], "hasMore": 1}
        page2 = {"books": [{"bookId": "2", "noteCount": 5, "sort": 50}], "hasMore": 0}
        mock = AsyncMock(side_effect=[page1, page2])
        with patch("eval.hallucination.build_fixtures.call_weread_api", mock):
            entries = await _fetch_all_notebook_entries("fake-key")

        assert [e["bookId"] for e in entries] == ["1", "2"]
        assert mock.await_count == 2
        # Second call must pass the first page's last entry's `sort` as
        # lastSort — that's the real API's cursor, not offset/limit.
        second_call_kwargs = mock.await_args_list[1].kwargs
        assert second_call_kwargs["lastSort"] == 100

    async def test_missing_cursor_stops_instead_of_looping_forever(self):
        page1 = {"books": [{"bookId": "1", "noteCount": 5}], "hasMore": 1}  # no "sort" field
        mock = AsyncMock(return_value=page1)
        with patch("eval.hallucination.build_fixtures.call_weread_api", mock):
            entries = await _fetch_all_notebook_entries("fake-key")
        assert len(entries) == 1
        mock.assert_awaited_once()

    async def test_empty_page_stops_pagination(self):
        page1 = {"books": [], "hasMore": 1}
        mock = AsyncMock(return_value=page1)
        with patch("eval.hallucination.build_fixtures.call_weread_api", mock):
            entries = await _fetch_all_notebook_entries("fake-key")
        assert entries == []
        mock.assert_awaited_once()


class TestFilterCandidates:
    def test_filters_by_min_highlights_and_sorts_descending(self):
        entries = [
            {"bookId": "1", "noteCount": 3, "book": {"title": "Too few"}},
            {"bookId": "2", "noteCount": 5, "book": {"title": "Exactly enough"}},
            {"bookId": "3", "noteCount": 20, "book": {"title": "Lots"}},
            {"bookId": "4", "noteCount": 8, "book": {"title": "Some"}},
        ]
        candidates = _filter_candidates(entries, min_highlights=5)
        assert [c["book_id"] for c in candidates] == ["3", "4", "2"]
        assert candidates[0]["note_count"] == 20

    def test_skips_entries_without_a_book_id(self):
        entries = [{"noteCount": 10, "book": {"title": "No id"}}]
        assert _filter_candidates(entries, min_highlights=5) == []

    def test_empty_entries_returns_empty_list(self):
        assert _filter_candidates([], min_highlights=5) == []

    def test_respects_custom_min_highlights(self):
        entries = [{"bookId": "1", "noteCount": 2, "book": {"title": "Few"}}]
        assert _filter_candidates(entries, min_highlights=5) == []
        candidates = _filter_candidates(entries, min_highlights=1)
        assert [c["book_id"] for c in candidates] == ["1"]

    def test_default_min_highlights_is_five(self):
        entries = [{"bookId": "1", "noteCount": 4, "book": {"title": "Just under"}}]
        assert _filter_candidates(entries) == []


class TestPrintCandidates:
    def test_prints_book_id_title_and_count(self, capsys):
        _print_candidates(
            [{"book_id": "42", "title": "Dune", "author": "Herbert", "note_count": 12}],
            total_books_with_notes=1,
        )
        out = capsys.readouterr().out
        assert "42" in out
        assert "Dune" in out
        assert "12" in out
        assert "--book-ids" in out

    def test_empty_candidates_prints_helpful_message_with_min_highlights_hint(self, capsys):
        _print_candidates([], total_books_with_notes=3, min_highlights=5)
        out = capsys.readouterr().out
        assert "No books" in out
        assert "--min-highlights" in out

    def test_reports_total_books_with_notes_vs_filtered_count(self, capsys):
        """This is the diagnostic line for 'why did I only get one book' —
        must distinguish a strict threshold from an actual fetch problem."""
        _print_candidates(
            [{"book_id": "1", "title": "Only One", "author": None, "note_count": 39}],
            total_books_with_notes=27,
            min_highlights=5,
        )
        out = capsys.readouterr().out
        assert "27" in out
        assert "1 of them" in out


class TestFetchRealHighlights:
    async def test_extracts_mark_text_and_title(self):
        payload = {
            "book": {"title": "Dune"},
            "updated": [
                {"markText": "Fear is the mind-killer."},
                {"markText": "  The spice must flow.  "},
                {"markText": ""},  # blank text must be dropped
                {"no_markText_key": True},
            ],
        }
        with patch(
            "eval.hallucination.build_fixtures.call_weread_api",
            AsyncMock(return_value=payload),
        ):
            title, highlights = await _fetch_real_highlights("fake-key", "book-1")

        assert title == "Dune"
        assert highlights == ["Fear is the mind-killer.", "The spice must flow."]

    async def test_falls_back_to_book_id_when_title_missing(self):
        payload = {"book": {}, "updated": []}
        with patch(
            "eval.hallucination.build_fixtures.call_weread_api",
            AsyncMock(return_value=payload),
        ):
            title, highlights = await _fetch_real_highlights("fake-key", "book-1")
        assert title == "book-1"
        assert highlights == []

    async def test_propagates_weread_error(self):
        with patch(
            "eval.hallucination.build_fixtures.call_weread_api",
            AsyncMock(side_effect=WeReadError("boom", status=502)),
        ):
            try:
                await _fetch_real_highlights("fake-key", "book-1")
                raise AssertionError("expected WeReadError")
            except WeReadError as exc:
                assert exc.message == "boom"


def _mock_provider():
    provider = AsyncMock()
    provider.generation = GenerationSettings(max_tokens=100)
    return provider


def _runtime(provider):
    return LLMRuntime.capture(provider, "test-model", context_window_tokens=10_000)


class TestDraftClaimsAndQuestions:
    async def test_returns_claims_and_questions_from_structured_output(self):
        provider = _mock_provider()
        provider.chat_with_retry.return_value = LLMResponse(
            content=None,
            tool_calls=[
                ToolCallRequest(
                    id="1",
                    name="propose_fixture_content",
                    arguments={
                        "injected_claims": [
                            {"text": "false claim", "why_false": "invented", "near_highlight_index": 0}
                        ],
                        "test_questions": ["What happens in this book?"],
                    },
                )
            ],
            usage={},
        )

        claims, questions = await _draft_claims_and_questions(
            provider, _runtime(provider), "Dune", ["real highlight"]
        )

        assert claims[0].text == "false claim"
        assert claims[0].is_true is False
        assert questions == ["What happens in this book?"]

    async def test_raises_when_llm_returns_no_structured_output(self):
        provider = _mock_provider()
        provider.chat_with_retry.return_value = LLMResponse(
            content="plain text, no tool call", tool_calls=[], usage={}
        )
        try:
            await _draft_claims_and_questions(provider, _runtime(provider), "Dune", ["h"])
            raise AssertionError("expected RuntimeError")
        except RuntimeError as exc:
            assert "Dune" in str(exc)
