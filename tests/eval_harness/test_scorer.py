"""Tests for eval/scorer.py — pure functions, no LLM calls involved."""

from __future__ import annotations

from eval.scorer import compute_metrics, score_case
from eval.tool_call_cases import ToolCallCase
from eval.trace_capture import TurnTrace


def _trace(tool_calls=None, final_answer="answer"):
    return TurnTrace(question="q", tool_calls=tool_calls or [], final_answer=final_answer)


class TestScoreCase:
    def test_correct_positive_call_scores_correct(self):
        case = ToolCallCase(id="c1", question="q", expected_tool="weread_shelf")
        trace = _trace([{"name": "weread_shelf", "args": {}}])
        scored = score_case(case, trace)
        assert scored["invocation_correct"] is True
        assert scored["actual_tool"] == "weread_shelf"

    def test_wrong_tool_scores_incorrect(self):
        case = ToolCallCase(id="c2", question="q", expected_tool="weread_shelf")
        trace = _trace([{"name": "weread_stats", "args": {}}])
        scored = score_case(case, trace)
        assert scored["invocation_correct"] is False
        assert scored["actual_tool"] == "weread_stats"

    def test_no_call_when_expected_scores_incorrect(self):
        case = ToolCallCase(id="c3", question="q", expected_tool="weread_shelf")
        trace = _trace([])
        scored = score_case(case, trace)
        assert scored["invocation_correct"] is False
        assert scored["actual_tool"] is None

    def test_negative_case_no_call_scores_correct(self):
        case = ToolCallCase(id="c4", question="q", expected_tool=None, category="negative")
        trace = _trace([])
        scored = score_case(case, trace)
        assert scored["invocation_correct"] is True

    def test_negative_case_unwanted_call_scores_incorrect(self):
        case = ToolCallCase(id="c5", question="q", expected_tool=None, category="negative")
        trace = _trace([{"name": "weread_shelf", "args": {}}])
        scored = score_case(case, trace)
        assert scored["invocation_correct"] is False

    def test_only_first_tool_call_is_judged(self):
        case = ToolCallCase(id="c6", question="q", expected_tool="weread_shelf")
        trace = _trace([{"name": "weread_shelf", "args": {}}, {"name": "weread_stats", "args": {}}])
        scored = score_case(case, trace)
        assert scored["invocation_correct"] is True
        assert scored["extra_tool_calls"] is True

    def test_matching_args_scores_args_correct(self):
        case = ToolCallCase(
            id="c7",
            question="q",
            expected_tool="weread_progress",
            expected_args={"book_title": "Sapiens"},
        )
        trace = _trace([{"name": "weread_progress", "args": {"book_title": "Sapiens", "extra": 1}}])
        scored = score_case(case, trace)
        assert scored["args_correct"] is True

    def test_mismatched_args_scores_args_incorrect(self):
        case = ToolCallCase(
            id="c8",
            question="q",
            expected_tool="weread_progress",
            expected_args={"book_title": "Sapiens"},
        )
        trace = _trace([{"name": "weread_progress", "args": {"book_title": "Other Book"}}])
        scored = score_case(case, trace)
        assert scored["args_correct"] is False

    def test_args_not_checked_when_tool_wrong(self):
        """If the wrong tool was called, args_correct must stay None — there's
        nothing meaningful to compare arguments against."""
        case = ToolCallCase(
            id="c9",
            question="q",
            expected_tool="weread_progress",
            expected_args={"book_title": "Sapiens"},
        )
        trace = _trace([{"name": "weread_stats", "args": {"book_title": "Sapiens"}}])
        scored = score_case(case, trace)
        assert scored["args_correct"] is None

    def test_no_expected_args_means_args_correct_stays_none(self):
        case = ToolCallCase(id="c10", question="q", expected_tool="weread_shelf")
        trace = _trace([{"name": "weread_shelf", "args": {}}])
        scored = score_case(case, trace)
        assert scored["args_correct"] is None


