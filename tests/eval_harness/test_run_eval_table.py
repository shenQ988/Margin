"""Regression tests for eval/run_eval.py's table formatting.

A missed tool call must only be labeled "(from history)" when the case
actually ran as a later turn in a shared session_group — never for a case
running in its own fresh, isolated session, which has no history to have
answered from. See the session where this was caught: ask_about_book_case
(a fresh, isolated single-turn case) was mislabeled "None (from history)"
when the model simply answered from general knowledge without calling the
tool at all — a plain tool-selection miss, not a stale-memory bug.
"""

from __future__ import annotations

from eval.run_eval import _expected_display, _format_actual, _repeat_turn_case_ids
from eval.tool_call_cases import ToolCallCase


class TestFormatActual:
    def test_missed_call_in_fresh_isolated_session_is_not_labeled_from_history(self):
        result = _format_actual(
            actual_tool=None,
            invocation_correct=False,
            expected_tool="ask_about_book",
            is_repeat_turn=False,
        )
        assert result == "None"

    def test_missed_call_on_a_true_repeat_turn_is_labeled_from_history(self):
        result = _format_actual(
            actual_tool=None,
            invocation_correct=False,
            expected_tool="weread_shelf",
            is_repeat_turn=True,
        )
        assert result == "None (from history)"

    def test_correctly_missing_call_on_negative_case_is_plain_none(self):
        result = _format_actual(
            actual_tool=None,
            invocation_correct=True,
            expected_tool=None,
            is_repeat_turn=False,
        )
        assert result == "None"

    def test_actual_tool_present_ignores_repeat_turn_flag(self):
        result = _format_actual(
            actual_tool="weread_shelf",
            invocation_correct=True,
            expected_tool="weread_shelf",
            is_repeat_turn=True,
        )
        assert result == "weread_shelf"


class TestRepeatTurnCaseIds:
    def test_first_case_in_a_group_is_not_a_repeat_turn(self):
        cases = [
            ToolCallCase(id="a", question="q1", expected_tool="x", session_group="g"),
            ToolCallCase(id="b", question="q2", expected_tool="x", session_group="g"),
        ]
        repeat_ids = _repeat_turn_case_ids(cases)
        assert repeat_ids == {"b"}

    def test_ungrouped_case_is_never_a_repeat_turn(self):
        cases = [ToolCallCase(id="solo", question="q", expected_tool="ask_about_book")]
        assert _repeat_turn_case_ids(cases) == set()

    def test_three_case_group_only_flags_second_and_third(self):
        cases = [
            ToolCallCase(id="a", question="q1", expected_tool="x", session_group="g"),
            ToolCallCase(id="b", question="q2", expected_tool="x", session_group="g"),
            ToolCallCase(id="c", question="q3", expected_tool="x", session_group="g"),
        ]
        assert _repeat_turn_case_ids(cases) == {"b", "c"}

    def test_matches_real_dataset_regression_pairs(self):
        """Sanity check against the actual EVAL_CASES dataset: the second
        case in each regression pair must be flagged, the first must not."""
        from eval.tool_call_cases import EVAL_CASES

        repeat_ids = _repeat_turn_case_ids(EVAL_CASES)
        assert "repeat_shelf_q2" in repeat_ids
        assert "repeat_shelf_q1" not in repeat_ids
        assert "repeat_notebooks_q2" in repeat_ids
        assert "repeat_notebooks_q1" not in repeat_ids
        assert "ask_about_book_case" not in repeat_ids


class TestExpectedDisplay:
    def test_single_tool_case_shows_bare_tool_name(self):
        scored = {"expected_tool": "weread_shelf", "expected_tool_sequence": None}
        assert _expected_display(scored) == "weread_shelf"

    def test_sequence_case_shows_arrow_joined_steps(self):
        scored = {
            "expected_tool": "weread_shelf",
            "expected_tool_sequence": ["weread_shelf", "weread_progress"],
        }
        assert _expected_display(scored) == "weread_shelf → weread_progress"

    def test_negative_case_shows_none(self):
        scored = {"expected_tool": None, "expected_tool_sequence": None}
        assert _expected_display(scored) == "None"