class TestScoreCaseSequence:
    """expected_tool_sequence adds a softer signal on top of the hard
    first-call invocation_correct check — it must never change
    invocation_correct itself."""

    def test_no_sequence_expected_leaves_sequence_correct_none(self):
        case = ToolCallCase(id="c11", question="q", expected_tool="weread_shelf")
        trace = _trace([{"name": "weread_shelf", "args": {}}])
        scored = score_case(case, trace)
        assert scored["sequence_correct"] is None

    def test_exact_sequence_match_scores_correct(self):
        case = ToolCallCase(
            id="c12", question="q", expected_tool="weread_shelf",
            expected_tool_sequence=["weread_shelf", "weread_progress"],
        )
        trace = _trace([
            {"name": "weread_shelf", "args": {}},
            {"name": "weread_progress", "args": {"book_title": "War and Peace"}},
        ])
        scored = score_case(case, trace)
        assert scored["sequence_correct"] is True
        assert scored["invocation_correct"] is True  # first-call check still passes too

    def test_wrong_order_scores_sequence_incorrect(self):
        case = ToolCallCase(
            id="c13", question="q", expected_tool="weread_shelf",
            expected_tool_sequence=["weread_shelf", "weread_progress"],
        )
        trace = _trace([
            {"name": "weread_progress", "args": {}},
            {"name": "weread_shelf", "args": {}},
        ])
        scored = score_case(case, trace)
        assert scored["sequence_correct"] is False
        assert scored["invocation_correct"] is False  # first call also wrong here

    def test_stopping_after_first_step_fails_sequence_but_not_invocation(self):
        """A single well-justified call that already answers the question
        must not fail the hard pass/fail metric — only the softer
        sequence_accuracy signal reflects the shorter-than-expected chain."""
        case = ToolCallCase(
            id="c14", question="q", expected_tool="weread_shelf",
            expected_tool_sequence=["weread_shelf", "weread_progress"],
        )
        trace = _trace([{"name": "weread_shelf", "args": {}}])
        scored = score_case(case, trace)
        assert scored["invocation_correct"] is True
        assert scored["sequence_correct"] is False

    def test_extra_calls_after_expected_sequence_do_not_fail_it(self):
        case = ToolCallCase(
            id="c15", question="q", expected_tool="weread_shelf",
            expected_tool_sequence=["weread_shelf", "weread_progress"],
        )
        trace = _trace([
            {"name": "weread_shelf", "args": {}},
            {"name": "weread_progress", "args": {}},
            {"name": "weread_stats", "args": {}},
        ])
        scored = score_case(case, trace)
        assert scored["sequence_correct"] is True

    def test_actual_tool_sequence_recorded_regardless_of_expectation(self):
        case = ToolCallCase(id="c16", question="q", expected_tool="weread_shelf")
        trace = _trace([{"name": "weread_shelf", "args": {}}, {"name": "weread_progress", "args": {}}])
        scored = score_case(case, trace)
        assert scored["actual_tool_sequence"] == ["weread_shelf", "weread_progress"]


class TestComputeMetrics:
    def test_all_correct_gives_perfect_scores(self):
        cases = [
            ToolCallCase(id="p1", question="q", expected_tool="weread_shelf"),
            ToolCallCase(id="n1", question="q", expected_tool=None, category="negative"),
        ]
        traces = [_trace([{"name": "weread_shelf", "args": {}}]), _trace([])]
        scored = [score_case(c, t) for c, t in zip(cases, traces)]
        metrics = compute_metrics(scored)
        assert metrics["invocation_recall"] == 1.0
        assert metrics["invocation_precision"] == 1.0
        assert metrics["negative_case_accuracy"] == 1.0
        assert metrics["total_cases"] == 2

    def test_precision_penalized_by_wrong_call_on_negative_case(self):
        cases = [
            ToolCallCase(id="p1", question="q", expected_tool="weread_shelf"),
            ToolCallCase(id="n1", question="q", expected_tool=None, category="negative"),
        ]
        traces = [
            _trace([{"name": "weread_shelf", "args": {}}]),
            _trace([{"name": "weread_shelf", "args": {}}]),  # wrongly called on a negative case
        ]
        scored = [score_case(c, t) for c, t in zip(cases, traces)]
        metrics = compute_metrics(scored)
        assert metrics["invocation_recall"] == 1.0  # the one positive case was still right
        assert metrics["invocation_precision"] == 0.5  # 1 of 2 calls made was correct
        assert metrics["negative_case_accuracy"] == 0.0

    def test_no_positive_cases_gives_none_recall(self):
        cases = [ToolCallCase(id="n1", question="q", expected_tool=None, category="negative")]
        scored = [score_case(cases[0], _trace([]))]
        metrics = compute_metrics(scored)
        assert metrics["invocation_recall"] is None

    def test_no_calls_at_all_gives_none_precision(self):
        cases = [ToolCallCase(id="n1", question="q", expected_tool=None, category="negative")]
        scored = [score_case(cases[0], _trace([]))]
        metrics = compute_metrics(scored)
        assert metrics["invocation_precision"] is None

    def test_argument_accuracy_only_counts_arg_checked_cases(self):
        cases = [
            ToolCallCase(id="p1", question="q", expected_tool="weread_shelf"),  # no expected_args
            ToolCallCase(
                id="p2", question="q", expected_tool="weread_progress",
                expected_args={"book_title": "Sapiens"},
            ),
        ]
        traces = [
            _trace([{"name": "weread_shelf", "args": {}}]),
            _trace([{"name": "weread_progress", "args": {"book_title": "Sapiens"}}]),
        ]
        scored = [score_case(c, t) for c, t in zip(cases, traces)]
        metrics = compute_metrics(scored)
        assert metrics["argument_accuracy"] == 1.0  # only p2 counted

    def test_sequence_accuracy_only_counts_sequence_checked_cases(self):
        cases = [
            ToolCallCase(id="p1", question="q", expected_tool="weread_shelf"),  # no sequence expected
            ToolCallCase(
                id="p2", question="q", expected_tool="weread_shelf",
                expected_tool_sequence=["weread_shelf", "weread_progress"],
            ),
        ]
        traces = [
            _trace([{"name": "weread_shelf", "args": {}}]),
            _trace([{"name": "weread_shelf", "args": {}}]),  # stopped early — sequence incorrect
        ]
        scored = [score_case(c, t) for c, t in zip(cases, traces)]
        metrics = compute_metrics(scored)
        assert metrics["sequence_accuracy"] == 0.0  # only p2 counted, and it fell short

    def test_sequence_accuracy_is_none_when_no_case_specifies_a_sequence(self):
        cases = [ToolCallCase(id="p1", question="q", expected_tool="weread_shelf")]
        scored = [score_case(cases[0], _trace([{"name": "weread_shelf", "args": {}}]))]
        metrics = compute_metrics(scored)
        assert metrics["sequence_accuracy"] is None
